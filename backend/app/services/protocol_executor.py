"""
Protocol Executor — converts thinking protocols into system prompt instructions
and handles orchestrator delegation, todo list tracking, and skill invocation.

Architecture:
  1. Orchestrator protocol → system prompt that drives high-level reasoning
  2. Child protocols → injected when orchestrator delegates
  3. Todo step → agent creates a structured task list and follows it
  4. Skills → agent can invoke skills via <<<SKILL:name>>> markers

The executor formats protocol steps into structured instructions that become
part of the LLM system prompt. The agent's responses are parsed for:
  - <<<SKILL:skill_name>>> {json_args} <<<END_SKILL>>> — skill invocation
  - <<<TODO>>> [...items...] <<<END_TODO>>> — todo list creation/update
  - <<<DELEGATE:protocol_name>>> — switch to a child protocol
"""

from __future__ import annotations

import json
import re
from typing import Optional

from app.services.response_styles import get_response_style_prompt


# ── Constants ──────────────────────────────────────────────

SKILL_PATTERN = re.compile(
    r"<<<SKILL:(\w+)>>>\s*(.*?)\s*<<<END_SKILL>>>",
    re.DOTALL,
)

TODO_PATTERN = re.compile(
    r"<<<TODO>>>\s*(.*?)\s*<<<END_TODO>>>",
    re.DOTALL,
)

DELEGATE_PATTERN = re.compile(
    r"<<<DELEGATE:(.+?)>>>",
)

DELEGATE_DONE_PATTERN = re.compile(
    r"<<<DELEGATE_DONE(?::([^>]+))?>>>",
    re.DOTALL,
)

DELEGATE_RESULT_PATTERN = re.compile(
    r"<<<DELEGATE_RESULT>>>(.*?)<<<END_DELEGATE_RESULT>>>",
    re.DOTALL,
)


# ── Step Formatters ────────────────────────────────────────

def _format_action_step(step: dict, indent: str = "") -> str:
    """Format an action step into text instruction."""
    name = step.get("name", "Action")
    instruction = step.get("instruction", "")
    category = step.get("category", "")
    cat_label = f" [{category}]" if category and category != "other" else ""
    return f"{indent}• **{name}**{cat_label}: {instruction}"


def _format_loop_step(step: dict, indent: str = "") -> str:
    """Format a loop step with nested sub-steps."""
    name = step.get("name", "Loop")
    instruction = step.get("instruction", "")
    max_iter = step.get("max_iterations", 5)
    exit_cond = step.get("exit_condition", "")

    lines = [f"{indent}🔄 **{name}** (repeat up to {max_iter} times):"]
    if instruction:
        lines.append(f"{indent}  Goal: {instruction}")
    if exit_cond:
        lines.append(f"{indent}  Exit when: {exit_cond}")

    sub_steps = step.get("steps", [])
    if sub_steps:
        lines.append(f"{indent}  Sub-steps:")
        for i, sub in enumerate(sub_steps, 1):
            lines.append(_format_step(sub, indent=indent + "    ", number=i))

    return "\n".join(lines)


def _format_decision_step(step: dict, indent: str = "") -> str:
    """Format a decision/branching step."""
    name = step.get("name", "Decision")
    instruction = step.get("instruction", "")
    exit_cond = step.get("exit_condition", "")

    lines = [f"{indent}❓ **{name}**: {instruction}"]
    if exit_cond:
        lines.append(f"{indent}  → {exit_cond}")
    return "\n".join(lines)


