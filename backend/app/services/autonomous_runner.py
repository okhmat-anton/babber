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

from app.database import get_mongodb
from app.config import get_settings
from app.mongodb.models import (
    MongoChatSession, MongoChatMessage, MongoAutonomousRun, MongoTask,
)
from app.mongodb.services import (
    AgentService, AgentModelService, AgentProtocolService,
    ModelConfigService, ChatSessionService, ChatMessageService,
    AutonomousRunService, ThinkingProtocolService, TaskService,
)
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
from app.services.log_service import syslog_bg, agent_log_bg
from app.services.todo_sync_service import sync_todos_to_tasks

# ── Global registry of active runs ──
# Maps run_id -> asyncio.Task
active_runs: dict[str, asyncio.Task] = {}


async def cleanup_orphaned_runs() -> int:
    """
    On server startup, find any autonomous runs stuck in 'running' status
    (orphaned by a previous server restart) and mark them as 'stopped'.
    """
    count = 0
    db = get_mongodb()
    run_svc = AutonomousRunService(db)
    agent_svc = AgentService(db)

    orphaned = await run_svc.get_all(filter={"status": "running"}, limit=500)
    for run in orphaned:
        await run_svc.update(run.id, {
            "status": "stopped",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error_message": "Orphaned: server restarted during active run",
        })
        agent = await agent_svc.get_by_id(run.agent_id)
        if agent and agent.status == "running":
            await agent_svc.update(agent.id, {"status": "idle"})
        count += 1
    if count:
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


# (sync_todos_to_tasks moved to todo_sync_service.py)


