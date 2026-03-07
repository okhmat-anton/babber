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
  - Generation parameter construction
  - LLM calls (single model)
  - Response parsing (todo, delegation, skill invocations)
  - Skill execution loop with follow-up LLM calls
  - Response cleanup (strip protocol markers)

Callers are responsible for:
  - Building the system prompt (using protocol_executor helpers)
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
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.llm.base import Message, GenerationParams, LLMResponse
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
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
          - 'ollama:modelname' → direct Ollama
          - UUID string → ModelConfig lookup
          - fallback to first active model
        """
        settings = get_settings()

        if model_id_str.startswith("ollama:"):
            model_name = model_id_str[7:]
            return ("ollama", settings.OLLAMA_BASE_URL, model_name, None)

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
            model_cfg = await mc_svc.get_by_id(str(best.model_config_id))

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

    # ── Core Generate ─────────────────────────────────────────────────

    async def generate(
        self,
        messages: list[dict],
        agent_context: AgentContext,
        model_id: str | None = None,
        max_skill_iterations: int = 5,
        parse_protocols: bool = True,
    ) -> EngineResult:
        """Full pipeline: LLM call → parse response → skill execution → follow-up → return.

        Args:
            messages: Conversation history [{role, content}, ...] including system prompt.
            agent_context: Loaded agent context (from load_agent_context()).
            model_id: Explicit model_id to use. If None, resolves from agent.
            max_skill_iterations: Max skill execution loops (0 = no skills).
            parse_protocols: Whether to parse todo/delegation/skill markers.

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
        try:
            llm_resp = await self.chat_with_model(
                provider, base_url, model_name, api_key,
                messages, gen_params,
            )
        except Exception as e:
            logger.error(f"LLM call failed (model={model_name}): {e}", exc_info=True)
            raise

        llm_content = llm_resp.content.strip() if llm_resp.content else ""
        total_tokens = llm_resp.total_tokens
        prompt_tokens = getattr(llm_resp, "prompt_tokens", 0)
        completion_tokens = getattr(llm_resp, "completion_tokens", 0)
        llm_calls = 1
        all_skill_results = []
        raw_parts = [llm_content]

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

        This is a convenience wrapper. Callers can build prompts manually if needed.
        """
        if not agent_context.protocols:
            prompt = agent_context.base_system_prompt or ""
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
            stack_info = " → ".join(delegation_stack)
            system_prompt += f"\n\n_Active delegation chain: {stack_info}_\n"
            system_prompt += "When done with this delegated work, output: `<<<DELEGATE_DONE:summary>>>`\n"

        if extra_context:
            system_prompt += extra_context

        return system_prompt