def _format_delegate_step(step: dict, child_protocols: list[dict], indent: str = "") -> str:
    """Format a delegate step that references child protocols."""
    name = step.get("name", "Delegate")
    instruction = step.get("instruction", "")
    protocol_ids = step.get("protocol_ids", [])

    lines = [f"{indent}📋 **{name}**: {instruction}"]

    # List available child protocols
    available = []
    for cp in child_protocols:
        if not protocol_ids or cp.get("id") in protocol_ids:
            available.append(cp)

    if available:
        lines.append(f"{indent}  Available protocols to delegate to:")
        for cp in available:
            cp_type = cp.get('type', 'standard')
            type_label = f" [orchestrator]" if cp_type == "orchestrator" else ""
            lines.append(f"{indent}    - \"{cp['name']}\"{type_label}: {cp.get('description', 'No description')}")
        lines.append(f"{indent}")
        lines.append(f"{indent}  **Delegation commands:**")
        lines.append(f"{indent}  - To delegate: `<<<DELEGATE:protocol_name>>>`")
        lines.append(f"{indent}  - When delegated work is complete: `<<<DELEGATE_DONE:brief summary of results>>>`")
        lines.append(f"{indent}  - To include detailed result: `<<<DELEGATE_RESULT>>>...details...<<<END_DELEGATE_RESULT>>>`")
        lines.append(f"{indent}")
        lines.append(f"{indent}  You can delegate to multiple protocols sequentially.")
        lines.append(f"{indent}  After each delegation completes, evaluate the result and decide next steps.")
    else:
        lines.append(f"{indent}  (No child protocols configured)")

    return "\n".join(lines)


def _format_todo_step(step: dict, indent: str = "") -> str:
    """Format a todo list step."""
    name = step.get("name", "Create Todo List")
    instruction = step.get("instruction", "")

    lines = [
        f"{indent}📝 **{name}**: {instruction}",
        f"{indent}  Create a structured task list for the current request.",
        f"{indent}  Output your todo list in this format:",
        f"{indent}  <<<TODO>>>",
        f'{indent}  [{{"id": 1, "task": "description", "status": "pending"}}]',
        f"{indent}  <<<END_TODO>>>",
        f"{indent}  Update the list as you complete tasks (status: \"pending\" → \"in_progress\" → \"done\").",
        f"{indent}  Always output the full updated todo list after completing each task.",
    ]
    return "\n".join(lines)


def _format_step(step: dict, indent: str = "", number: int | None = None, child_protocols: list[dict] | None = None) -> str:
    """Format a single step based on its type."""
    prefix = f"{number}. " if number else ""
    step_type = step.get("type", "action")

    if step_type == "action":
        text = _format_action_step(step, indent)
    elif step_type == "loop":
        text = _format_loop_step(step, indent)
    elif step_type == "decision":
        text = _format_decision_step(step, indent)
    elif step_type == "delegate":
        text = _format_delegate_step(step, child_protocols or [], indent)
    elif step_type == "todo":
        text = _format_todo_step(step, indent)
    else:
        text = f"{indent}• {step.get('name', 'Step')}: {step.get('instruction', '')}"

    # Insert number prefix after indent
    if prefix and indent:
        # Replace first occurrence of indent+marker with indent+number+marker
        return text
    elif prefix:
        return f"{prefix}{text.lstrip('•❓🔄📋📝 ')}"

    return text


# ── Protocol Formatters ────────────────────────────────────

