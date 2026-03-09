"""
AgentChatEngine — unified core for agent LLM interaction.

Used by:
  - Web chat (chat.py)
  - Telegram messenger (telegram_service.py)
  - Autonomous runner (autonomous_runner.py)
  - Future channels (Discord, API, etc.)

The engine handles:
  - Model resolution (agent models, role fallback, runtime Ollama URL)
  - Agent context loading (config, settings, protocols, skills, beliefs, aspirations)
  - Project/task context enrichment (via skills)
  - System prompt building (always includes beliefs, aspirations, skills, protocols)
  - Generation parameter construction
  - LLM calls (single model)
  - Response parsing (todo, delegation, skill invocations)
  - Skill execution loop with follow-up LLM calls
  - Response cleanup (strip protocol markers)
  - Thinking log recording (optional, for all channels)

Recommended entry point:
  - generate_full() — handles context, prompt, LLM, skills, thinking log
  - generate()      — lower-level, caller builds messages manually

Callers are responsible for:
  - Building conversation history (from their message store)
  - Persisting results (messages, protocol state, etc.)
  - Channel-specific logic (typing indicators, session management, etc.)
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.llm.base import Message, GenerationParams, LLMResponse
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.anthropic import AnthropicProvider
from app.llm.kieai import KieAIProvider
from app.mongodb.services import (
    AgentService, AgentModelService, AgentProtocolService,
    ModelConfigService, SkillService, AgentSkillService,
    ThinkingProtocolService, ModelRoleAssignmentService,
)
from app.services.protocol_executor import (
    build_agent_system_prompt,
    parse_skill_invocations,
    parse_todo_list,
    parse_delegate,
    parse_delegate_done,
)

logger = logging.getLogger(__name__)


# ── Data Classes ─────────────────────────────────────────────────────────


@dataclass
class AgentContext:
    """All loaded context for an agent."""
    agent: Any                          # MongoAgent object
    config: dict = field(default_factory=dict)         # from agent.json
    settings: dict = field(default_factory=dict)       # from settings.json
    gen_params: GenerationParams = field(default_factory=GenerationParams)
    protocols: list[dict] = field(default_factory=list)
    skills: list[dict] = field(default_factory=list)
    beliefs: Optional[str] = None       # beliefs text/dict
    aspirations: Optional[dict] = None  # {dreams, desires, goals}
    base_system_prompt: str = ""


@dataclass
class EngineResult:
    """Result of a chat engine generate() call."""
    content: str = ""            # clean response (markers stripped)
    raw_content: str = ""        # raw LLM output with all markers
    model_name: str = ""
    provider: str = ""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls_count: int = 0
    duration_ms: int = 0
    skill_results: list[dict] = field(default_factory=list)
    todo_list: Optional[list[dict]] = None
    delegate_to: Optional[str] = None
    delegate_done: Optional[dict] = None
    metadata: dict = field(default_factory=dict)
    agent_context: Optional[Any] = None   # AgentContext used for generation
    thinking_log_id: Optional[str] = None # ThinkingLog ID if tracking was enabled


# ── Engine ───────────────────────────────────────────────────────────────


class AgentChatEngine:
    """Unified agent chat engine — core LLM pipeline used by all channels."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db

    # ── Model Resolution ──────────────────────────────────────────────

    async def resolve_model(
        self, model_id_str: str,
    ) -> tuple[str, str, str, str | None]:
        """Resolve a model_id string to (provider, base_url, model_name, api_key).

        Supports:
          - 'ollama:modelname' -> direct Ollama
          - 'role:rolename' -> model role resolution
          - UUID string -> ModelConfig lookup
          - fallback to first active model
        """
        settings = get_settings()

        if model_id_str.startswith("ollama:"):
            model_name = model_id_str[7:]
            return ("ollama", settings.OLLAMA_BASE_URL, model_name, None)

        if model_id_str.startswith("role:"):
            role_name = model_id_str[5:]
            from app.services.model_role_service import resolve_model_for_role
            mc = await resolve_model_for_role(self.db, role_name)
            if not mc:
                raise ValueError(f"No model assigned for role '{role_name}'")
            if mc.provider == "ollama":
                return (mc.provider, settings.OLLAMA_BASE_URL, mc.model_id, mc.api_key)
            if mc.provider == "anthropic" and not mc.api_key:
                from app.api.settings import get_setting_value
                api_key = await get_setting_value(self.db, "anthropic_api_key")
                return (mc.provider, mc.base_url or "https://api.anthropic.com", mc.model_id, api_key)
            if mc.provider == "kieai" and not mc.api_key:
                from app.api.settings import get_setting_value
                api_key = await get_setting_value(self.db, "kieai_api_key")
                return (mc.provider, mc.base_url or "https://api.kie.ai", mc.model_id, api_key)
            return (mc.provider, mc.base_url or "https://api.openai.com/v1", mc.model_id, mc.api_key or "")

        try:
            uid = str(uuid.UUID(model_id_str))
        except ValueError:
            return ("ollama", settings.OLLAMA_BASE_URL, model_id_str, None)

        model_svc = ModelConfigService(self.db)
        mc = await model_svc.get_by_id(uid)
        if not mc:
            all_models = await model_svc.get_all(filter={"is_active": True}, limit=1)
            mc = all_models[0] if all_models else None
            if not mc:
                raise ValueError(f"Model config {model_id_str} not found and no active models available")

        if mc.provider == "ollama":
            return (mc.provider, settings.OLLAMA_BASE_URL, mc.model_id, mc.api_key)

        # Resolve API keys from system settings for managed providers
        if mc.provider == "anthropic" and not mc.api_key:
            from app.api.settings import get_setting_value
            api_key = await get_setting_value(self.db, "anthropic_api_key")
            return (mc.provider, mc.base_url or "https://api.anthropic.com", mc.model_id, api_key)
        if mc.provider == "kieai" and not mc.api_key:
            from app.api.settings import get_setting_value
            api_key = await get_setting_value(self.db, "kieai_api_key")
            return (mc.provider, mc.base_url or "https://api.kie.ai", mc.model_id, api_key)

        return (mc.provider, mc.base_url, mc.model_id, mc.api_key)

    async def resolve_agent_model(
        self, agent,
    ) -> tuple[str, str, str, str | None]:
        """Smart model resolution for an agent with fallback chain:
        1. Agent's assigned models (priority order)
        2. Agent's own model_id / model_name (legacy)
        3. Model role: 'dialog' then 'base'
        4. First active non-embedding model
        Returns (provider, base_url, model_name, api_key).
        """
        settings = get_settings()
        mc_svc = ModelConfigService(self.db)
        model_cfg = None

        # 1) Agent's assigned models
        agent_model_svc = AgentModelService(self.db)
        agent_models = await agent_model_svc.get_by_agent(str(agent.id))
        if agent_models:
            best = sorted(agent_models, key=lambda x: x.priority)[0]
            mid = str(best.model_config_id)
            if mid.startswith("role:"):
                # Resolve role to actual model
                role_name = mid[5:]
                from app.services.model_role_service import resolve_model_for_role
                model_cfg = await resolve_model_for_role(self.db, role_name)
            else:
                model_cfg = await mc_svc.get_by_id(mid)

        # 2) Agent's own model_id / model_name (legacy)
        if not model_cfg and (getattr(agent, "model_name", None) or getattr(agent, "model_id", None)):
            configs = await mc_svc.get_all()
            for cfg in configs:
                if cfg.model_id == agent.model_name or str(cfg.id) == str(agent.model_id or ""):
                    model_cfg = cfg
                    break

        # 3) Model role: 'dialog' then 'base'
        if not model_cfg:
            from app.services.model_role_service import resolve_model_for_role
            model_cfg = await resolve_model_for_role(self.db, "dialog")
            if not model_cfg:
                model_cfg = await resolve_model_for_role(self.db, "base")

        # 4) First active non-embedding model
        if not model_cfg:
            configs = await mc_svc.get_all(filter={"is_active": True})
            for cfg in configs:
                if "embed" not in (cfg.model_id or "").lower():
                    model_cfg = cfg
                    break

        if not model_cfg:
            raise ValueError(f"No LLM model available for agent {agent.name}")

        if model_cfg.provider == "ollama":
            return (model_cfg.provider, settings.OLLAMA_BASE_URL, model_cfg.model_id, model_cfg.api_key)

        # Resolve API keys from system settings for managed providers
        if model_cfg.provider == "anthropic" and not model_cfg.api_key:
            from app.api.settings import get_setting_value
            api_key = await get_setting_value(self.db, "anthropic_api_key")
            return (model_cfg.provider, model_cfg.base_url or "https://api.anthropic.com", model_cfg.model_id, api_key)
        if model_cfg.provider == "kieai" and not model_cfg.api_key:
            from app.api.settings import get_setting_value
            api_key = await get_setting_value(self.db, "kieai_api_key")
            return (model_cfg.provider, model_cfg.base_url or "https://api.kie.ai", model_cfg.model_id, api_key)

        return (
            model_cfg.provider,
            model_cfg.base_url or "https://api.openai.com/v1",
            model_cfg.model_id,
            model_cfg.api_key or "",
        )

    # ── LLM Call ──────────────────────────────────────────────────────

    @staticmethod
    async def chat_with_model(
        provider: str, base_url: str, model_name: str, api_key: str | None,
        messages: list[dict], params: GenerationParams | None = None,
    ) -> LLMResponse:
        """Send chat to a single model and return LLMResponse."""
        llm_messages = [Message(role=m["role"], content=m["content"]) for m in messages]
        if params is None:
            params = GenerationParams()

        if provider == "ollama":
            llm = OllamaProvider(base_url)
        elif provider == "anthropic":
            llm = AnthropicProvider(api_key=api_key, base_url=base_url)
        elif provider == "kieai":
            llm = KieAIProvider(api_key=api_key, base_url=base_url)
        else:
            llm = OpenAICompatibleProvider(base_url, api_key)

        return await llm.chat(model_name, llm_messages, params)

    # ── Context Loading ───────────────────────────────────────────────

    async def load_agent_context(
        self,
        agent_id: str,
        load_protocols: bool = True,
        load_skills: bool = True,
        load_beliefs: bool = True,
        load_aspirations: bool = True,
    ) -> AgentContext:
        """Load all agent context: config, settings, protocols, skills, beliefs, aspirations."""
        agent_svc = AgentService(self.db)
        agent = await agent_svc.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Load file-based config and settings
        from app.api.agent_files import read_agent_config, read_agent_settings
        agent_config = {}
        agent_settings = {}
        try:
            agent_config = read_agent_config(agent.name)
        except Exception:
            pass
        try:
            agent_settings = read_agent_settings(agent.name) or {}
        except Exception:
            pass

        base_system_prompt = agent_config.get("system_prompt", "") or agent.system_prompt or ""

        # Build GenerationParams from file settings
        gen_params = GenerationParams(
            temperature=agent_settings.get("temperature", getattr(agent, "temperature", 0.7) or 0.7),
            top_p=agent_settings.get("top_p", 0.9),
            top_k=agent_settings.get("top_k", 40),
            max_tokens=agent_settings.get("max_tokens", getattr(agent, "max_tokens", 2048) or 2048),
            num_ctx=agent_settings.get("num_ctx", 32768),
            repeat_penalty=agent_settings.get("repeat_penalty", 1.1),
            num_predict=agent_settings.get("num_predict", -1),
            stop=agent_settings.get("stop") or None,
            num_thread=agent_settings.get("num_thread", 8),
            num_gpu=agent_settings.get("num_gpu", 1),
        )

        # Load protocols
        protocols = []
        if load_protocols:
            protocols = await self.load_agent_protocols(agent_id, self.db)

        # Load skills
        skills = []
        if load_skills:
            skills = await self.load_agent_skills(agent_id, self.db, agent=agent)

        # Load beliefs
        beliefs = None
        if load_beliefs:
            try:
                from app.api.agent_beliefs import read_beliefs
                beliefs = read_beliefs(agent.name)
            except Exception:
                pass

        # Load aspirations
        aspirations = None
        if load_aspirations:
            try:
                from app.api.agent_aspirations import read_aspirations
                aspirations = read_aspirations(agent.name)
            except Exception:
                pass

        return AgentContext(
            agent=agent,
            config=agent_config,
            settings=agent_settings,
            gen_params=gen_params,
            protocols=protocols,
            skills=skills,
            beliefs=beliefs,
            aspirations=aspirations,
            base_system_prompt=base_system_prompt,
        )

    @staticmethod
    async def load_agent_protocols(agent_id: str, db: AsyncIOMotorDatabase) -> list[dict]:
        """Load all protocols assigned to an agent."""
        ap_svc = AgentProtocolService(db)
        proto_svc = ThinkingProtocolService(db)
        agent_protos = await ap_svc.get_by_agent(agent_id)
        protocols = []
        for ap in agent_protos:
            p = await proto_svc.get_by_id(ap.protocol_id)
            if p:
                protocols.append({
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description or "",
                    "type": p.type or "standard",
                    "steps": p.steps or [],
                    "is_main": ap.is_main,
                    "priority": ap.priority,
                })
        return protocols

    @staticmethod
    async def load_agent_skills(agent_id: str, db: AsyncIOMotorDatabase, agent=None) -> list[dict]:
        """Load all enabled skills for an agent."""
        from app.api.settings import get_setting_value

        # Determine effective permissions (global AND agent-level)
        global_fs = (await get_setting_value(db, "filesystem_access_enabled")) == "true"
        global_sys = (await get_setting_value(db, "system_access_enabled")) == "true"
        agent_fs = agent.filesystem_access if agent else False
        agent_sys = agent.system_access if agent else False
        effective_fs = global_fs and agent_fs
        effective_sys = global_sys and agent_sys

        FS_SKILLS = {"file_read", "file_write"}
        SYS_SKILLS = {"shell_exec", "code_execute"}

        # Get all potentially available skills (system, shared, or author)
        skill_svc = SkillService(db)
        all_skills_list = await skill_svc.get_all(limit=1000)
        agent_id_str = str(agent_id)
        all_skills = [
            s for s in all_skills_list
            if s.is_system or s.is_shared or s.author_agent_id == agent_id_str
        ]

        # Check disabled state from agent_skills
        ask_svc = AgentSkillService(db)
        agent_skill_records = await ask_svc.get_all(filter={"agent_id": agent_id_str}, limit=1000)
        disabled_ids = {str(ask.skill_id) for ask in agent_skill_records if not ask.is_enabled}

        skills = []
        for s in all_skills:
            if str(s.id) in disabled_ids:
                continue
            # Skip globally disabled skills
            if not getattr(s, "enabled", True):
                continue
            if s.name in FS_SKILLS and not effective_fs:
                continue
            if s.name in SYS_SKILLS and not effective_sys:
                continue
            skills.append({
                "id": str(s.id),
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description or "",
                "description_for_agent": s.description_for_agent or "",
                "category": s.category,
                "code": s.code,
                "input_schema": s.input_schema or {},
            })
        return skills

    # ── Skill Execution ───────────────────────────────────────────────

    @staticmethod
    async def execute_skill(skill_name: str, args: dict, agent_skills: list[dict]) -> dict:
        """Execute a skill by name and return the result.
        Returns {"result": ...} on success or {"error": ...} on failure.
        """
        skill = None
        for s in agent_skills:
            if s["name"] == skill_name:
                skill = s
                break

        if not skill:
            return {"error": f"Skill '{skill_name}' not found or not enabled"}

        code = skill.get("code", "")
        if not code or code.startswith("#"):
            return {"error": f"Skill '{skill_name}' has no executable code"}

        # Inject PROJECTS_DIR env var for project-aware skills
        _settings = get_settings()
        os.environ.setdefault("PROJECTS_DIR", _settings.PROJECTS_DIR)

        try:
            namespace = {}
            exec(code, namespace)

            execute_fn = namespace.get("execute")
            if not execute_fn:
                return {"error": f"Skill '{skill_name}' has no execute() function"}

            # Normalize args: map common LLM mistakes to actual parameter names
            sig = inspect.signature(execute_fn)
            expected_params = set(sig.parameters.keys())
            alias_map = {}
            for p in expected_params:
                alias_map[p] = p
                parts = p.split('_')
                if len(parts) > 1:
                    alias_map[parts[-1]] = p
                    alias_map['_'.join(parts[1:])] = p
            normalized = {}
            for k, v in args.items():
                mapped = alias_map.get(k, k)
                normalized[mapped] = v

            if asyncio.iscoroutinefunction(execute_fn):
                result = await execute_fn(**normalized)
            else:
                result = execute_fn(**normalized)

            return {"result": result}
        except Exception as e:
            return {"error": f"Skill '{skill_name}' execution failed: {str(e)}"}

    # ── Project/Task Context ──────────────────────────────────────────

    async def load_project_task_context(
        self,
        agent_context: AgentContext,
        project_slug: str | None = None,
        task_id: str | None = None,
    ) -> list[str]:
        """Load project and task context via skills, append to agent_context.base_system_prompt.

        Returns list of context summary parts (for logging/tracking).
        """
        context_parts = []

        if not project_slug and not task_id:
            return context_parts

        if project_slug:
            try:
                has_skill = any(s["name"] == "project_context_build" for s in agent_context.skills)
                if has_skill:
                    proj_result = await self.execute_skill(
                        "project_context_build",
                        {"project_slug": project_slug, "max_recent_logs": 30},
                        agent_context.skills,
                    )
                    if "result" in proj_result:
                        pc = proj_result["result"]
                        proj_info = pc.get("project", {})
                        context_parts.append(
                            f"\U0001f4c1 Project: {proj_info.get('name')} ({project_slug})\n"
                            f"   Goals: {proj_info.get('goals', 'N/A')[:200]}\n"
                            f"   Tech Stack: {', '.join(proj_info.get('tech_stack', []))}\n"
                            f"   Tasks: {pc.get('task_stats', {}).get('total', 0)} total, "
                            f"{pc.get('task_stats', {}).get('in_progress', 0)} in progress\n"
                            f"   Files: {pc.get('file_tree', {}).get('total_files', 0)}"
                        )
            except Exception as e:
                logger.warning(f"Failed to load project context for {project_slug}: {e}")

        if task_id and project_slug:
            try:
                has_skill = any(s["name"] == "task_context_build" for s in agent_context.skills)
                if has_skill:
                    task_result = await self.execute_skill(
                        "task_context_build",
                        {"project_slug": project_slug, "task_id": task_id},
                        agent_context.skills,
                    )
                    if "result" in task_result:
                        tc = task_result["result"]
                        task_info = tc.get("task", {})
                        context_parts.append(
                            f"\n\U0001f4cb Current Task: {task_info.get('key')} - {task_info.get('title')}\n"
                            f"   Status: {task_info.get('status')} | Priority: {task_info.get('priority')}\n"
                            f"   Description: {task_info.get('description', 'N/A')[:300]}\n"
                            f"   Comments: {len(tc.get('comments', []))}, "
                            f"Related Files: {len(tc.get('related_files', []))}"
                        )
            except Exception as e:
                logger.warning(f"Failed to load task context for {task_id}: {e}")

        if context_parts:
            context_summary = "\n\n## Current Work Context\n\n" + "\n".join(context_parts)
            agent_context.base_system_prompt += context_summary

        return context_parts

    # ── General Projects Overview ─────────────────────────────────────

    async def load_general_context_overview(self, agent_id: str) -> str:
        """Load a brief overview of active projects AND agent's standalone tasks.

        Called when no specific project_slug is set so the agent still
        knows about existing projects, their active tasks, and its own
        standalone tasks from the task backlog.

        Returns a string to append to the system prompt.
        """
        sections = []

        # ── 1. Active projects from filesystem ──
        settings = get_settings()
        projects_dir = Path(settings.PROJECTS_DIR)
        if projects_dir.exists():
            project_parts = []
            for project_dir in sorted(projects_dir.iterdir()):
                if not project_dir.is_dir():
                    continue
                project_json = project_dir / "project.json"
                if not project_json.exists():
                    continue
                try:
                    proj = json.loads(project_json.read_text(encoding="utf-8"))
                except Exception:
                    continue

                status = proj.get("status", "unknown")
                # Skip non-active projects
                if status in ("paused", "completed", "archived"):
                    continue

                name = proj.get("name", project_dir.name)
                slug = proj.get("slug", project_dir.name)
                description = (proj.get("description") or "")[:150]
                goals = (proj.get("goals") or "")[:150]
                tech_stack = ", ".join(proj.get("tech_stack", []))

                # Load task stats
                tasks_json = project_dir / "tasks.json"
                task_counts = {}
                active_tasks = []
                if tasks_json.exists():
                    try:
                        tasks = json.loads(tasks_json.read_text(encoding="utf-8"))
                        for t in tasks:
                            s = t.get("status", "backlog")
                            task_counts[s] = task_counts.get(s, 0) + 1
                            if s in ("todo", "in_progress"):
                                active_tasks.append(
                                    f"[{s}] {t.get('key', '?')} - {t.get('title', '?')[:60]}"
                                )
                    except Exception:
                        pass

                total_tasks = sum(task_counts.values())
                done_tasks = task_counts.get("done", 0)
                in_progress = task_counts.get("in_progress", 0)
                todo = task_counts.get("todo", 0)

                entry = f"- **{name}** (slug: `{slug}`, status: {status})"
                if description:
                    entry += f"\n  Description: {description}"
                if goals:
                    entry += f"\n  Goals: {goals}"
                if tech_stack:
                    entry += f"\n  Tech: {tech_stack}"
                entry += (
                    f"\n  Tasks: {total_tasks} total, {done_tasks} done, "
                    f"{in_progress} in progress, {todo} todo"
                )
                if active_tasks:
                    entry += "\n  Active tasks:"
                    for at in active_tasks[:5]:
                        entry += f"\n    {at}"
                project_parts.append(entry)

            if project_parts:
                sections.append(
                    "## Your Projects\n\n"
                    "You have access to following active projects:\n\n"
                    + "\n\n".join(project_parts)
                    + "\n\nYou can use project skills (project_list_files, project_file_read, "
                    "project_file_write, project_context_build, etc.) to work with these projects. "
                    "Always specify the `project_slug` parameter when using project skills."
                )

        # ── 2. Agent's standalone tasks from MongoDB ──
        try:
            agent_tasks = await self.db.tasks.find(
                {"agent_id": str(agent_id)}
            ).sort("created_at", -1).to_list(50)

            if agent_tasks:
                task_lines = []
                for t in agent_tasks:
                    status = t.get("status", "?")
                    priority = t.get("priority", "normal")
                    title = t.get("title", "?")
                    desc = (t.get("description") or "")[:100]
                    task_type = t.get("type", "one_time")
                    line = f"- [{status}] ({priority}) {title}"
                    if task_type == "recurring" and t.get("schedule"):
                        line += f" (recurring: {t['schedule']})"
                    if desc:
                        line += f"\n  {desc}"
                    task_lines.append(line)

                sections.append(
                    "## Your Tasks\n\n"
                    "Your assigned standalone tasks:\n\n"
                    + "\n".join(task_lines)
                )
        except Exception as e:
            logger.warning(f"Failed to load agent tasks: {e}")

        if not sections:
            return ""

        return "\n\n" + "\n\n".join(sections) + "\n"

    # ── High-Level Generate ───────────────────────────────────────────

    async def generate_full(
        self,
        agent_id: str,
        user_input: str,
        history: list[dict],
        *,
        session_id: str | None = None,
        project_slug: str | None = None,
        task_id: str | None = None,
        model_id: str | None = None,
        max_skill_iterations: int = 5,
        extra_context: str = "",
        current_todo: list[dict] | None = None,
        delegation_stack: list[str] | None = None,
        load_protocols: bool = True,
        load_skills: bool = True,
        load_beliefs: bool = True,
        load_aspirations: bool = True,
        enable_thinking_log: bool = True,
        summary: str | None = None,
        use_staged_pipeline: bool | str = "auto",
    ) -> EngineResult:
        """Full pipeline: context load -> prompt build -> LLM -> skills -> thinking log.

        Args:
            use_staged_pipeline: "auto" (default) enables staged pipeline when agent
                has skills loaded. True/False for explicit control.

        This is the recommended entry point for ALL channels (web chat, Telegram, etc.).
        It handles everything: context loading, project/task context enrichment,
        system prompt building with full agent context (beliefs, aspirations, skills,
        protocols), thinking log recording, LLM calls, and skill execution.

        Args:
            agent_id: Agent ID to generate for.
            user_input: Current user message text.
            history: Previous conversation messages [{role, content}].
                     Do NOT include system prompt or the current user message.
            session_id: Enables thinking log. Can be chat session ID, messenger chat_id, etc.
            project_slug: Load project context via project_context_build skill.
            task_id: Load task context via task_context_build skill.
            model_id: Explicit model_id. If None, resolved from agent.
            max_skill_iterations: Max skill loops (0 = no skills).
            extra_context: Extra text appended to system prompt (e.g. messenger context).
            current_todo: Current protocol todo list.
            delegation_stack: Protocol delegation stack.
            load_protocols/skills/beliefs/aspirations: What to load.
            enable_thinking_log: Record thinking log steps (requires session_id).
            summary: Conversation summary to inject as system message.

        Returns:
            EngineResult with clean content, thinking_log_id, agent_context, etc.
        """
        from app.services.thinking_log_service import ThinkingTracker

        tracker = None
        if enable_thinking_log and session_id:
            tracker = ThinkingTracker(self.db, agent_id, session_id, user_input)
            await tracker.start()

        try:
            # ── 1. Load agent context ──
            if tracker:
                tracker.start_step_timer()

            ctx = await self.load_agent_context(
                agent_id,
                load_protocols=load_protocols,
                load_skills=load_skills,
                load_beliefs=load_beliefs,
                load_aspirations=load_aspirations,
            )

            if tracker:
                await tracker.step(
                    "config_load", "Load agent configuration",
                    input_data={"agent_name": ctx.agent.name},
                    output_data={
                        "has_system_prompt": bool(ctx.base_system_prompt),
                        "system_prompt_length": len(ctx.base_system_prompt),
                        "gen_params": {
                            "temperature": ctx.gen_params.temperature,
                            "top_p": ctx.gen_params.top_p,
                            "top_k": ctx.gen_params.top_k,
                            "max_tokens": ctx.gen_params.max_tokens,
                            "num_ctx": ctx.gen_params.num_ctx,
                        },
                        "protocols_count": len(ctx.protocols),
                        "protocols": [p.get("name", "?") for p in ctx.protocols],
                        "skills_count": len(ctx.skills),
                        "skills": [s.get("name", "?") for s in ctx.skills],
                        "has_beliefs": bool(ctx.beliefs),
                        "has_aspirations": bool(ctx.aspirations),
                    },
                    duration_ms=tracker.elapsed_step_ms(),
                )

            # ── 2. Load project/task context ──
            if project_slug or task_id:
                if tracker:
                    tracker.start_step_timer()

                context_parts = await self.load_project_task_context(
                    ctx, project_slug=project_slug, task_id=task_id,
                )

                if tracker:
                    await tracker.step(
                        "project_task_context", "Load project/task context",
                        output_data={
                            "has_project_context": bool(context_parts),
                            "context_summary_length": sum(len(p) for p in context_parts),
                            "context_parts": context_parts,
                        },
                        duration_ms=tracker.elapsed_step_ms(),
                    )
            else:
                # No specific project — load general overview of active projects + agent tasks
                if tracker:
                    tracker.start_step_timer()

                general_context = await self.load_general_context_overview(agent_id)
                if general_context:
                    ctx.base_system_prompt += general_context

                if tracker:
                    await tracker.step(
                        "context_load", "Load general projects & tasks overview",
                        output_data={
                            "has_overview": bool(general_context),
                            "overview_length": len(general_context) if general_context else 0,
                            "overview": general_context or "",
                        },
                        duration_ms=tracker.elapsed_step_ms(),
                    )

            # ── 3. Build system prompt ──
            if tracker:
                tracker.start_step_timer()

            system_prompt = self.build_system_prompt(
                ctx,
                current_todo=current_todo,
                delegation_stack=delegation_stack,
                extra_context=extra_context,
            )

            if tracker:
                await tracker.step(
                    "prompt_build", "Build system prompt",
                    input_data={
                        "delegation_stack": delegation_stack,
                        "has_todo": bool(current_todo),
                    },
                    output_data={
                        "system_prompt_length": len(system_prompt) if system_prompt else 0,
                        "system_prompt": system_prompt or "",
                    },
                    duration_ms=tracker.elapsed_step_ms(),
                )

            # ── 4. Build messages ──
            messages = [{"role": "system", "content": system_prompt}]

            if summary:
                messages.append({"role": "system", "content": (
                    f"**Previous conversation summary:**\n\n{summary}"
                )})

            messages.extend(history)
            messages.append({"role": "user", "content": user_input})

            if tracker:
                await tracker.step(
                    "history_build", "Build conversation history",
                    output_data={
                        "history_messages": len(messages),
                        "total_chars": sum(len(m["content"]) for m in messages),
                        "has_summary": bool(summary),
                        "messages": [
                            {"role": m["role"], "content_length": len(m["content"]), "content": m["content"]}
                            for m in messages
                        ],
                    },
                )

            # ── 5. Generate ──
            # Auto-detect staged pipeline: use when agent has skills
            should_use_staged = (
                (use_staged_pipeline == "auto" and ctx.skills)
                or (use_staged_pipeline is True and ctx.skills)
            )
            if should_use_staged:
                # Multi-stage pipeline: Understand → Plan → Execute → Synthesize
                staged_prompt = system_prompt
                if summary:
                    staged_prompt += f"\n\n**Previous conversation summary:**\n\n{summary}"
                result = await self.generate_staged(
                    user_input=user_input,
                    history=history,
                    system_prompt=staged_prompt,
                    agent_context=ctx,
                    model_id=model_id,
                    tracker=tracker,
                )
            else:
                # Classic single-shot pipeline (LLM + skill markers)
                result = await self.generate(
                    messages=messages,
                    agent_context=ctx,
                    model_id=model_id,
                    max_skill_iterations=max_skill_iterations,
                    parse_protocols=bool(ctx.protocols),
                    tracker=tracker,
                )

            # Attach agent context and thinking log ID
            result.agent_context = ctx
            if tracker and tracker.log:
                result.thinking_log_id = str(tracker.log.id)

            # ── 6. Complete thinking log ──
            if tracker:
                await tracker.complete(
                    result.content,
                    model_name=result.model_name,
                    total_tokens=result.total_tokens,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    llm_calls_count=result.llm_calls_count,
                )

            return result

        except asyncio.CancelledError:
            # asyncio.CancelledError does NOT inherit from Exception in Python 3.9+
            # — must catch explicitly so the thinking log doesn't stay "started" forever.
            if tracker:
                await tracker.fail("Task cancelled (client disconnected or timeout)")
            raise
        except Exception as e:
            if tracker:
                await tracker.fail(str(e))
            raise

    # ── Core Generate ─────────────────────────────────────────────────

    async def generate(
        self,
        messages: list[dict],
        agent_context: AgentContext,
        model_id: str | None = None,
        max_skill_iterations: int = 5,
        parse_protocols: bool = True,
        tracker: Any = None,
    ) -> EngineResult:
        """LLM call -> parse response -> skill execution -> follow-up -> return.

        For full pipeline with context loading and thinking log, use generate_full().

        Args:
            messages: Conversation history [{role, content}, ...] including system prompt.
            agent_context: Loaded agent context (from load_agent_context()).
            model_id: Explicit model_id to use. If None, resolves from agent.
            max_skill_iterations: Max skill execution loops (0 = no skills).
            parse_protocols: Whether to parse todo/delegation/skill markers.
            tracker: Optional ThinkingTracker for recording LLM/skill steps.

        Returns:
            EngineResult with clean content, raw content, tokens, skills, etc.
        """
        start = time.monotonic()

        # ── Resolve model ──
        if model_id:
            provider, base_url, model_name, api_key = await self.resolve_model(model_id)
        else:
            provider, base_url, model_name, api_key = await self.resolve_agent_model(
                agent_context.agent,
            )

        gen_params = agent_context.gen_params

        # ── Initial LLM call ──
        if tracker:
            tracker.start_step_timer()

        try:
            llm_resp = await self.chat_with_model(
                provider, base_url, model_name, api_key,
                messages, gen_params,
            )
        except Exception as e:
            logger.error(f"LLM call failed (model={model_name}): {e}", exc_info=True)
            if tracker:
                await tracker.step(
                    "llm_call", f"LLM call failed ({model_name})",
                    input_data={"model": model_name, "provider": provider},
                    status="error",
                    error_message=str(e),
                    duration_ms=tracker.elapsed_step_ms(),
                )
            raise

        llm_content = llm_resp.content.strip() if llm_resp.content else ""
        total_tokens = llm_resp.total_tokens
        prompt_tokens = getattr(llm_resp, "prompt_tokens", 0)
        completion_tokens = getattr(llm_resp, "completion_tokens", 0)
        llm_calls = 1
        all_skill_results = []
        raw_parts = [llm_content]

        if tracker:
            await tracker.step(
                "llm_call", f"LLM inference ({model_name})",
                input_data={
                    "model": model_name,
                    "provider": provider,
                    "history_messages": len(messages),
                    "gen_params": {
                        "temperature": gen_params.temperature,
                        "top_p": gen_params.top_p,
                        "top_k": gen_params.top_k,
                        "max_tokens": gen_params.max_tokens,
                        "num_ctx": gen_params.num_ctx,
                    },
                },
                output_data={
                    "response_length": len(llm_content),
                    "response": llm_content or "",
                    "total_tokens": total_tokens,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                duration_ms=tracker.elapsed_step_ms(),
            )

        # ── Protocol parsing + skill loop ──
        result_todo = None
        result_delegate_to = None
        result_delegate_done = None

        if parse_protocols and llm_content:
            # Parse todo
            result_todo = parse_todo_list(llm_content)

            # Parse delegation
            result_delegate_to = parse_delegate(llm_content)
            result_delegate_done = parse_delegate_done(llm_content)

            # Skill execution loop
            if max_skill_iterations > 0 and agent_context.skills:
                iteration = 0
                current_content = llm_content

                while iteration < max_skill_iterations:
                    skill_calls = parse_skill_invocations(current_content)
                    if not skill_calls:
                        break

                    iteration += 1
                    logger.info(
                        f"Engine: executing {len(skill_calls)} skill(s), "
                        f"iteration {iteration}/{max_skill_iterations}"
                    )

                    # Execute all skills
                    if tracker:
                        tracker.start_step_timer()

                    iter_results = []
                    for call in skill_calls:
                        result = await self.execute_skill(
                            call["skill_name"], call["args"], agent_context.skills,
                        )
                        iter_results.append({
                            "skill": call["skill_name"],
                            "args": call["args"],
                            "result": result,
                        })
                    all_skill_results.extend(iter_results)

                    if tracker:
                        await tracker.step(
                            "skill_exec", f"Execute skills (iteration {iteration})",
                            input_data={
                                "skills": [c["skill_name"] for c in skill_calls],
                                "args": [c["args"] for c in skill_calls],
                            },
                            output_data={
                                "results_count": len(iter_results),
                                "results": [
                                    {
                                        "skill": r["skill"],
                                        "args": r["args"],
                                        "has_error": "error" in r["result"],
                                        "result": r["result"],
                                    }
                                    for r in iter_results
                                ],
                            },
                            duration_ms=tracker.elapsed_step_ms(),
                        )

                    # Build feedback and follow-up LLM call
                    skill_feedback = "\n\n".join(
                        f"**Skill `{sr['skill']}` result:**\n```json\n"
                        f"{json.dumps(sr['result'], ensure_ascii=False, indent=2)}\n```"
                        for sr in iter_results
                    )
                    follow_up_prompt = (
                        f"Skills have been executed. Here are the results:\n\n"
                        f"{skill_feedback}\n\n"
                        f"Continue with your protocol steps based on these results."
                    )

                    messages.append({"role": "assistant", "content": current_content})
                    messages.append({"role": "user", "content": follow_up_prompt})

                    try:
                        follow_resp = await self.chat_with_model(
                            provider, base_url, model_name, api_key,
                            messages, gen_params,
                        )
                    except Exception as e:
                        logger.error(f"Follow-up LLM call failed: {e}", exc_info=True)
                        break

                    if not follow_resp or not follow_resp.content:
                        break

                    current_content = follow_resp.content.strip()
                    raw_parts.append(current_content)
                    total_tokens += follow_resp.total_tokens
                    prompt_tokens += getattr(follow_resp, "prompt_tokens", 0)
                    completion_tokens += getattr(follow_resp, "completion_tokens", 0)
                    llm_calls += 1

                    # Re-parse todo/delegation from follow-up
                    new_todo = parse_todo_list(current_content)
                    if new_todo:
                        result_todo = new_todo

                    new_delegate = parse_delegate(current_content)
                    if new_delegate:
                        result_delegate_to = new_delegate

                    new_done = parse_delegate_done(current_content)
                    if new_done:
                        result_delegate_done = new_done

                # Update llm_content to the last response
                llm_content = current_content

        # ── Build raw content (all parts joined) ──
        raw_content = "\n\n---\n\n".join(raw_parts) if len(raw_parts) > 1 else raw_parts[0]

        # ── Clean content ──
        clean_content = self.clean_protocol_markers(llm_content)

        duration_ms = int((time.monotonic() - start) * 1000)

        if tracker and parse_protocols:
            await tracker.step(
                "response_parse", "Parse LLM response (todo, delegation, skills)",
                output_data={
                    "todo_found": bool(result_todo),
                    "todo_list": result_todo,
                    "delegation_found": bool(result_delegate_to),
                    "delegation_target": result_delegate_to,
                    "delegate_done": bool(result_delegate_done),
                    "delegate_done_data": result_delegate_done,
                    "skill_calls_total": len(all_skill_results),
                    "clean_content": clean_content,
                    "raw_content": raw_content,
                },
            )

        return EngineResult(
            content=clean_content,
            raw_content=raw_content,
            model_name=model_name,
            provider=provider,
            total_tokens=total_tokens,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            llm_calls_count=llm_calls,
            duration_ms=duration_ms,
            skill_results=all_skill_results if all_skill_results else [],
            todo_list=result_todo,
            delegate_to=result_delegate_to,
            delegate_done=result_delegate_done,
            metadata={},
        )

    # ── Staged Pipeline ─────────────────────────────────────────────

    async def generate_staged(
        self,
        user_input: str,
        history: list[dict],
        system_prompt: str,
        agent_context: AgentContext,
        model_id: str | None = None,
        tracker: Any = None,
    ) -> EngineResult:
        """Multi-stage pipeline: Pre-process → Understand → Plan → Execute → Synthesize.

        An alternative to generate() that uses multiple focused LLM calls
        instead of relying on the model to generate <<<SKILL>>> markers.
        Effective even with small models (3B, 7B).

        Args:
            user_input: Current user message.
            history: Previous messages [{role, content}] — user/assistant only.
            system_prompt: Full agent system prompt.
            agent_context: Loaded agent context.
            model_id: Optional explicit model ID.
            tracker: Optional ThinkingTracker.

        Returns:
            EngineResult compatible with generate().
        """
        from app.services.staged_pipeline import StagedPipeline

        pipeline = StagedPipeline(self, agent_context, tracker)
        result = await pipeline.run(
            user_input=user_input,
            history=history,
            system_prompt=system_prompt,
            model_id=model_id,
        )

        return EngineResult(
            content=result["content"],
            raw_content=result.get("raw_content", result["content"]),
            model_name=result["model_name"],
            provider=result.get("provider", "unknown"),
            total_tokens=result["total_tokens"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            llm_calls_count=result["llm_calls_count"],
            duration_ms=result["duration_ms"],
            skill_results=[],
            todo_list=None,
            delegate_to=None,
            delegate_done=None,
            metadata={
                "pipeline": "staged",
                "analysis": result.get("analysis"),
                "plan": result.get("plan"),
                "execution": result.get("execution"),
                "classification": result.get("classification"),
                "stages_run": result.get("stages_run"),
            },
        )

    # ── Utilities ─────────────────────────────────────────────────────

    @staticmethod
    def clean_protocol_markers(text: str) -> str:
        """Strip all protocol markers from text for clean output."""
        if not text:
            return text
        clean = re.sub(r'<<<SKILL:\w+>>>\s*\{[^}]*\}\s*<<<END_SKILL>>>', '', text)
        clean = re.sub(r'<<<TODO>>>.*?<<<END_TODO>>>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'<<<DELEGATE:\w+>>>', '', clean)
        clean = re.sub(r'<<<DELEGATE_DONE:[^>]*>>>', '', clean)
        clean = re.sub(r'<<<DELEGATE_RESULT>>>.*?<<<END_DELEGATE_RESULT>>>', '', clean, flags=re.DOTALL)
        clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
        return clean if clean else text

    @staticmethod
    def build_system_prompt(
        agent_context: AgentContext,
        current_todo: list[dict] | None = None,
        delegation_stack: list[str] | None = None,
        extra_context: str = "",
    ) -> str:
        """Build a full system prompt from agent context using protocol_executor.

        ALWAYS includes beliefs, aspirations, and skills — even without protocols.
        """
        if not agent_context.protocols:
            # No protocols — still include all agent context (beliefs, aspirations, skills)
            prompt = build_agent_system_prompt(
                base_system_prompt=agent_context.base_system_prompt,
                agent_name=agent_context.agent.name,
                protocols=[],
                available_skills=agent_context.skills or None,
                beliefs=agent_context.beliefs,
                aspirations=agent_context.aspirations,
            )
            if extra_context:
                prompt += extra_context
            return prompt

        # Handle delegation chain
        active_child = delegation_stack[-1] if delegation_stack else None
        protocols_to_use = agent_context.protocols

        if active_child:
            child_proto = None
            for p in agent_context.protocols:
                if p["name"] == active_child or p["id"] == active_child:
                    child_proto = p
                    break
            if child_proto:
                if child_proto.get("type") == "orchestrator":
                    child_proto["child_protocols"] = [
                        p for p in agent_context.protocols
                        if p["id"] != child_proto["id"] and p.get("type") != "orchestrator"
                    ]
                protocols_to_use = [{**child_proto, "is_main": True}]

        system_prompt = build_agent_system_prompt(
            base_system_prompt=agent_context.base_system_prompt,
            agent_name=agent_context.agent.name,
            protocols=protocols_to_use,
            available_skills=agent_context.skills or None,
            current_todo=current_todo,
            beliefs=agent_context.beliefs,
            aspirations=agent_context.aspirations,
        )

        # Add delegation context
        if delegation_stack and active_child:
            stack_info = " -> ".join(delegation_stack)
            system_prompt += f"\n\n_Active delegation chain: {stack_info}_\n"
            system_prompt += "When done with this delegated work, output: `<<<DELEGATE_DONE:summary>>>`\n"

        if extra_context:
            system_prompt += extra_context

        return system_prompt
