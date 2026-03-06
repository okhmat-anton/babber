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
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

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
        result = await db.execute(select(AutonomousRun).where(AutonomousRun.id == uuid.UUID(run_id)))
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError("Autonomous run not found")

        if run.status == "running":
            run.status = "stopped"
            run.completed_at = datetime.now(timezone.utc)
            # Reset agent status
            result2 = await db.execute(select(Agent).where(Agent.id == run.agent_id))
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
                result = await db.execute(select(AutonomousRun).where(AutonomousRun.id == uuid.UUID(run_id)))
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
        if cycle_state.get("todo_list"):
            pending = [t for t in cycle_state["todo_list"] if t.get("status") in ("pending", "in_progress")]
            if pending:
                cycle_prompt += f" You have {len(pending)} pending tasks."

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
                    "to work on, or generate supporting tasks aligned with project goals."
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

            from app.api.chat import _execute_skill
            skill_results = []
            for call in skill_calls:
                result_val = await _execute_skill(call["skill_name"], call["args"], agent_skills)
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
                },
                duration_ms=tracker.elapsed_step_ms(),
            )

            # Follow-up LLM call with skill results
            tracker.start_step_timer()
            skill_feedback = "\n\n".join(
                f"**Skill `{sr['skill']}` result:**\n```json\n{json.dumps(sr['result'], ensure_ascii=False, indent=2)}\n```"
                for sr in skill_results
            )
            follow_up = (
                f"Skills executed. Results:\n\n{skill_feedback}\n\n"
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
        new_cycle_state = {
            "last_output": llm_content[:3000],
            "todo_list": new_todo or cycle_state.get("todo_list"),
            "cycle_summary": _extract_summary(llm_content),
        }
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

        if config.get("status") in ("archived",):
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