def format_protocol_prompt(
    protocol: dict,
    child_protocols: list[dict] | None = None,
    available_skills: list[dict] | None = None,
    current_todo: list[dict] | None = None,
) -> str:
    """
    Convert a thinking protocol into system prompt instructions.

    Args:
        protocol: The protocol dict with name, description, type, steps
        child_protocols: For orchestrators — list of child protocols that can be delegated to
        available_skills: Skills the agent can invoke
        current_todo: Current state of the agent's todo list (if any)

    Returns:
        Formatted system prompt section for the protocol
    """
    name = protocol.get("name", "Protocol")
    description = protocol.get("description", "")
    proto_type = protocol.get("type", "standard")
    steps = protocol.get("steps", [])
    response_style = protocol.get("response_style")

    sections = []

    # Header
    sections.append(f"## Thinking Protocol: {name}")
    if description:
        sections.append(f"_{description}_")
    sections.append("")

    # Response style instructions (injected before protocol-specific content)
    style_prompt = get_response_style_prompt(response_style)
    if style_prompt:
        sections.append(style_prompt)
        sections.append("")

    # Protocol type info
    if proto_type == "orchestrator":
        sections.append("You are operating as an **orchestrator** — your role is to:")
        sections.append("1. **Analyze** the user's request to understand intent, scope, and complexity")
        sections.append("2. **Decompose** complex tasks into sub-tasks if needed")
        sections.append("3. **Select** the best child protocol(s) for each sub-task")
        sections.append("4. **Delegate** to child protocols sequentially")
        sections.append("5. **Evaluate** results from each delegation")
        sections.append("6. **Iterate** — re-delegate or try another protocol if the result is insufficient")
        sections.append("7. **Synthesize** final results from all delegations into a coherent response")
        sections.append("")
        sections.append("**Important orchestrator principles:**")
        sections.append("- You may delegate to the same protocol multiple times with different context")
        sections.append("- You may delegate to multiple protocols in sequence to solve complex tasks")
        sections.append("- Some child protocols are themselves orchestrators — they can manage their own sub-delegations")
        sections.append("- If no child protocol fits perfectly, you can handle the task directly using your skills")
        sections.append("- Always review the quality of delegated work before presenting to the user")
        sections.append("")

    # Steps
    if steps:
        sections.append("### Reasoning Steps")
        sections.append("Follow these steps in order:")
        sections.append("")
        for i, step in enumerate(steps, 1):
            sections.append(f"**Step {i}.**")
            sections.append(_format_step(step, child_protocols=child_protocols or []))
            sections.append("")

    # Skills section
    if available_skills:
        sections.append("### Available Skills")
        sections.append("You can invoke skills by outputting the following markers in your response:")
        sections.append("```")
        sections.append("<<<SKILL:skill_name>>> {\"param\": \"value\"} <<<END_SKILL>>>")
        sections.append("```")
        sections.append("")
        sections.append("Available skills:")
        for skill in available_skills:
            desc = skill.get("description_for_agent") or skill.get("description", "")
            input_schema = skill.get("input_schema", {})
            params_info = ""
            if input_schema and input_schema.get("properties"):
                param_names = list(input_schema["properties"].keys())
                params_info = f" — params: {', '.join(param_names)}"
            sections.append(f"  - **{skill['name']}**: {desc}{params_info}")
        sections.append("")
        sections.append("After invoking a skill, wait for the result before continuing.")
        sections.append("")

    # Current todo list
    if current_todo:
        sections.append("### Current Task List")
        sections.append("Your active todo list (update as you progress):")
        sections.append("")
        for item in current_todo:
            status_icon = {"pending": "⬜", "in_progress": "🔄", "done": "✅", "skipped": "⏭️"}.get(
                item.get("status", "pending"), "⬜"
            )
            sections.append(f"  {status_icon} {item.get('id', '?')}. {item.get('task', 'Unknown task')} [{item.get('status', 'pending')}]")
        sections.append("")

    # General instructions
    sections.append("### Output Rules")
    sections.append("- Think step-by-step following the protocol above")
    sections.append("- When creating or updating a todo list, use <<<TODO>>>...<<<END_TODO>>> markers")
    sections.append("- When invoking a skill, use <<<SKILL:name>>> {args} <<<END_SKILL>>> markers")
    if proto_type == "orchestrator":
        sections.append("")
        sections.append("**Orchestrator delegation commands:**")
        sections.append("- To delegate to a child protocol: `<<<DELEGATE:protocol_name>>>`")
        sections.append("- When your delegated work is complete, signal: `<<<DELEGATE_DONE:brief result summary>>>`")
        sections.append("- To attach detailed results: `<<<DELEGATE_RESULT>>>...<<<END_DELEGATE_RESULT>>>`")
        sections.append("- You can delegate multiple times in a conversation — each delegation is a separate step")
        sections.append("- After delegation completes, you'll see the results. Evaluate and decide next action.")
    sections.append("- Always explain your reasoning before taking actions")
    sections.append("")

    return "\n".join(sections)


