"""
Autonomous Runner — executes self-directed agent work cycles.

The runner creates a chat session and iterates:
  1. Build system prompt from loop protocol + agent context
  2. Send to LLM
  3. Parse response for skills, todos, stop markers
  4. Execute skills, update state
  5. Record thinking log per cycle
  6. Check stop conditions (max_cycles, <<<STOP>>>, agent stopped)
  7. Repeat

Works as a background asyncio task managed via the active_runs registry.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.config import get_settings
from app.models.agent import Agent
from app.models.agent_model import AgentModel
from app.models.agent_protocol import AgentProtocol
from app.models.autonomous_run import AutonomousRun
from app.models.chat import ChatSession, ChatMessage
from app.models.thinking_protocol import ThinkingProtocol
from app.llm.base import Message, GenerationParams, LLMResponse
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.services.thinking_log_service import ThinkingTracker
from app.services.protocol_executor import (
    format_loop_protocol_prompt,
    parse_skill_invocations,
    parse_todo_list,
    parse_stop,
)
from app.services.log_service import syslog_bg

# ── Global registry of active runs ──
# Maps run_id -> asyncio.Task
active_runs: dict[str, asyncio.Task] = {}


async def cleanup_orphaned_runs() -> int:
    """
    On server startup, find any autonomous runs stuck in 'running' status
    (orphaned by a previous server restart) and mark them as 'stopped'.
    Also resets corresponding agent statuses to 'idle'.
    Returns the number of orphaned runs cleaned up.
    """
    count = 0
    async with async_session() as db:
        result = await db.execute(
            select(AutonomousRun).where(AutonomousRun.status == "running")
        )
        orphaned_runs = result.scalars().all()
        for run in orphaned_runs:
            run.status = "stopped"
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = "Orphaned: server restarted during active run"
            # Reset agent status
            agent_result = await db.execute(
                select(Agent).where(Agent.id == run.agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if agent and agent.status == "running":
                agent.status = "idle"
            count += 1
        if count:
            await db.commit()
            logger.warning("Cleaned up %d orphaned autonomous run(s)", count)
    return count


# ── Status mapping: TODO statuses → Task statuses ──
_TODO_STATUS_TO_TASK = {
    "pending": "pending",
    "in_progress": "running",
    "done": "completed",
    "skipped": "cancelled",
}
_TASK_STATUS_TO_TODO = {v: k for k, v in _TODO_STATUS_TO_TASK.items()}


async def sync_todos_to_tasks(
    db: AsyncSession,
    agent_id: uuid.UUID,
    todo_items: list[dict],
    todo_task_map: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Synchronise the agent's TODO list (from <<<TODO>>> markers) with the
    persistent tasks table so that every TODO item is visible in the Tasks tab.

    Parameters
    ----------
    db          – active async session (caller commits)
    agent_id    – the agent owning these tasks
    todo_items  – parsed TODO list from the LLM output
    todo_task_map – existing mapping {todo_id_str: task_uuid_str} from cycle_state

    Returns
    -------
    Updated todo_task_map dict.
    """
    from app.models.task import Task

    mapping = dict(todo_task_map or {})

    for item in todo_items:
        todo_id = str(item.get("id", ""))
        title = (item.get("task") or item.get("title") or f"Task {todo_id}")[:500]
        status = _TODO_STATUS_TO_TASK.get(item.get("status", "pending"), "pending")

        existing_task_id = mapping.get(todo_id)

        if existing_task_id:
            # Update existing Task
            result = await db.execute(
                select(Task).where(Task.id == uuid.UUID(existing_task_id))
            )
            task = result.scalar_one_or_none()
            if task:
                if task.title != title:
                    task.title = title
                if task.status != status:
                    task.status = status
                    if status == "completed" and not task.completed_at:
                        task.completed_at = datetime.now(timezone.utc)
                    elif status == "running" and not task.started_at:
                        task.started_at = datetime.now(timezone.utc)
            else:
                # Task was deleted — re-create
                new_task = Task(
                    agent_id=agent_id,
                    title=title,
                    description="Auto-created from agent TODO list",
                    type="one_time",
                    status=status,
                    priority="normal",
                )
                db.add(new_task)
                await db.flush()
                mapping[todo_id] = str(new_task.id)
        else:
            # Create new Task
            new_task = Task(
                agent_id=agent_id,
                title=title,
                description="Auto-created from agent TODO list",
                type="one_time",
                status=status,
                priority="normal",
            )
            if status == "running":
                new_task.started_at = datetime.now(timezone.utc)
            elif status == "completed":
                new_task.started_at = datetime.now(timezone.utc)
                new_task.completed_at = datetime.now(timezone.utc)
            db.add(new_task)
            await db.flush()
            mapping[todo_id] = str(new_task.id)

    await db.flush()
    return mapping