async def start_autonomous_run(
    agent_id: uuid.UUID,
    mode: str = "continuous",
    max_cycles: int | None = None,
    loop_protocol_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> MongoAutonomousRun:
    """Create an autonomous run record and launch the background loop."""
    db = get_mongodb()
    agent_svc = AgentService(db)
    agent_model_svc = AgentModelService(db)
    proto_svc = ThinkingProtocolService(db)
    ap_svc = AgentProtocolService(db)

    agent_id_str = str(agent_id)
    agent = await agent_svc.get_by_id(agent_id_str)
    if not agent:
        raise ValueError("Agent not found")

    # Resolve loop protocol
    protocol_id = str(loop_protocol_id) if loop_protocol_id else None
    if not protocol_id:
        agent_protos = await ap_svc.get_by_agent(agent_id_str)
        for ap in agent_protos:
            p = await proto_svc.get_by_id(ap.protocol_id)
            if p and p.type == "loop":
                protocol_id = str(p.id)
                break

    if not protocol_id:
        raise ValueError("No loop protocol found. Assign a loop protocol to the agent first.")

    protocol = await proto_svc.get_by_id(protocol_id)
    if not protocol:
        raise ValueError("Loop protocol not found")
    if protocol.type != "loop":
        raise ValueError(f"Protocol '{protocol.name}' is type '{protocol.type}', expected 'loop'")

    # Resolve models
    model_ids = []
    agent_models = await agent_model_svc.get_by_agent(agent_id_str)
    if agent_models:
        model_ids = [str(am.model_config_id) for am in sorted(agent_models, key=lambda x: x.priority)]
    elif agent.model_id:
        model_ids = [str(agent.model_id)]

    if model_ids:
        from app.api.chat import _validate_and_remap_model_ids
        model_ids = await _validate_and_remap_model_ids(model_ids, db)

    if not model_ids:
        from app.services.model_role_service import resolve_model_for_role
        base_model = await resolve_model_for_role(db, "base")
        if base_model:
            model_ids = [str(base_model.id)]

    if not model_ids:
        raise ValueError("Agent has no models configured and no base model available")

    # Find or create chat session (reuse existing project_task / agent chats)
    sess_svc = ChatSessionService(db)
    chat_session = None

    # Check if agent has assigned projects → use project_task chat
    assigned_projects = _load_assigned_projects(agent_id_str)
    primary_project = None
    if assigned_projects:
        # Prefer the project where agent is lead, or the first one
        for p in assigned_projects:
            if p.get("is_lead"):
                primary_project = p
                break
        if not primary_project:
            primary_project = assigned_projects[0]

    if primary_project:
        project_slug = primary_project.get("slug")
        # Look for existing project_task chat for this project + agent
        existing = await sess_svc.find_one({
            "chat_type": "project_task",
            "project_slug": project_slug,
            "agent_id": agent_id_str,
        })
        if not existing:
            # Also look for project_task chat for this project without specific agent
            existing = await sess_svc.find_one({
                "chat_type": "project_task",
                "project_slug": project_slug,
            })
        if existing:
            chat_session = existing
            # Update model_ids if needed
            await sess_svc.update(chat_session.id, {"model_ids": model_ids})
    else:
        # No projects — look for existing agent chat
        existing = await sess_svc.find_one({
            "chat_type": "agent",
            "agent_id": agent_id_str,
        })
        if existing:
            chat_session = existing
            await sess_svc.update(chat_session.id, {"model_ids": model_ids})

    if not chat_session:
        # Create new session with correct chat_type
        if primary_project:
            chat_session = MongoChatSession(
                title=primary_project.get("name") or primary_project.get("slug", "Project"),
                model_ids=model_ids,
                agent_id=agent_id_str,
                agent_ids=[agent_id_str],
                user_id=str(user_id) if user_id else None,
                multi_model=False,
                system_prompt="",
                temperature=agent.temperature,
                chat_type="project_task",
                project_slug=primary_project.get("slug"),
            )
        else:
            chat_session = MongoChatSession(
                title=agent.name,
                model_ids=model_ids,
                agent_id=agent_id_str,
                agent_ids=[agent_id_str],
                user_id=str(user_id) if user_id else None,
                multi_model=False,
                system_prompt="",
                temperature=agent.temperature,
                chat_type="agent",
            )
        chat_session = await sess_svc.create(chat_session)

    # Create autonomous run
    run_svc = AutonomousRunService(db)
    run = MongoAutonomousRun(
        agent_id=agent_id_str,
        session_id=chat_session.id,
        mode=mode,
        max_cycles=max_cycles if mode == "cycles" else None,
        loop_protocol_id=protocol_id,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    run = await run_svc.create(run)

    # Update agent status
    await agent_svc.update(agent_id_str, {
        "status": "running",
        "last_run_at": datetime.now(timezone.utc).isoformat(),
    })

    run_id = str(run.id)

    # Launch background task
    task = asyncio.create_task(
        _run_autonomous_loop(run_id, agent_id_str),
        name=f"autonomous-{run_id}",
    )
    active_runs[run_id] = task

    await syslog_bg("info", f"Autonomous run started: {run_id} (mode={mode}, max_cycles={max_cycles})",
                     source="autonomous", metadata={"run_id": run_id, "agent_id": agent_id_str})
    await agent_log_bg(agent_id_str, "info", f"Autonomous run started (mode={mode}, max_cycles={max_cycles})",
                       metadata={"run_id": run_id, "mode": mode})

    return run


async def stop_autonomous_run(run_id: str) -> MongoAutonomousRun:
    """Stop an active autonomous run."""
    task = active_runs.get(run_id)
    if task and not task.done():
        task.cancel()

    db = get_mongodb()
    run_svc = AutonomousRunService(db)
    agent_svc = AgentService(db)

    run = await run_svc.get_by_id(run_id)
    if not run:
        raise ValueError("Autonomous run not found")

    if run.status == "running":
        await run_svc.update(run_id, {
            "status": "stopped",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        agent = await agent_svc.get_by_id(run.agent_id)
        if agent:
            await agent_svc.update(agent.id, {"status": "idle"})

    active_runs.pop(run_id, None)
    return await run_svc.get_by_id(run_id)


async def get_active_run_for_agent(agent_id: uuid.UUID) -> MongoAutonomousRun | None:
    """Get the currently running autonomous run for an agent, if any."""
    db = get_mongodb()
    run_svc = AutonomousRunService(db)
    return await run_svc.find_one({
        "agent_id": str(agent_id),
        "status": "running",
    })


# ── The main loop ──────────────────────────────────────────

async def _run_autonomous_loop(run_id: str, agent_id_str: str):
    """Background task: runs the autonomous cycle loop."""
    settings = get_settings()

    try:
        while True:
            db = get_mongodb()
            run_svc = AutonomousRunService(db)
            agent_svc = AgentService(db)

            run = await run_svc.get_by_id(run_id)
            if not run or run.status != "running":
                break

            agent = await agent_svc.get_by_id(run.agent_id)
            if not agent or agent.status not in ("running",):
                await run_svc.update(run_id, {
                    "status": "stopped",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                break

            # Check max cycles
            if run.mode == "cycles" and run.max_cycles and run.completed_cycles >= run.max_cycles:
                await run_svc.update(run_id, {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                await agent_svc.update(agent.id, {"status": "idle"})
                break

            # Execute one cycle
            try:
                should_stop = await _execute_cycle(db, run, agent)
                if should_stop:
                    break
            except asyncio.CancelledError:
                await run_svc.update(run_id, {
                    "status": "stopped",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                await agent_svc.update(agent.id, {"status": "idle"})
                raise
            except Exception as e:
                import traceback
                error_tb = traceback.format_exc()
                print(f"[AUTONOMOUS ERROR] Cycle error for run {run_id}: {e}\n{error_tb}")
                await run_svc.update(run_id, {
                    "status": "error",
                    "error_message": f"{e}\n{error_tb}"[:2000],
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                await agent_svc.update(agent.id, {"status": "error"})

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

                await syslog_bg("error", f"Autonomous cycle error: {e}\n{error_tb}",
                                source="autonomous",
                                metadata={"run_id": run_id, "cycle": run.completed_cycles})
                await agent_log_bg(agent_id_str, "error",
                                   f"Autonomous cycle {run.completed_cycles + 1} failed: {e}",
                                   metadata={"run_id": run_id})
                break

            # Brief pause between cycles
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
            db = get_mongodb()
            run_svc = AutonomousRunService(db)
            agent_svc = AgentService(db)
            run = await run_svc.get_by_id(run_id)
            if run and run.status == "running":
                await run_svc.update(run_id, {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
            agent = await agent_svc.get_by_id(agent_id_str)
            if agent and agent.status == "running":
                await agent_svc.update(agent.id, {"status": "idle"})
        except Exception:
            pass

        await syslog_bg("info", f"Autonomous run ended: {run_id}",
                        source="autonomous", metadata={"run_id": run_id})
        await agent_log_bg(agent_id_str, "info", f"Autonomous run ended",
                           metadata={"run_id": run_id})


async def _execute_cycle(db, run: MongoAutonomousRun, agent) -> bool:
    """
    Execute a single autonomous cycle.

    Returns True if the agent decided to stop (<<<STOP>>>), False otherwise.
    """
    settings = get_settings()
    cycle_num = run.completed_cycles + 1
    cycle_start = time.monotonic()

    run_svc = AutonomousRunService(db)
    agent_svc = AgentService(db)
    agent_model_svc = AgentModelService(db)
    msg_svc = ChatMessageService(db)
    task_svc = TaskService(db)

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
                max_tokens=agent_settings.get("max_tokens", 32768),
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

        agent_protocols = await _load_agent_protocols(str(agent.id), db)
        agent_skills = await _load_agent_skills(str(agent.id), db, agent=agent)
        agent_beliefs = read_beliefs(agent.name)
        agent_aspirations = read_aspirations(agent.name)

        # Load assigned projects with their pending tasks
        assigned_projects = _load_assigned_projects(str(agent.id))

        # Load agent's persistent tasks from DB and populate cycle_state.todo_list
        agent_db_tasks = await task_svc.get_all(
            filter={"agent_id": str(agent.id), "status": {"$in": ["pending", "running"]}, "is_user_task": {"$ne": True}},
            limit=500,
        )
        # Sort by created_at
        agent_db_tasks.sort(key=lambda t: t.created_at or "")
        cycle_state = run.cycle_state or {}
        if agent_db_tasks and not cycle_state.get("todo_list"):
            seeded_todo = []
            seeded_map = cycle_state.get("todo_task_map", {})
            for idx, t in enumerate(agent_db_tasks, 1):
                todo_status = _TASK_STATUS_TO_TODO.get(t.status, "pending")
                seeded_todo.append({"id": idx, "task": t.title, "status": todo_status})
                seeded_map[str(idx)] = str(t.id)
            cycle_state["todo_list"] = seeded_todo
            cycle_state["todo_task_map"] = seeded_map
            await run_svc.update(run.id, {"cycle_state": cycle_state})

        # ── Enrich thinking log title with current task ──
        _todo_list = cycle_state.get("todo_list", [])
        if _todo_list:
            _in_prog = [t for t in _todo_list if t.get("status") == "in_progress"]
            _chosen = _in_prog[0] if _in_prog else next((t for t in _todo_list if t.get("status") == "pending"), None)
            if _chosen and _chosen.get("task") and tracker.log:
                _task_label = _chosen["task"][:80]
                tracker.log.user_input = f"[Autonomous cycle {cycle_num}] {_task_label}"
                from app.services.thinking_log_service import ThinkingLogService
                await ThinkingLogService(db).update(tracker.log.id, {"user_input": tracker.log.user_input})

        # Load the loop protocol
        proto_svc = ThinkingProtocolService(db)
        loop_protocol = await proto_svc.get_by_id(run.loop_protocol_id) if run.loop_protocol_id else None
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
                "system_prompt": system_prompt,
            },
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 4: Build history ──
        tracker.start_step_timer()

        # For autonomous work, keep a rolling window of recent cycle outputs
        history = [{"role": "system", "content": system_prompt}]

        # Load recent messages from the session (last N messages for context)
        session_messages = await msg_svc.get_by_session(run.session_id)
        if session_messages:
            recent = sorted(session_messages, key=lambda m: m.created_at or "")[-10:]
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
            output_data={
                "history_messages": len(history),
                "total_chars": sum(len(m["content"]) for m in history),
                "messages": [
                    {"role": m["role"], "content_length": len(m["content"]), "content": m["content"]}
                    for m in history
                ],
            },
            duration_ms=tracker.elapsed_step_ms(),
        )

        # ── Step 5: LLM call ──
        tracker.start_step_timer()

        model_ids = []
        agent_models = await agent_model_svc.get_by_agent(str(agent.id))
        if agent_models:
            model_ids = [str(am.model_config_id) for am in sorted(agent_models, key=lambda x: x.priority)]
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
                "response": llm_resp.content,
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
                "todo_list": new_todo,
                "skill_calls_found": len(skill_calls) if skill_calls else 0,
                "skill_calls": [{"skill": c["skill_name"], "args": c["args"]} for c in skill_calls] if skill_calls else [],
                "stop_requested": stop_reason is not None,
                "stop_reason": stop_reason,
                "raw_response": llm_content,
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
                input_data={
                    "skills": [c["skill_name"] for c in skill_calls],
                    "args": [c["args"] for c in skill_calls],
                },
                output_data={
                    "results": [
                        {
                            "skill": sr["skill"],
                            "args": sr["args"],
                            "has_error": "error" in sr["result"],
                            "result": sr["result"],
                        }
                        for sr in skill_results
                    ],
                    "errors_logged": len(errors_in_cycle),
                    "errors": errors_in_cycle,
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
                        "response": follow_resp.content,
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
        user_msg = MongoChatMessage(
            session_id=run.session_id,
            role="user",
            content=cycle_prompt,
        )
        user_msg = await msg_svc.create(user_msg)

        assistant_msg = MongoChatMessage(
            session_id=run.session_id,
            role="assistant",
            content=llm_content,
            model_name=model_name,
            total_tokens=total_tokens,
            duration_ms=int((time.monotonic() - cycle_start) * 1000),
        )
        assistant_msg = await msg_svc.create(assistant_msg)

        # Update cycle state
        effective_todo = new_todo or cycle_state.get("todo_list")
        new_cycle_state = {
            "last_output": llm_content[:3000],
            "todo_list": effective_todo,
            "cycle_summary": _extract_summary(llm_content),
            "todo_task_map": cycle_state.get("todo_task_map", {}),
        }

        # ── Sync TODO items → persistent Tasks collection ──
        if effective_todo:
            try:
                updated_map = await sync_todos_to_tasks(
                    db, str(agent.id), effective_todo,
                    todo_task_map=new_cycle_state.get("todo_task_map"),
                )
                new_cycle_state["todo_task_map"] = updated_map
            except Exception as e:
                print(f"[AUTONOMOUS] Warning: failed to sync todos to tasks: {e}")

        await run_svc.update(run.id, {
            "cycle_state": new_cycle_state,
            "completed_cycles": cycle_num,
            "total_tokens": (run.total_tokens or 0) + total_tokens,
            "total_llm_calls": (run.total_llm_calls or 0) + llm_calls,
            "total_duration_ms": int((time.monotonic() - cycle_start) * 1000) + (run.total_duration_ms or 0),
        })

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

        # Log cycle completion for agent logs tab
        await agent_log_bg(
            str(agent.id), "info",
            f"Cycle {cycle_num} completed ({total_tokens} tokens, {llm_calls} LLM calls)",
            metadata={"run_id": str(run.id), "cycle": cycle_num, "tokens": total_tokens},
        )

        # Check stop conditions
        if stop_reason is not None:
            await run_svc.update(run.id, {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error_message": f"Agent stopped: {stop_reason}" if stop_reason else None,
            })
            await agent_svc.update(agent.id, {"status": "idle"})
            await syslog_bg("info", f"Autonomous run self-stopped: {stop_reason}",
                            source="autonomous",
                            metadata={"run_id": str(run.id), "cycle": cycle_num, "reason": stop_reason})
            return True

        if run.mode == "cycles" and run.max_cycles and cycle_num >= run.max_cycles:
            await run_svc.update(run.id, {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            await agent_svc.update(agent.id, {"status": "idle"})
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