def format_child_protocol_prompt(
    child_protocol: dict,
    available_skills: list[dict] | None = None,
    current_todo: list[dict] | None = None,
    parent_context: str = "",
    delegation_stack: list[str] | None = None,
) -> str:
    """
    Format a child protocol after delegation from an orchestrator.

    Args:
        child_protocol: The delegated-to protocol
        available_skills: Skills available
        current_todo: Current todo list state
        parent_context: Context from the orchestrator about why this was delegated
        delegation_stack: Current delegation hierarchy (parent protocol names)
    """
    sections = []

    if delegation_stack:
        chain = " → ".join(delegation_stack)
        sections.append(f"_Delegation chain: {chain} → **{child_protocol.get('name', 'Protocol')}**_")
        sections.append("")

    if parent_context:
        sections.append(f"## Orchestrator Context")
        sections.append(f"The orchestrator has delegated this task to you because: {parent_context}")
        sections.append("")

    # If this child protocol is itself an orchestrator, pass child protocols through
    child_type = child_protocol.get("type", "standard")
    child_protos = child_protocol.get("child_protocols") if child_type == "orchestrator" else None

    sections.append(format_protocol_prompt(
        child_protocol,
        child_protocols=child_protos,
        available_skills=available_skills,
        current_todo=current_todo,
    ))

    # Add instructions about returning results to parent
    sections.append("### Returning Results to Orchestrator")
    sections.append("When you have completed the delegated work:")
    sections.append("1. Summarize what you accomplished")
    sections.append("2. Signal completion: `<<<DELEGATE_DONE:brief summary>>>`")
    sections.append("3. Optionally provide detailed results: `<<<DELEGATE_RESULT>>>...<<<END_DELEGATE_RESULT>>>`")
    sections.append("Control will return to the parent orchestrator which may delegate further work.")
    sections.append("")

    return "\n".join(sections)


# ── Response Parsers ───────────────────────────────────────

def parse_skill_invocations(response_text: str) -> list[dict]:
    """
    Parse skill invocation markers from the agent's response.

    Returns list of: {"skill_name": str, "args": dict, "raw_match": str}
    """
    invocations = []
    for match in SKILL_PATTERN.finditer(response_text):
        skill_name = match.group(1)
        args_text = match.group(2).strip()
        try:
            args = json.loads(args_text) if args_text else {}
        except json.JSONDecodeError:
            args = {"raw": args_text}

        invocations.append({
            "skill_name": skill_name,
            "args": args,
            "raw_match": match.group(0),
        })
    return invocations


def parse_todo_list(response_text: str) -> list[dict] | None:
    """
    Parse todo list markers from the agent's response.

    Returns the todo list if found, or None.
    """
    match = TODO_PATTERN.search(response_text)
    if not match:
        return None

    todo_text = match.group(1).strip()
    try:
        todo_list = json.loads(todo_text)
        if isinstance(todo_list, list):
            return todo_list
    except json.JSONDecodeError:
        # Try to parse line-by-line
        items = []
        for line in todo_text.split("\n"):
            line = line.strip()
            if line and not line.startswith("//"):
                try:
                    item = json.loads(line)
                    items.append(item)
                except json.JSONDecodeError:
                    # Try simple format: "1. task description"
                    m = re.match(r"(\d+)\.\s*(.+)", line)
                    if m:
                        items.append({"id": int(m.group(1)), "task": m.group(2), "status": "pending"})
        if items:
            return items

    return None


def parse_delegate(response_text: str) -> str | None:
    """
    Parse delegate marker from the agent's response.

    Returns the protocol name to delegate to, or None.
    """
    match = DELEGATE_PATTERN.search(response_text)
    if match:
        return match.group(1).strip()
    return None