async def start_autonomous_run(
    agent_id: uuid.UUID,
    mode: str = "continuous",
    max_cycles: int | None = None,
    loop_protocol_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AutonomousRun:
    """
    Create an autonomous run record and launch the background loop.

    Returns the AutonomousRun immediately; actual work happens in background.
    """
    async with async_session() as db:
        # Verify agent exists (load relations for model/protocol access)
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id)
            .options(
                selectinload(Agent.agent_models),
                selectinload(Agent.agent_protocols).selectinload(AgentProtocol.protocol),
            )
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise ValueError("Agent not found")

        # Resolve loop protocol
        protocol_id = loop_protocol_id
        if not protocol_id:
            # Try to find a loop protocol assigned to this agent
            for ap in (agent.agent_protocols or []):
                if ap.protocol and ap.protocol.type == "loop":
                    protocol_id = ap.protocol.id
                    break

        if not protocol_id:
            raise ValueError("No loop protocol found. Assign a loop protocol to the agent first.")

        # Verify protocol exists and is type=loop
        result = await db.execute(select(ThinkingProtocol).where(ThinkingProtocol.id == protocol_id))
        protocol = result.scalar_one_or_none()
        if not protocol:
            raise ValueError("Loop protocol not found")
        if protocol.type != "loop":
            raise ValueError(f"Protocol '{protocol.name}' is type '{protocol.type}', expected 'loop'")

        # Create chat session for autonomous work
        model_ids = []
        if agent.agent_models:
            model_ids = [str(am.model_config_id) for am in sorted(agent.agent_models, key=lambda x: x.priority)]
        elif agent.model_id:
            model_ids = [str(agent.model_id)]

        # Validate and remap stale model_ids
        if model_ids:
            from app.api.chat import _validate_and_remap_model_ids
            model_ids = await _validate_and_remap_model_ids(model_ids, db)

        # Fallback to base role model
        if not model_ids:
            from app.services.model_role_service import resolve_model_for_role
            base_model = await resolve_model_for_role(db, "base")
            if base_model:
                model_ids = [str(base_model.id)]

        if not model_ids:
            raise ValueError("Agent has no models configured and no base model available")

        chat_session = ChatSession(
            title=f"🔄 Autonomous: {agent.name} — {protocol.name}",
            model_ids=model_ids,
            agent_id=agent_id,
            user_id=user_id,
            multi_model=False,
            system_prompt="",
            temperature=agent.temperature,
        )
        db.add(chat_session)
        await db.flush()

        # Create autonomous run record
        run = AutonomousRun(
            agent_id=agent_id,
            session_id=chat_session.id,
            mode=mode,
            max_cycles=max_cycles if mode == "cycles" else None,
            loop_protocol_id=protocol_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()
        await db.refresh(run)

        # Update agent status
        agent.status = "running"
        agent.last_run_at = datetime.now(timezone.utc)
        await db.flush()

        run_id = str(run.id)
        agent_id_str = str(agent_id)

        await db.commit()

    # Launch background task
    task = asyncio.create_task(
        _run_autonomous_loop(run_id, agent_id_str),
        name=f"autonomous-{run_id}",
    )
    active_runs[run_id] = task

    await syslog_bg("info", f"Autonomous run started: {run_id} (mode={mode}, max_cycles={max_cycles})",
                     source="autonomous", metadata={"run_id": run_id, "agent_id": agent_id_str})

    # Return fresh run from new session
    async with async_session() as db:
        result = await db.execute(select(AutonomousRun).where(AutonomousRun.id == uuid.UUID(run_id)))
        return result.scalar_one()


async def stop_autonomous_run(run_id: str) -> AutonomousRun:
    """Stop an active autonomous run."""
    task = active_runs.get(run_id)
    if task and not task.done():
        task.cancel()

    async with async_session() as db:
        result = await db.execute(
            select(AutonomousRun)
            .where(AutonomousRun.id == uuid.UUID(run_id))
            .with_for_update()
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError("Autonomous run not found")

        if run.status == "running":
            run.status = "stopped"
            run.completed_at = datetime.now(timezone.utc)
            # Reset agent status
            result2 = await db.execute(
                select(Agent)
                .where(Agent.id == run.agent_id)
                .with_for_update()
            )
            agent = result2.scalar_one_or_none()
            if agent:
                agent.status = "idle"
            await db.commit()

        active_runs.pop(run_id, None)
        await db.refresh(run)
        return run


async def get_active_run_for_agent(agent_id: uuid.UUID) -> AutonomousRun | None:
    """Get the currently running autonomous run for an agent, if any."""
    async with async_session() as db:
        result = await db.execute(
            select(AutonomousRun).where(
                AutonomousRun.agent_id == agent_id,
                AutonomousRun.status == "running",
            ).order_by(AutonomousRun.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()


# ── The main loop ──────────────────────────────────────────

async def _run_autonomous_loop(run_id: str, agent_id_str: str):
    """Background task: runs the autonomous cycle loop."""
    settings = get_settings()

    try:
        while True:
            # Open a fresh DB session per cycle
            async with async_session() as db:
                # Load run
                result = await db.execute(
                    select(AutonomousRun)
                    .where(AutonomousRun.id == uuid.UUID(run_id))
                )
                run = result.scalar_one_or_none()
                if not run or run.status != "running":
                    break

                # Load agent with relationships eagerly loaded
                result = await db.execute(
                    select(Agent).where(Agent.id == run.agent_id)
                    .options(
                        selectinload(Agent.agent_models),
                        selectinload(Agent.agent_protocols).selectinload(AgentProtocol.protocol),
                    )
                )
                agent = result.scalar_one_or_none()
                if not agent or agent.status not in ("running",):
                    run.status = "stopped"
                    run.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    break

                # Check max cycles
                if run.mode == "cycles" and run.max_cycles and run.completed_cycles >= run.max_cycles:
                    run.status = "completed"
                    run.completed_at = datetime.now(timezone.utc)
                    agent.status = "idle"
                    await db.commit()
                    break

                # Execute one cycle
                try:
                    should_stop = await _execute_cycle(db, run, agent)
                    await db.commit()

                    if should_stop:
                        break
                except asyncio.CancelledError:
                    # Graceful cancel
                    run.status = "stopped"
                    run.completed_at = datetime.now(timezone.utc)
                    agent.status = "idle"
                    await db.commit()
                    raise
                except Exception as e:
                    import traceback
                    error_tb = traceback.format_exc()
                    print(f"[AUTONOMOUS ERROR] Cycle error for run {run_id}: {e}\n{error_tb}")
                    run.status = "error"
                    run.error_message = f"{e}\n{error_tb}"[:2000]
                    run.completed_at = datetime.now(timezone.utc)
                    agent.status = "error"

                    # Log AgentError for unexpected cycle failures
                    try:
                        from app.api.chat import create_agent_error
                        await create_agent_error(
                            db, agent.id,
                            error_type="unknown",
                            message=f"Autonomous cycle {run.completed_cycles + 1} failed: {e}",
                            source="autonomous",
                            context={"run_id": run_id, "cycle": run.completed_cycles + 1, "traceback": error_tb[:1000]},
                        )
                    except Exception:
                        pass

                    await db.commit()
                    await syslog_bg("error", f"Autonomous cycle error: {e}\n{error_tb}",
                                    source="autonomous",
                                    metadata={"run_id": run_id, "cycle": run.completed_cycles})
                    break

            # Brief pause between cycles (avoid tight loops)
            await asyncio.sleep(2)

    except asyncio.CancelledError:
        pass
    except Exception as e:
        import traceback
        print(f"[AUTONOMOUS FATAL] run {run_id}: {e}\n{traceback.format_exc()}")
        await syslog_bg("error", f"Autonomous run fatal error: {e}\n{traceback.format_exc()}",
                        source="autonomous", metadata={"run_id": run_id})
    finally:
        active_runs.pop(run_id, None)

        # Ensure agent is set to idle if run completes
        try:
            async with async_session() as db:
                result = await db.execute(select(AutonomousRun).where(AutonomousRun.id == uuid.UUID(run_id)))
                run = result.scalar_one_or_none()
                if run and run.status == "running":
                    run.status = "completed"
                    run.completed_at = datetime.now(timezone.utc)

                result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id_str)))
                agent = result.scalar_one_or_none()
                if agent and agent.status == "running":
                    agent.status = "idle"
                await db.commit()
        except Exception:
            pass

        await syslog_bg("info", f"Autonomous run ended: {run_id}",
                        source="autonomous", metadata={"run_id": run_id})


async def _execute_cycle(db: AsyncSession, run: AutonomousRun, agent: Agent) -> bool:
    """
    Execute a single autonomous cycle.

    Returns True if the agent decided to stop (<<<STOP>>>), False otherwise.
    """
    settings = get_settings()
    cycle_num = run.completed_cycles + 1
    cycle_start = time.monotonic()

    # ── Thinking tracker ──
    tracker = ThinkingTracker(
        db, agent.id, run.session_id,
        f"[Autonomous cycle {cycle_num}]",
    )
    await tracker.start()

    try:
        # ── Step 1: Load agent config ──
        tracker.start_step_timer()
        from app.api.agent_files import read_agent_config, read_agent_settings
        agent_config = read_agent_config(agent.name)
        agent_settings = read_agent_settings(agent.name)

        gen_params = GenerationParams(temperature=agent.temperature)
        if agent_settings:
            gen_params = GenerationParams(
                temperature=agent_settings.get("temperature", agent.temperature),
                top_p=agent_settings.get("top_p", 0.9),
                top_k=agent_settings.get("top_k", 40),
                max_tokens=agent_settings.get("max_tokens", 2048),
                num_ctx=agent_settings.get("num_ctx", 32768),
                repeat_penalty=agent_settings.get("repeat_penalty", 1.1),
                num_predict=agent_settings.get("num_predict", -1),
                stop=agent_settings.get("stop") or None,
                num_thread=agent_settings.get("num_thread", 8),
                num_gpu=agent_settings.get("num_gpu", 1),
            )

        await tracker.step(
            "config_load", "Load agent configuration",
            input_data={"agent_name": agent.name, "cycle": cycle_num},
            output_data={"temperature": gen_params.temperature},
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 2: Load context ──
        tracker.start_step_timer()
        from app.api.chat import _load_agent_protocols, _load_agent_skills
        from app.api.agent_beliefs import read_beliefs
        from app.api.agent_aspirations import read_aspirations

        agent_protocols = await _load_agent_protocols(agent, db)
        agent_skills = await _load_agent_skills(agent.id, db, agent=agent)
        agent_beliefs = read_beliefs(agent.name)
        agent_aspirations = read_aspirations(agent.name)

        # Load assigned projects with their pending tasks
        assigned_projects = _load_assigned_projects(str(agent.id))

        # Load agent's persistent tasks from DB and populate cycle_state.todo_list
        from app.models.task import Task as TaskModel
        task_result = await db.execute(
            select(TaskModel)
            .where(TaskModel.agent_id == agent.id,
                   TaskModel.status.in_(["pending", "running"]))
            .order_by(TaskModel.created_at)
        )
        agent_db_tasks = task_result.scalars().all()
        if agent_db_tasks and not (run.cycle_state or {}).get("todo_list"):
            # Seed the cycle todo_list from DB tasks
            run.cycle_state = run.cycle_state or {}
            seeded_todo = []
            seeded_map = run.cycle_state.get("todo_task_map", {})
            for idx, t in enumerate(agent_db_tasks, 1):
                todo_status = _TASK_STATUS_TO_TODO.get(t.status, "pending")
                seeded_todo.append({"id": idx, "task": t.title, "status": todo_status})
                seeded_map[str(idx)] = str(t.id)
            run.cycle_state["todo_list"] = seeded_todo
            run.cycle_state["todo_task_map"] = seeded_map

        # Load the loop protocol
        result = await db.execute(select(ThinkingProtocol).where(ThinkingProtocol.id == run.loop_protocol_id))
        loop_protocol = result.scalar_one_or_none()
        protocol_dict = {
            "id": str(loop_protocol.id),
            "name": loop_protocol.name,
            "description": loop_protocol.description or "",
            "type": loop_protocol.type,
            "steps": loop_protocol.steps or [],
        } if loop_protocol else {"name": "Default Autonomous", "steps": [], "type": "loop", "description": ""}

        await tracker.step(
            "context_load", "Load protocols, skills, beliefs, aspirations, projects",
            output_data={
                "protocols_count": len(agent_protocols),
                "skills_count": len(agent_skills),
                "has_beliefs": bool(agent_beliefs),
                "has_aspirations": bool(agent_aspirations),
                "assigned_projects_count": len(assigned_projects),
                "loop_protocol": protocol_dict.get("name"),
            },
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 3: Build system prompt ──
        tracker.start_step_timer()
        cycle_state = run.cycle_state or {}

        system_prompt = format_loop_protocol_prompt(
            protocol=protocol_dict,
            cycle_number=cycle_num,
            max_cycles=run.max_cycles,
            cycle_state=cycle_state,
            available_skills=agent_skills or None,
            beliefs=agent_beliefs,
            aspirations=agent_aspirations,
            agent_name=agent.name,
            assigned_projects=assigned_projects or None,
        )

        await tracker.step(
            "prompt_build", "Build autonomous cycle prompt",
            input_data={"cycle": cycle_num, "has_previous_state": bool(cycle_state)},
            output_data={
                "prompt_length": len(system_prompt),
                "prompt_preview": system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt,
            },
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 4: Build history ──
        tracker.start_step_timer()

        # For autonomous work, keep a rolling window of recent cycle outputs
        history = [{"role": "system", "content": system_prompt}]

        # Load recent messages from the session (last N messages for context)
        from sqlalchemy.orm import selectinload
        result = await db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(ChatSession.id == run.session_id)
        )
        session = result.scalar_one_or_none()
        if session and session.messages:
            # Keep last 10 messages for context
            recent = sorted(session.messages, key=lambda m: m.created_at)[-10:]
            for msg in recent:
                if msg.role != "system":
                    history.append({"role": msg.role, "content": msg.content})

        # Add the autonomous cycle prompt as user message
        cycle_prompt = f"Execute cycle {cycle_num}. Analyze your current state and decide what to do."

        # Always prioritize project work first
        if assigned_projects:
            project_names = [p.get("name", "") for p in assigned_projects]
            has_project_tasks = any(p.get("pending_tasks") for p in assigned_projects)
            if has_project_tasks:
                cycle_prompt += (
                    f"\n\n🚨 **PROJECT WORK IS YOUR TOP PRIORITY.** You have assigned projects: {', '.join(project_names)}. "
                    "Work on pending project tasks FIRST. Use `project_file_write` skill to save code to project files. "
                    "Do NOT just write code in your response — it won't be saved. You MUST use the skill."
                )

        if cycle_state.get("todo_list"):
            pending = [t for t in cycle_state["todo_list"] if t.get("status") in ("pending", "in_progress")]
            if pending:
                cycle_prompt += f" You have {len(pending)} pending tasks in your todo list."

        # Self-thinking mode: suggest task generation when idle
        if agent.self_thinking:
            has_pending_todo = cycle_state.get("todo_list") and any(
                t.get("status") in ("pending", "in_progress") for t in cycle_state["todo_list"]
            )
            has_project_tasks = assigned_projects and any(
                p.get("pending_tasks") for p in assigned_projects
            )
            if not has_pending_todo and not has_project_tasks:
                cycle_prompt += (
                    "\n\n🧠 **Self-Thinking Mode Active:** You have no pending tasks. "
                    "Reflect on your mission, dreams, goals, and assigned projects. "
                    "Generate new low-priority tasks aligned with your aspirations — "
                    "think about what you could learn, explore, improve, or create. "
                    "Add them to your todo list with <<<TODO>>> markers."
                )
            elif not has_pending_todo and has_project_tasks:
                cycle_prompt += (
                    "\n\n🧠 **Self-Thinking Mode:** Your personal todo list is empty, "
                    "but you have project tasks waiting. Pick the highest-priority project task "
                    "to work on. Use `project_file_write` skill to save your code!"
                )

        history.append({"role": "user", "content": cycle_prompt})

        await tracker.step(
            "history_build", "Build conversation history",
            output_data={"history_messages": len(history), "total_chars": sum(len(m["content"]) for m in history)},
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 5: LLM call ──
        tracker.start_step_timer()

        model_ids = []
        if agent.agent_models:
            model_ids = [str(am.model_config_id) for am in sorted(agent.agent_models, key=lambda x: x.priority)]
        elif agent.model_id:
            model_ids = [str(agent.model_id)]

        if not model_ids:
            raise ValueError("No models configured for agent")

        from app.api.chat import _resolve_model, _chat_with_model
        model_id = model_ids[0]
        provider, base_url, model_name, api_key = await _resolve_model(model_id, db)

        llm_resp = await _chat_with_model(
            provider, base_url, model_name, api_key,
            history, gen_params,
        )

        llm_duration_ms = tracker.elapsed_step_ms()

        await tracker.step(
            "llm_call", f"LLM inference ({model_name})",
            input_data={"model": model_name, "history_messages": len(history)},
            output_data={
                "response_length": len(llm_resp.content),
                "response_preview": llm_resp.content[:500],
                "total_tokens": llm_resp.total_tokens,
                "prompt_tokens": getattr(llm_resp, "prompt_tokens", 0),
                "completion_tokens": getattr(llm_resp, "completion_tokens", 0),
            },
            duration_ms=llm_duration_ms,
        )

        llm_content = llm_resp.content
        total_tokens = llm_resp.total_tokens
        llm_calls = 1

        # ── Step 6: Parse response ──
        tracker.start_step_timer()

        new_todo = parse_todo_list(llm_content)
        skill_calls = parse_skill_invocations(llm_content)
        stop_reason = parse_stop(llm_content)

        # ── Fallback: auto-extract code from markdown if agent forgot SKILL markers ──
        if not skill_calls and assigned_projects:
            fallback_calls = _extract_code_fallback(llm_content, assigned_projects)
            if fallback_calls:
                skill_calls = fallback_calls
                logger.info(
                    "Auto-extracted %d code block(s) from markdown as fallback skill call(s)",
                    len(fallback_calls),
                )

        await tracker.step(
            "response_parse", "Parse autonomous cycle response",
            output_data={
                "todo_found": bool(new_todo),
                "skill_calls_found": len(skill_calls) if skill_calls else 0,
                "stop_requested": stop_reason is not None,
                "stop_reason": stop_reason,
            },
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 7: Execute skills ──
        if skill_calls and agent_skills:
            tracker.start_step_timer()

            from app.api.chat import _execute_skill, create_agent_error
            skill_results = []
            errors_in_cycle = []
            for call in skill_calls:
                result_val = await _execute_skill(call["skill_name"], call["args"], agent_skills)

                # ── Error handling: log AgentError and project log ──
                if "error" in result_val:
                    err_msg = result_val["error"]
                    is_not_found = "not found" in err_msg.lower()
                    error_type = "skill_not_found" if is_not_found else "skill_exec_error"

                    # Determine project context for logging
                    project_slug = None
                    if assigned_projects:
                        # Pick the first project the agent is lead of, or first assigned
                        for p in assigned_projects:
                            if p.get("is_lead"):
                                project_slug = p.get("slug")
                                break
                        if not project_slug and assigned_projects:
                            project_slug = assigned_projects[0].get("slug")

                    ctx = {
                        "skill_name": call["skill_name"],
                        "args": call["args"],
                        "cycle": cycle_num,
                        "run_id": str(run.id),
                    }
                    if project_slug:
                        ctx["project_slug"] = project_slug

                    agent_err = await create_agent_error(
                        db, agent.id,
                        error_type=error_type,
                        message=err_msg,
                        source="autonomous",
                        context=ctx,
                    )
                    errors_in_cycle.append({"skill": call["skill_name"], "error": err_msg, "type": error_type})

                    # Log to project log if project context exists
                    if project_slug:
                        try:
                            from pathlib import Path
                            from app.api.projects import _add_log
                            proj_dir = Path(settings.PROJECTS_DIR) / project_slug
                            if proj_dir.exists():
                                _add_log(proj_dir, "error",
                                         f"Agent '{agent.name}' skill error: {err_msg}",
                                         source="agent")
                        except Exception:
                            pass  # Don't fail the cycle on logging errors

                skill_results.append({
                    "skill": call["skill_name"],
                    "args": call["args"],
                    "result": result_val,
                })

            await tracker.step(
                "skill_exec", f"Execute {len(skill_results)} skill(s)",
                input_data={"skills": [c["skill_name"] for c in skill_calls]},
                output_data={
                    "results": [{"skill": sr["skill"], "has_error": "error" in sr["result"]} for sr in skill_results],
                    "errors_logged": len(errors_in_cycle),
                },
                duration_ms=tracker.elapsed_step_ms(),
            )

            # Follow-up LLM call with skill results
            tracker.start_step_timer()
            skill_feedback = "\n\n".join(
                f"**Skill `{sr['skill']}` result:**\n```json\n{json.dumps(sr['result'], ensure_ascii=False, indent=2)}\n```"
                for sr in skill_results
            )

            # If there were errors, ask the model to handle them intelligently
            error_guidance = ""
            if errors_in_cycle:
                not_found = [e for e in errors_in_cycle if e["type"] == "skill_not_found"]
                exec_errors = [e for e in errors_in_cycle if e["type"] == "skill_exec_error"]
                if not_found:
                    error_guidance += (
                        "\n\n⚠️ **Skill(s) not found:** "
                        + ", ".join(f"`{e['skill']}`" for e in not_found)
                        + ". These skills are not available. Try to accomplish the same goal "
                        "using the skills that ARE available, or describe what you need done in plain text."
                    )
                if exec_errors:
                    error_guidance += (
                        "\n\n⚠️ **Execution error(s):** "
                        + "; ".join(f"`{e['skill']}`: {e['error']}" for e in exec_errors)
                        + ". Analyze the error and decide: retry with different parameters, "
                        "use an alternative approach, or skip and continue."
                    )

            follow_up = (
                f"Skills executed. Results:\n\n{skill_feedback}\n\n"
                f"{error_guidance}\n"
                "Continue with your cycle and summarize what you accomplished."
            )
            history.append({"role": "assistant", "content": llm_content})
            history.append({"role": "user", "content": follow_up})

            try:
                follow_resp = await _chat_with_model(
                    provider, base_url, model_name, api_key,
                    history, gen_params,
                )
                llm_content = llm_content + "\n\n---\n\n" + follow_resp.content
                total_tokens += follow_resp.total_tokens
                llm_calls += 1

                # Re-parse for todo/stop from follow-up
                new_todo2 = parse_todo_list(follow_resp.content)
                if new_todo2:
                    new_todo = new_todo2
                stop2 = parse_stop(follow_resp.content)
                if stop2 is not None:
                    stop_reason = stop2

                await tracker.step(
                    "follow_up_call", f"Follow-up after skills ({model_name})",
                    output_data={
                        "response_length": len(follow_resp.content),
                        "tokens": follow_resp.total_tokens,
                    },
                    duration_ms=tracker.elapsed_step_ms(),
                )
            except Exception as e:
                await tracker.step(
                    "follow_up_call", "Follow-up after skills",
                    status="error",
                    error_message=str(e),
                    duration_ms=tracker.elapsed_step_ms(),
                )

        # ── Step 8: Update state ──
        tracker.start_step_timer()

        # Save messages to chat session
        user_msg = ChatMessage(
            session_id=run.session_id,
            role="user",
            content=cycle_prompt,
        )
        db.add(user_msg)
        await db.flush()

        assistant_msg = ChatMessage(
            session_id=run.session_id,
            role="assistant",
            content=llm_content,
            model_name=model_name,
            total_tokens=total_tokens,
            duration_ms=int((time.monotonic() - cycle_start) * 1000),
        )
        db.add(assistant_msg)
        await db.flush()

        # Update cycle state
        effective_todo = new_todo or cycle_state.get("todo_list")
        new_cycle_state = {
            "last_output": llm_content[:3000],
            "todo_list": effective_todo,
            "cycle_summary": _extract_summary(llm_content),
            "todo_task_map": cycle_state.get("todo_task_map", {}),
        }

        # ── Sync TODO items → persistent Tasks table ──
        if effective_todo:
            try:
                updated_map = await sync_todos_to_tasks(
                    db, agent.id, effective_todo,
                    todo_task_map=new_cycle_state.get("todo_task_map"),
                )
                new_cycle_state["todo_task_map"] = updated_map
            except Exception as e:
                print(f"[AUTONOMOUS] Warning: failed to sync todos to tasks: {e}")

        run.cycle_state = new_cycle_state
        run.completed_cycles = cycle_num
        run.total_tokens = (run.total_tokens or 0) + total_tokens
        run.total_llm_calls = (run.total_llm_calls or 0) + llm_calls
        run.total_duration_ms = int((time.monotonic() - cycle_start) * 1000) + (run.total_duration_ms or 0)

        await tracker.step(
            "state_update", "Update autonomous run state",
            output_data={
                "cycle_completed": cycle_num,
                "has_todo": bool(new_cycle_state.get("todo_list")),
                "stop_requested": stop_reason is not None,
            },
            duration_ms=tracker.elapsed_step_ms(),
        )

        # Complete thinking log
        await tracker.complete(
            llm_content,
            message_id=assistant_msg.id,
            model_name=model_name,
            total_tokens=total_tokens,
            prompt_tokens=getattr(llm_resp, "prompt_tokens", 0),
            completion_tokens=getattr(llm_resp, "completion_tokens", 0),
            llm_calls_count=llm_calls,
        )

        # Check stop conditions
        if stop_reason is not None:
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = f"Agent stopped: {stop_reason}" if stop_reason else None
            agent.status = "idle"
            await syslog_bg("info", f"Autonomous run self-stopped: {stop_reason}",
                            source="autonomous",
                            metadata={"run_id": str(run.id), "cycle": cycle_num, "reason": stop_reason})
            return True

        if run.mode == "cycles" and run.max_cycles and cycle_num >= run.max_cycles:
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            agent.status = "idle"
            return True

        return False

    except Exception as e:
        await tracker.fail(str(e))
        raise


def _extract_summary(text: str) -> str:
    """Extract the last paragraph as a cycle summary."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if paragraphs:
        return paragraphs[-1][:1000]
    return text[:1000]


# ── Regex for fenced code blocks: ```lang\n...\n``` ──
_CODE_BLOCK_RE = re.compile(
    r"```(\w*)\n(.*?)```",
    re.DOTALL,
)

# Map language hints to file extensions
_LANG_TO_EXT = {
    "python": ".py", "py": ".py", "python3": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "html": ".html", "css": ".css",
    "java": ".java", "c": ".c", "cpp": ".cpp",
    "go": ".go", "rust": ".rs", "ruby": ".rb",
    "sh": ".sh", "bash": ".sh", "shell": ".sh",
    "sql": ".sql", "json": ".json", "yaml": ".yml",
}


def _extract_code_fallback(
    llm_content: str,
    assigned_projects: list[dict],
) -> list[dict]:
    """
    Fallback: when the LLM wrote code in markdown blocks but forgot to use
    <<<SKILL:project_file_write>>> markers, auto-construct skill calls.

    Only fires if the agent has assigned projects with pending tasks.
    Returns list of synthetic skill call dicts compatible with parse_skill_invocations format.
    """
    # Find the lead project (or first one)
    target_project = None
    for p in (assigned_projects or []):
        if p.get("is_lead") and p.get("pending_tasks"):
            target_project = p
            break
    if not target_project:
        for p in (assigned_projects or []):
            if p.get("pending_tasks"):
                target_project = p
                break
    if not target_project:
        return []

    slug = target_project.get("slug", "")
    if not slug:
        return []

    # Find code blocks in the response
    blocks = _CODE_BLOCK_RE.findall(llm_content)
    if not blocks:
        return []

    # Filter: only substantial code (>20 chars, not json/text/etc)
    skip_langs = {"json", "text", "txt", "markdown", "md", ""}
    calls = []
    for idx, (lang, code) in enumerate(blocks):
        lang_lower = lang.strip().lower()
        code_stripped = code.strip()

        # Skip tiny blocks, json snippets, and non-code
        if len(code_stripped) < 30:
            continue
        if lang_lower in skip_langs and not any(kw in code_stripped[:100] for kw in ("def ", "class ", "import ", "print(", "function ", "const ", "let ", "var ")):
            continue

        # Determine filename
        ext = _LANG_TO_EXT.get(lang_lower, ".py")

        # Try to extract filename from a comment on the first line like "# hello_world.py"
        first_line = code_stripped.split("\n")[0].strip()
        extracted_name = None
        for prefix in ("# ", "// ", "-- ", "/* "):
            if first_line.startswith(prefix):
                candidate = first_line[len(prefix):].strip()
                if "." in candidate and len(candidate) < 60 and " " not in candidate:
                    extracted_name = candidate
                    break

        if extracted_name:
            path = extracted_name
        elif len(calls) == 0:
            path = f"solution{ext}"
        else:
            path = f"solution_{idx}{ext}"

        calls.append({
            "skill_name": "project_file_write",
            "args": {
                "project_slug": slug,
                "path": path,
                "content": code_stripped,
            },
            "raw_match": f"[auto-extracted from markdown code block #{idx + 1}]",
        })

    return calls


def _load_assigned_projects(agent_id: str) -> list[dict]:
    """
    Load projects assigned to agent (file-based).
    Returns list of project dicts with pending_tasks included.
    """
    from pathlib import Path
    from app.config import get_settings
    import json as _json

    settings = get_settings()
    base = Path(settings.PROJECTS_DIR)
    if not base.exists():
        return []

    projects = []
    for entry in sorted(base.iterdir(), key=lambda e: e.name.lower()):
        if not entry.is_dir():
            continue
        pj = entry / "project.json"
        if not pj.exists():
            continue
        try:
            config = _json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue

        if config.get("status") in ("archived", "paused"):
            continue

        access = config.get("access_level", "full")
        allowed = config.get("allowed_agent_ids", [])
        lead = config.get("lead_agent_id")

        if access == "full" or agent_id in allowed or lead == agent_id:
            proj = {
                "name": config.get("name", ""),
                "slug": config.get("slug", entry.name),
                "description": config.get("description", ""),
                "goals": config.get("goals", ""),
                "tech_stack": config.get("tech_stack", []),
                "status": config.get("status", "active"),
                "is_lead": (lead == agent_id),
            }

            # Load tasks
            tasks_file = entry / "tasks.json"
            tasks = []
            if tasks_file.exists():
                try:
                    tasks = _json.loads(tasks_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Compute task stats
            proj["task_stats"] = {
                "total": len(tasks),
                "backlog": sum(1 for t in tasks if t.get("status") == "backlog"),
                "todo": sum(1 for t in tasks if t.get("status") == "todo"),
                "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
                "review": sum(1 for t in tasks if t.get("status") == "review"),
                "done": sum(1 for t in tasks if t.get("status") == "done"),
            }

            # Include pending tasks (not done, not cancelled)
            pending = [t for t in tasks if t.get("status") not in ("done", "cancelled")]
            # Sort by priority
            priority_order = {"highest": 0, "high": 1, "medium": 2, "low": 3, "lowest": 4}
            pending.sort(key=lambda t: priority_order.get(t.get("priority", "medium"), 2))
            proj["pending_tasks"] = pending

            projects.append(proj)

    return projects