def parse_delegate_done(response_text: str) -> dict | None:
    """
    Parse <<<DELEGATE_DONE>>> or <<<DELEGATE_DONE:summary>>> marker.
    Indicates the child protocol has finished and control should return
    to the parent orchestrator.

    Returns {"summary": str, "result": str | None} or None.
    """
    match = DELEGATE_DONE_PATTERN.search(response_text)
    if not match:
        return None

    summary = (match.group(1) or "").strip() or None

    # Also extract detailed result block if present
    result_match = DELEGATE_RESULT_PATTERN.search(response_text)
    result_text = result_match.group(1).strip() if result_match else None

    return {
        "summary": summary,
        "result": result_text,
    }


def strip_markers(response_text: str) -> str:
    """Remove all protocol markers from response text for clean display."""
    text = SKILL_PATTERN.sub("", response_text)
    text = TODO_PATTERN.sub("", text)
    text = DELEGATE_PATTERN.sub("", text)
    text = DELEGATE_DONE_PATTERN.sub("", text)
    text = DELEGATE_RESULT_PATTERN.sub("", text)
    return text.strip()


# ── Autonomous (loop) stop marker ──────────────────────────

STOP_PATTERN = re.compile(r"<<<STOP(?::(.+?))?\s*>>>")


def parse_stop(response_text: str) -> str | None:
    """Parse <<<STOP>>> or <<<STOP:reason>>> marker. Returns reason or '' if found."""
    match = STOP_PATTERN.search(response_text)
    if match:
        return (match.group(1) or "").strip()
    return None


def format_loop_protocol_prompt(
    protocol: dict,
    cycle_number: int,
    max_cycles: int | None,
    cycle_state: dict | None = None,
    available_skills: list[dict] | None = None,
    beliefs: dict | None = None,
    aspirations: dict | None = None,
    agent_name: str = "Agent",
    assigned_projects: list[dict] | None = None,
) -> str:
    """
    Build the system prompt for an autonomous loop cycle.

    The loop protocol drives the agent to decide what to do next based on
    its goals, aspirations, beliefs, memories, and available skills.
    """
    sections = []

    name = protocol.get("name", "Autonomous Work")
    description = protocol.get("description", "")
    steps = protocol.get("steps", [])

    sections.append(f"You are **{agent_name}**, an AI agent working **autonomously**.")
    sections.append("")
    sections.append(f"## Autonomous Work Protocol: {name}")
    if description:
        sections.append(f"_{description}_")
    sections.append("")

    # Cycle info
    if max_cycles:
        sections.append(f"**Cycle {cycle_number} of {max_cycles}**")
    else:
        sections.append(f"**Cycle {cycle_number}** (continuous mode — will run until you output <<<STOP>>> or are stopped externally)")
    sections.append("")

    # Previous cycle context
    if cycle_state:
        last_output = cycle_state.get("last_output")
        todo_list = cycle_state.get("todo_list")
        cycle_summary = cycle_state.get("cycle_summary")

        if cycle_summary:
            sections.append("### Previous Cycle Summary")
            sections.append(cycle_summary)
            sections.append("")

        if last_output:
            sections.append("### Your Previous Output")
            preview = last_output[:2000] + "..." if len(last_output) > 2000 else last_output
            sections.append(preview)
            sections.append("")

        if todo_list:
            sections.append("### Current Task List")
            for item in todo_list:
                status_icon = {"pending": "⬜", "in_progress": "🔄", "done": "✅", "skipped": "⏭️"}.get(
                    item.get("status", "pending"), "⬜"
                )
                sections.append(f"  {status_icon} {item.get('id', '?')}. {item.get('task', '')} [{item.get('status', 'pending')}]")
            sections.append("")

    # Beliefs
    if beliefs:
        core = beliefs.get("core", [])
        additional = beliefs.get("additional", [])
        if core or additional:
            sections.append("## Your Beliefs & Principles")
            for b in core:
                w = b.get("weight", 1.0)
                weight_indicator = "🔴" if w >= 0.8 else "🟡" if w >= 0.5 else "⚪"
                sections.append(f"  {weight_indicator} {b.get('text', '')} (weight: {w})")
            for b in additional:
                sections.append(f"  ◦ {b.get('text', '')}")
            sections.append("")

    # Aspirations
    if aspirations:
        dreams = aspirations.get("dreams", [])
        desires = aspirations.get("desires", [])
        goals = aspirations.get("goals", [])
        if dreams or desires or goals:
            sections.append("## Your Aspirations")
            if dreams:
                sections.append("### Dreams (long-term visions)")
                for d in dreams:
                    lock = "🔒" if d.get("locked") else "🔓"
                    sections.append(f"  {lock} [{d.get('priority','medium')}] {d.get('text','')}")
            if desires:
                sections.append("### Desires")
                for d in desires:
                    lock = "🔒" if d.get("locked") else "🔓"
                    sections.append(f"  {lock} [{d.get('priority','medium')}] {d.get('text','')}")
            if goals:
                sections.append("### Goals (actionable objectives)")
                for g in goals:
                    lock = "🔒" if g.get("locked") else "🔓"
                    status = g.get("status", "active")
                    sections.append(f"  {lock} [{g.get('priority','medium')}] [{status}] {g.get('text','')}")
            sections.append("")

    # Assigned Projects
    if assigned_projects:
        sections.append("## 🚨 YOUR ASSIGNED PROJECTS (HIGHEST PRIORITY)")
        sections.append("")
        # Gather the first pending task across all projects for explicit instruction
        first_task = None
        first_task_slug = None
        for proj in assigned_projects:
            project_tasks = proj.get("pending_tasks", [])
            if project_tasks and not first_task:
                first_task = project_tasks[0]
                first_task_slug = proj.get("slug", "")

        for proj in assigned_projects:
            lead_marker = " ⭐ [Lead]" if proj.get("is_lead") else ""
            slug = proj.get("slug", "")
            sections.append(f"### 📁 {proj.get('name', 'Unnamed')}{lead_marker}  (slug: `{slug}`)")
            if proj.get("tech_stack"):
                sections.append(f"  Tech: {', '.join(proj['tech_stack'][:10])}")
            # Show pending project tasks — these are what the agent MUST work on
            project_tasks = proj.get("pending_tasks", [])
            if project_tasks:
                sections.append(f"  **YOUR TASKS (do these, not the project goals):**")
                for pt in project_tasks[:10]:
                    priority_icon = {"highest": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "lowest": "⚪"}.get(pt.get("priority", "medium"), "🟡")
                    task_id_str = pt.get("id", "?")
                    task_key_str = pt.get("key", "?")
                    sections.append(f"    {priority_icon} [{pt.get('status','backlog')}] {task_key_str} (id: `{task_id_str}`): {pt.get('title','')} (priority: {pt.get('priority','medium')})")
            else:
                sections.append("  No pending tasks.")
            sections.append("")

        # Explicit current task instruction with example
        if first_task and first_task_slug:
            task_title = first_task.get("title", "")
            task_id = first_task.get("id", "")
            task_key = first_task.get("key", "")
            sections.append(f"---")
            sections.append(f"## 🎯 YOUR CURRENT TASK")
            sections.append(f"**Work on this task NOW:** {task_title}")
            sections.append(f"**Task ID:** `{task_id}` (key: `{task_key}`)")
            sections.append(f"**Project slug:** `{first_task_slug}`")
            sections.append("")
            sections.append("**⚠️ REQUIRED BEFORE WRITING ANY FILE:**")
            sections.append(f"**STEP 1:** Check what files already exist:")
            sections.append("```")
            sections.append(f'<<<SKILL:project_list_files>>> {{"project_slug": "{first_task_slug}"}} <<<END_SKILL>>>')
            sections.append("```")
            sections.append("")
            sections.append("**STEP 2:** Choose a UNIQUE filename:")
            sections.append(f"  - If working on task {task_key}, use a specific name like: `{task_key.lower()}_counter.py`, `{task_key.lower()}_solver.py`")
            sections.append("  - NEVER reuse existing filenames (main.py, solution.py, etc.) - you will OVERWRITE and LOSE previous work!")
            sections.append("")
            sections.append("**STEP 3:** Save your code with the unique filename:")
            sections.append("```")
            sections.append(f'<<<SKILL:project_file_write>>> {{"project_slug": "{first_task_slug}", "path": "{task_key.lower()}_solution.py", "content": "# your code here\\nprint(42)"}} <<<END_SKILL>>>')
            sections.append("```")
            sections.append("⚠️ Code written as markdown/text (without <<<SKILL:project_file_write>>>) is NOT saved!")
            sections.append("")
            sections.append("**STEP 4:** Test/run your code (if needed by task):")
            sections.append("```")
            sections.append(f'<<<SKILL:project_run_code>>> {{"project_slug": "{first_task_slug}", "file_path": "{task_key.lower()}_solution.py"}} <<<END_SKILL>>>')
            sections.append("```")
            sections.append("Check stdout/stderr output to verify it works correctly.")
            sections.append("")
            sections.append("**AFTER completing a task, you MUST do both:**")
            sections.append(f"1. Add a comment explaining what you did:")
            sections.append("```")
            sections.append(f'<<<SKILL:project_task_comment>>> {{"project_slug": "{first_task_slug}", "task_id": "{task_id}", "content": "Completed: wrote solution.py with [description of work]"}} <<<END_SKILL>>>')
            sections.append("```")
            sections.append(f"2. Move the task to 'done' (or 'review' if it needs review):")
            sections.append("```")
            sections.append(f'<<<SKILL:project_update_task>>> {{"project_slug": "{first_task_slug}", "task_id": "{task_id}", "status": "done"}} <<<END_SKILL>>>')
            sections.append("```")
            sections.append("")

    # Protocol steps
    if steps:
        sections.append("### Protocol Steps")
        sections.append("Follow these steps for this cycle:")
        sections.append("")
        for i, step in enumerate(steps, 1):
            sections.append(f"**Step {i}.**")
            sections.append(_format_step(step))
            sections.append("")

    # Skills section — keep compact for small models
    if available_skills:
        sections.append("### Skills")
        sections.append("To use a skill, write: `<<<SKILL:name>>> {json_args} <<<END_SKILL>>>`")
        sections.append("")
        for skill in available_skills:
            desc = skill.get("description_for_agent") or skill.get("description", "")
            schema = skill.get("input_schema", {})
            params = schema.get("properties", {})
            param_str = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in params.items()) if params else ""
            sections.append(f"  - **{skill['name']}**({param_str}): {desc}")
        sections.append("")

    # Output rules — concise
    sections.append("### Rules")
    sections.append("1. Work on YOUR CURRENT TASK (see above)")
    sections.append("2. Save code with <<<SKILL:project_file_write>>> — code in markdown is NOT saved")
    sections.append("3. Update todo: <<<TODO>>> [...] <<<END_TODO>>>")
    sections.append("4. To stop: <<<STOP:reason>>>")
    sections.append("")

    return "\n".join(sections)


# ── Build Full System Prompt ───────────────────────────────

def build_agent_system_prompt(
    base_system_prompt: str,
    agent_name: str,
    protocols: list[dict],
    available_skills: list[dict] | None = None,
    current_todo: list[dict] | None = None,
    beliefs: dict | None = None,
    aspirations: dict | None = None,
) -> str:
    """
    Build the complete system prompt for an agent, combining:
    - Base system prompt (from agent.json)
    - Main/orchestrator protocol
    - Available skills
    - Current todo list state
    - Agent beliefs
    - Agent aspirations (dreams, desires, goals)

    Args:
        base_system_prompt: The agent's custom system prompt
        agent_name: Agent name
        protocols: All assigned protocols (with is_main flag)
        available_skills: Skills this agent can use
        current_todo: Current todo list (persisted in session metadata)
        beliefs: Agent beliefs
        aspirations: Agent aspirations (dreams, desires, goals)
    """
    sections = []

    # Identity
    sections.append(f"You are **{agent_name}**, an AI agent.")
    sections.append("")

    # Base system prompt
    if base_system_prompt:
        sections.append(base_system_prompt)
        sections.append("")

    # Beliefs
    if beliefs:
        core = beliefs.get("core", [])
        additional = beliefs.get("additional", [])
        if core or additional:
            sections.append("## Your Beliefs & Principles")
            for b in core:
                w = b.get("weight", 1.0)
                weight_indicator = "🔴" if w >= 0.8 else "🟡" if w >= 0.5 else "⚪"
                sections.append(f"  {weight_indicator} {b.get('text', '')} (weight: {w})")
            for b in additional:
                sections.append(f"  ◦ {b.get('text', '')}")
            sections.append("")

    # Aspirations (dreams, desires, goals)
    if aspirations:
        dreams = aspirations.get("dreams", [])
        desires = aspirations.get("desires", [])
        goals = aspirations.get("goals", [])
        if dreams or desires or goals:
            sections.append("## Your Aspirations")
            if dreams:
                sections.append("### Dreams (long-term visions)")
                for d in dreams:
                    lock = "🔒" if d.get("locked") else "🔓"
                    prio = d.get("priority", "medium")
                    sections.append(f"  {lock} [{prio}] {d.get('text', '')}")
            if desires:
                sections.append("### Desires")
                for d in desires:
                    lock = "🔒" if d.get("locked") else "🔓"
                    prio = d.get("priority", "medium")
                    sections.append(f"  {lock} [{prio}] {d.get('text', '')}")
            if goals:
                sections.append("### Goals (actionable objectives)")
                for g in goals:
                    lock = "🔒" if g.get("locked") else "🔓"
                    prio = g.get("priority", "medium")
                    status = g.get("status", "active")
                    deadline = f" (deadline: {g['deadline']})" if g.get("deadline") else ""
                    sections.append(f"  {lock} [{prio}] [{status}] {g.get('text', '')}{deadline}")
            sections.append("")
            sections.append("🔒 = set by user, do NOT contradict or override these")
            sections.append("🔓 = you may modify, refine, or create new ones that align with locked items")
            sections.append("")

    # Find main protocol (orchestrator or single standard)
    main_protocol = None
    child_protocols = []

    for p in protocols:
        if p.get("is_main"):
            main_protocol = p
        else:
            child_protocols.append(p)

    # If no main marked, use first orchestrator or first protocol
    if not main_protocol and protocols:
        orchestrators = [p for p in protocols if p.get("type") == "orchestrator"]
        if orchestrators:
            main_protocol = orchestrators[0]
            child_protocols = [p for p in protocols if p.get("id") != main_protocol.get("id")]
        else:
            main_protocol = protocols[0]
            child_protocols = protocols[1:]

    # Protocol instructions
    if main_protocol:
        sections.append(format_protocol_prompt(
            main_protocol,
            child_protocols=child_protocols,
            available_skills=available_skills,
            current_todo=current_todo,
        ))

    # If no protocol but has skills, still list them
    elif available_skills:
        sections.append("### Available Skills")
        sections.append("You can invoke skills by outputting:")
        sections.append("```")
        sections.append("<<<SKILL:skill_name>>> {\"param\": \"value\"} <<<END_SKILL>>>")
        sections.append("```")
        for skill in available_skills:
            desc = skill.get("description_for_agent") or skill.get("description", "")
            sections.append(f"  - **{skill['name']}**: {desc}")
        sections.append("")

    return "\n".join(sections)
