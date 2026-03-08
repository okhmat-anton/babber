"""
Chat API — persistent chat sessions with single/multi-model support.
Integrates protocol execution: orchestrator delegation, todo tracking, skill invocation.
Uses AgentChatEngine as the unified core for agent LLM interaction.
"""
import asyncio
import json
import time
import uuid
from typing import Optional
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.config import get_settings
from app.core.dependencies import get_current_user
from app.mongodb.models import (
    MongoChatSession, MongoChatMessage, MongoAgentError, MongoTask,
)
from app.mongodb.services import (
    AgentService, AgentModelService, AgentProtocolService, AgentErrorService,
    ModelConfigService, ChatSessionService, ChatMessageService,
    SkillService, AgentSkillService, ThinkingProtocolService, TaskService,
)
from app.llm.base import Message, GenerationParams, LLMResponse
from app.llm.ollama import OllamaProvider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.api.agent_files import read_agent_config, read_agent_settings
from app.api.agent_beliefs import read_beliefs
from app.services.protocol_executor import (
    build_agent_system_prompt,
    format_child_protocol_prompt,
    parse_skill_invocations,
    parse_todo_list,
    parse_delegate,
    parse_delegate_done,
)
from app.services.thinking_log_service import ThinkingTracker
from app.services.model_role_service import resolve_model_for_role
from app.services.chat_summary_service import (
    should_summarize_session,
    create_summary,
    get_session_messages_for_llm,
)
from app.services.agent_chat_engine import AgentChatEngine, AgentContext, EngineResult

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Schemas ──────────────────────────────────────────────

class ChatSessionCreate(BaseModel):
    title: str = "New Chat"
    model_ids: list[str] = []          # model_config UUIDs or "ollama:modelname"
    agent_id: Optional[str] = None
    agent_ids: list[str] = []          # multiple agent UUIDs for multi-agent mode
    multi_model: bool = False
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    chat_type: str = "user"            # 'user', 'agent', 'project_task'
    project_slug: Optional[str] = None # for project_task chats
    task_id: Optional[str] = None      # for project_task chats


class ChatSessionUpdate(BaseModel):
    title: Optional[str] = None
    model_ids: Optional[list[str]] = None
    multi_model: Optional[bool] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    model_ids: list[str]
    agent_id: Optional[str] = None
    agent_ids: list[str] = []
    multi_model: bool
    system_prompt: Optional[str] = None
    temperature: float
    chat_type: str = "user"
    project_slug: Optional[str] = None
    task_id: Optional[str] = None
    unread_count: int = 0
    message_count: int = 0
    created_at: str
    updated_at: str
    last_message: Optional[str] = None

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    model_name: Optional[str] = None
    model_responses: Optional[dict] = None
    total_tokens: int = 0
    duration_ms: int = 0
    created_at: str


class SendMessageRequest(BaseModel):
    content: str
    # Override models for this message (optional)
    model_ids: Optional[list[str]] = None


class AvailableModel(BaseModel):
    id: str
    name: str
    model_id: str
    provider: str
    type: str = "model"  # "model" or "agent"


# ── Helpers ──────────────────────────────────────────────

def _ts(val) -> str:
    """Convert datetime or string to ISO string."""
    if val is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(val, str):
        return val
    return val.isoformat()


def _session_to_response(session: MongoChatSession, messages: list = None,
                         model_names: dict[str, str] = None) -> dict:
    msgs = messages or []
    last_msg = None
    if msgs:
        last = msgs[-1]
        content = last.content if hasattr(last, "content") else last.get("content")
        last_msg = content[:100] if content else None
    return {
        "id": str(session.id),
        "title": session.title,
        "model_ids": session.model_ids or [],
        "model_names": model_names or {},
        "agent_id": str(session.agent_id) if session.agent_id else None,
        "agent_ids": session.agent_ids or [],
        "multi_model": session.multi_model,
        "system_prompt": session.system_prompt,
        "temperature": session.temperature,
        "chat_type": session.chat_type,
        "project_slug": session.project_slug,
        "task_id": session.task_id,
        "unread_count": session.unread_count,
        "protocol_state": session.protocol_state,
        "message_count": len(msgs),
        "created_at": _ts(session.created_at),
        "updated_at": _ts(session.updated_at),
        "last_message": last_msg,
    }


async def _build_model_names(model_ids: list[str], db: AsyncIOMotorDatabase) -> dict[str, str]:
    """Build a map of model_id -> display name for all model_ids in a session."""
    names = {}
    if not model_ids:
        return names
    agent_svc = AgentService(db)
    model_svc = ModelConfigService(db)

    uuids_to_lookup = []
    for mid in model_ids:
        if mid.startswith("agent:"):
            try:
                aid = str(uuid.UUID(mid[6:]))
                agent = await agent_svc.get_by_id(aid)
                names[mid] = f"🤖 {agent.name}" if agent else mid
            except Exception:
                names[mid] = mid
        elif mid.startswith("ollama:"):
            names[mid] = mid[7:]
        else:
            try:
                uuid.UUID(mid)
                uuids_to_lookup.append(mid)
            except ValueError:
                names[mid] = mid

    for uid in uuids_to_lookup:
        mc = await model_svc.get_by_id(uid)
        if mc:
            names[uid] = mc.name or mc.model_id
        else:
            names[uid] = f"⚠ Unknown ({uid[:8]}…)"

    for mid in model_ids:
        if mid not in names:
            names[mid] = f"⚠ Unknown ({mid[:8]}…)"
    return names


def _message_to_response(msg: MongoChatMessage) -> dict:
    return {
        "id": str(msg.id),
        "role": msg.role,
        "content": msg.content,
        "model_name": msg.model_name,
        "model_responses": msg.model_responses,
        "total_tokens": msg.total_tokens,
        "duration_ms": msg.duration_ms,
        "metadata": msg.metadata,
        "created_at": _ts(msg.created_at),
    }


async def _resolve_model(model_id_str: str, db: AsyncIOMotorDatabase) -> tuple[str, str, str, str | None]:
    """Resolve a model_id string to (provider, base_url, model_name, api_key)."""
    if model_id_str.startswith("ollama:"):
        model_name = model_id_str[7:]
        settings = get_settings()
        return ("ollama", settings.OLLAMA_BASE_URL, model_name, None)

    try:
        uid = str(uuid.UUID(model_id_str))
    except ValueError:
        settings = get_settings()
        return ("ollama", settings.OLLAMA_BASE_URL, model_id_str, None)

    model_svc = ModelConfigService(db)
    mc = await model_svc.get_by_id(uid)
    if not mc:
        all_models = await model_svc.get_all(filter={"is_active": True}, limit=1)
        mc = all_models[0] if all_models else None
        if not mc:
            raise HTTPException(status_code=404, detail=f"Model config {model_id_str} not found and no active models available")

    if mc.provider == "ollama":
        settings = get_settings()
        return (mc.provider, settings.OLLAMA_BASE_URL, mc.model_id, mc.api_key)

    return (mc.provider, mc.base_url, mc.model_id, mc.api_key)


async def _remap_model_id(model_id_str: str, db: AsyncIOMotorDatabase) -> str | None:
    """Try to remap a stale model_id to a valid one."""
    if model_id_str.startswith("ollama:") or model_id_str.startswith("agent:"):
        return None

    try:
        uid = str(uuid.UUID(model_id_str))
    except ValueError:
        return None

    model_svc = ModelConfigService(db)
    mc = await model_svc.get_by_id(uid)
    if mc:
        return None  # Still valid

    all_active = await model_svc.get_all(filter={"is_active": True}, limit=1)
    if all_active:
        return str(all_active[0].id)
    return None


async def _validate_and_remap_model_ids(model_ids: list[str], db: AsyncIOMotorDatabase,
                                        session: MongoChatSession = None) -> list[str]:
    """Validate model_ids and remap any stale UUIDs."""
    if not model_ids:
        return model_ids

    new_ids = []
    changed = False
    for mid in model_ids:
        if mid.startswith("agent:"):
            new_ids.append(mid)
            continue
        remapped = await _remap_model_id(mid, db)
        if remapped is not None:
            new_ids.append(remapped)
            changed = True
        else:
            new_ids.append(mid)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for mid in new_ids:
        if mid not in seen:
            seen.add(mid)
            deduped.append(mid)

    if changed and session is not None:
        await ChatSessionService(db).update(session.id, {"model_ids": deduped})
        session.model_ids = deduped

    return deduped


async def _chat_with_model(
    provider: str, base_url: str, model_name: str, api_key: str | None,
    messages: list[dict], params: GenerationParams | None = None,
) -> LLMResponse:
    """Send chat to a single model and return response."""
    llm_messages = [Message(role=m["role"], content=m["content"]) for m in messages]
    if params is None:
        params = GenerationParams()

    if provider == "ollama":
        llm = OllamaProvider(base_url)
    else:
        llm = OpenAICompatibleProvider(base_url, api_key)

    return await llm.chat(model_name, llm_messages, params)


# ── Endpoints ────────────────────────────────────────────

@router.get("/available-models")
async def get_available_models(
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List available models (running ollama + active API models) and all agents."""
    models = []
    settings = get_settings()

    # 1. Get running ollama model names
    running_ollama_names = set()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/ps")
            if r.status_code == 200:
                for om in r.json().get("models", []):
                    running_ollama_names.add(om.get("name", ""))
    except Exception:
        pass

    # 2. From model_configs: active non-ollama always, ollama only if running
    model_svc = ModelConfigService(db)
    all_configs = await model_svc.get_all(filter={"is_active": True}, limit=500)
    registered_ollama_names = set()
    for mc in all_configs:
        if mc.provider == "ollama":
            registered_ollama_names.add(mc.model_id)
            if mc.model_id not in running_ollama_names:
                continue
        models.append({
            "id": str(mc.id),
            "name": mc.name,
            "model_id": mc.model_id,
            "provider": mc.provider,
            "type": "model",
        })

    # 3. Running ollama models not registered in model_configs
    for name in running_ollama_names:
        if name not in registered_ollama_names:
            models.append({
                "id": f"ollama:{name}",
                "name": name,
                "model_id": name,
                "provider": "ollama",
                "type": "model",
            })

    # 4. Only enabled agents
    agent_svc = AgentService(db)
    all_agents = await agent_svc.get_all(limit=500)
    for agent in all_agents:
        if not getattr(agent, 'enabled', True):
            continue
        models.append({
            "id": f"agent:{agent.id}",
            "name": f"🤖 {agent.name}",
            "model_id": "",
            "provider": "agent",
            "type": "agent",
        })

    return models


# ── Sessions CRUD ────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    limit: int = Query(50, le=200),
    chat_type: Optional[str] = Query(None, description="Filter by chat type: 'user', 'agent', 'project_task'"),
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List chat sessions, newest first."""
    flt = {}
    if chat_type:
        flt["chat_type"] = chat_type
    sess_svc = ChatSessionService(db)
    msg_svc = ChatMessageService(db)
    sessions = await sess_svc.get_by_user(str(user.id), filter_extra=flt, limit=limit)
    # Sort by updated_at desc (client side)
    sessions.sort(key=lambda s: s.updated_at if s.updated_at else datetime.min, reverse=True)

    # Build model names map for all sessions efficiently
    all_model_ids = set()
    for s in sessions:
        for mid in (s.model_ids or []):
            all_model_ids.add(mid)
    all_names = await _build_model_names(list(all_model_ids), db) if all_model_ids else {}

    # Fetch message counts
    result = []
    for s in sessions:
        msgs = await msg_svc.get_by_session(s.id)
        result.append(_session_to_response(s, msgs, {mid: all_names.get(mid, mid) for mid in (s.model_ids or [])}))
    return result


@router.post("/sessions")
async def create_session(
    body: ChatSessionCreate,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a new chat session."""
    agent_id = None
    agent_ids_raw = []
    model_ids = list(body.model_ids)

    # Collect all agent: prefixed IDs from model_ids
    for mid in model_ids:
        if mid.startswith("agent:"):
            try:
                agent_ids_raw.append(str(uuid.UUID(mid[6:])))
            except ValueError:
                pass

    # Also from explicit fields
    if body.agent_ids:
        for aid in body.agent_ids:
            cleaned = aid.replace("agent:", "")
            try:
                aid_str = str(uuid.UUID(cleaned))
                if aid_str not in agent_ids_raw:
                    agent_ids_raw.append(aid_str)
            except ValueError:
                pass

    if body.agent_id:
        cleaned = body.agent_id.replace("agent:", "")
        try:
            aid_str = str(uuid.UUID(cleaned))
            if aid_str not in agent_ids_raw:
                agent_ids_raw.append(aid_str)
        except ValueError:
            pass

    # Remove agent: entries from model_ids
    model_ids = [m for m in model_ids if not m.startswith("agent:")]

    # Set primary agent_id (first agent for backward compat)
    if agent_ids_raw:
        agent_id = agent_ids_raw[0]

    # Multi-agent mode: if 2+ agents selected, it's always multi_model
    is_multi_agent = len(agent_ids_raw) > 1
    if is_multi_agent:
        body.multi_model = True

    # If agents selected, resolve model(s) for LLM calls
    if agent_ids_raw:
        if not model_ids:
            agent_svc = AgentService(db)
            agent = await agent_svc.get_by_id(agent_ids_raw[0])
            if agent:
                agent_models = await AgentModelService(db).get_by_agent(agent.id)
                if agent_models:
                    model_ids = [str(am.model_config_id) for am in sorted(agent_models, key=lambda x: x.priority)]
                elif agent.model_id:
                    model_ids = [str(agent.model_id)]

        model_ids = await _validate_and_remap_model_ids(model_ids, db)

        if not model_ids:
            base_model = await resolve_model_for_role(db, "base")
            if base_model:
                model_ids = [str(base_model.id)]

        if not model_ids:
            raise HTTPException(status_code=400, detail="Agent has no models configured and no base model assigned")

    sess_svc = ChatSessionService(db)
    session = MongoChatSession(
        user_id=str(user.id),
        title=body.title,
        model_ids=model_ids,
        agent_id=agent_id,
        agent_ids=agent_ids_raw,
        multi_model=body.multi_model,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        chat_type=body.chat_type,
        project_slug=body.project_slug,
        task_id=body.task_id,
        unread_count=0,
    )
    session = await sess_svc.create(session)
    model_names = await _build_model_names(session.model_ids or [], db)
    return _session_to_response(session, [], model_names)


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get session with all messages."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")

    session.model_ids = await _validate_and_remap_model_ids(session.model_ids or [], db, session)
    model_names = await _build_model_names(session.model_ids or [], db)
    msgs = await ChatMessageService(db).get_by_session(session.id)
    msgs.sort(key=lambda m: m.created_at if m.created_at else datetime.min)
    data = _session_to_response(session, msgs, model_names)
    data["messages"] = [_message_to_response(m) for m in msgs]
    return data


@router.put("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: ChatSessionUpdate,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update session settings."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")

    update_data = {}
    if body.title is not None:
        update_data["title"] = body.title
    if body.model_ids is not None:
        update_data["model_ids"] = body.model_ids
    if body.multi_model is not None:
        update_data["multi_model"] = body.multi_model
    if body.system_prompt is not None:
        update_data["system_prompt"] = body.system_prompt
    if body.temperature is not None:
        update_data["temperature"] = body.temperature
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        session = await sess_svc.update(session_id, update_data)

    model_names = await _build_model_names(session.model_ids or [], db)
    msgs = await ChatMessageService(db).get_by_session(session.id)
    return _session_to_response(session, msgs, model_names)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a chat session and all its messages."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    await ChatMessageService(db).delete_by_session(session_id)
    await sess_svc.delete(session_id)
    return {"message": "Session deleted"}


@router.post("/sessions/{session_id}/mark-read")
async def mark_session_as_read(
    session_id: str,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Mark a chat session as read (reset unread count)."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    await sess_svc.update(session_id, {"unread_count": 0})
    return {"message": "Session marked as read", "unread_count": 0}


# ── Send Message ─────────────────────────────────────────

# ── Re-exports from AgentChatEngine for backward compatibility ──
# (autonomous_runner.py imports these from here)
_load_agent_protocols = AgentChatEngine.load_agent_protocols
_load_agent_skills = AgentChatEngine.load_agent_skills
_execute_skill = AgentChatEngine.execute_skill


async def create_agent_error(
    db: AsyncIOMotorDatabase,
    agent_id: str,
    error_type: str,
    message: str,
    source: str = "autonomous",
    context: dict | None = None,
):
    """Create an AgentError record in MongoDB."""
    err = MongoAgentError(
        agent_id=str(agent_id),
        error_type=error_type,
        source=source,
        message=message,
        context=context,
    )
    return await AgentErrorService(db).create(err)


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Send a message and get a response with protocol execution support."""
    sess_svc = ChatSessionService(db)
    msg_svc = ChatMessageService(db)
    agent_svc = AgentService(db)

    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")

    # Resolve agent object if this is an agent session
    agent = None
    if session.agent_id:
        agent = await agent_svc.get_by_id(session.agent_id)

    model_ids = body.model_ids or session.model_ids or []
    model_ids = [m for m in model_ids if not m.startswith("agent:")]
    model_ids = await _validate_and_remap_model_ids(model_ids, db, session)
    if not model_ids:
        if agent:
            agent_models = await AgentModelService(db).get_by_agent(agent.id)
            if agent_models:
                model_ids = [str(am.model_config_id) for am in sorted(agent_models, key=lambda x: x.priority)]
                model_ids = await _validate_and_remap_model_ids(model_ids, db)
            elif agent.model_id:
                model_ids = [str(agent.model_id)]
                model_ids = await _validate_and_remap_model_ids(model_ids, db)
    
    # Filter out non-running Ollama models for agent chats
    if model_ids and agent:
        filtered_model_ids = []
        model_svc = ModelConfigService(db)
        settings = get_settings()
        
        # Get list of running Ollama models
        running_ollama_names = set()
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/ps")
                if r.status_code == 200:
                    for om in r.json().get("models", []):
                        running_ollama_names.add(om.get("name", ""))
        except Exception:
            pass
        
        # Check each model - keep only running Ollama models or non-Ollama models
        for mid in model_ids:
            if mid.startswith("ollama:"):
                model_name = mid[7:]
                if model_name in running_ollama_names:
                    filtered_model_ids.append(mid)
            else:
                try:
                    uid = str(uuid.UUID(mid))
                    mc = await model_svc.get_by_id(uid)
                    if mc:
                        if mc.provider == "ollama":
                            if mc.model_id in running_ollama_names:
                                filtered_model_ids.append(mid)
                        else:
                            filtered_model_ids.append(mid)
                    else:
                        filtered_model_ids.append(mid)
                except ValueError:
                    filtered_model_ids.append(mid)
        
        model_ids = filtered_model_ids
    
    if not model_ids:
        base_model = await resolve_model_for_role(db, "base")
        if base_model:
            model_ids = [str(base_model.id)]
    if not model_ids:
        raise HTTPException(status_code=400, detail="No models selected for this chat")

    # Save user message
    user_msg = MongoChatMessage(
        session_id=session.id,
        role="user",
        content=body.content,
    )
    user_msg = await msg_svc.create(user_msg)

    # ── Initialize thinking tracker (only for agent sessions) ──
    tracker = None
    is_agent_session = bool(agent)
    if is_agent_session:
        tracker = ThinkingTracker(db, session.agent_id, session.id, body.content)
        await tracker.start()

    # Build generation params — agent's file settings are source of truth
    gen_params = GenerationParams(temperature=session.temperature)
    system_prompt = session.system_prompt
    agent_ctx = None  # AgentContext from engine
    engine_result = None  # EngineResult if engine was used
    llm_calls_count = 0
    _resolved_model_name = None

    try:
        engine = AgentChatEngine(db)

        if is_agent_session:
            # ── Step: Load agent context via engine ──
            if tracker:
                tracker.start_step_timer()
            agent_ctx = await engine.load_agent_context(agent.id)
            gen_params = agent_ctx.gen_params

            if tracker:
                await tracker.step(
                    "config_load", "Load agent configuration",
                    input_data={"agent_name": agent_ctx.agent.name},
                    output_data={
                        "has_system_prompt": bool(agent_ctx.base_system_prompt),
                        "system_prompt_length": len(agent_ctx.base_system_prompt),
                        "gen_params": {
                            "temperature": gen_params.temperature,
                            "top_p": gen_params.top_p,
                            "top_k": gen_params.top_k,
                            "max_tokens": gen_params.max_tokens,
                            "num_ctx": gen_params.num_ctx,
                        },
                        "protocols_count": len(agent_ctx.protocols),
                        "protocols": [p.get("name", "?") for p in agent_ctx.protocols],
                        "skills_count": len(agent_ctx.skills),
                        "skills": [s.get("name", "?") for s in agent_ctx.skills],
                        "has_beliefs": bool(agent_ctx.beliefs),
                        "has_aspirations": bool(agent_ctx.aspirations),
                    },
                    duration_ms=tracker.elapsed_step_ms(),
                )

            # ── Step: Load project/task context (AIS-34) ──
            if session.project_slug or session.task_id:
                if tracker:
                    tracker.start_step_timer()

                context_summary_parts = []

                if session.project_slug:
                    try:
                        proj_ctx_skill = any(s["name"] == "project_context_build" for s in agent_ctx.skills)
                        if proj_ctx_skill:
                            proj_result = await engine.execute_skill(
                                "project_context_build",
                                {"project_slug": session.project_slug, "max_recent_logs": 30},
                                agent_ctx.skills,
                            )
                            if "result" in proj_result:
                                project_context = proj_result["result"]
                                proj_info = project_context.get("project", {})
                                context_summary_parts.append(
                                    f"📁 Project: {proj_info.get('name')} ({session.project_slug})\n"
                                    f"   Goals: {proj_info.get('goals', 'N/A')[:200]}\n"
                                    f"   Tech Stack: {', '.join(proj_info.get('tech_stack', []))}\n"
                                    f"   Tasks: {project_context.get('task_stats', {}).get('total', 0)} total, "
                                    f"{project_context.get('task_stats', {}).get('in_progress', 0)} in progress\n"
                                    f"   Files: {project_context.get('file_tree', {}).get('total_files', 0)}"
                                )
                    except Exception:
                        pass

                if session.task_id and session.project_slug:
                    try:
                        task_ctx_skill = any(s["name"] == "task_context_build" for s in agent_ctx.skills)
                        if task_ctx_skill:
                            task_result = await engine.execute_skill(
                                "task_context_build",
                                {"project_slug": session.project_slug, "task_id": session.task_id},
                                agent_ctx.skills,
                            )
                            if "result" in task_result:
                                task_context = task_result["result"]
                                task_info = task_context.get("task", {})
                                context_summary_parts.append(
                                    f"\n📋 Current Task: {task_info.get('key')} - {task_info.get('title')}\n"
                                    f"   Status: {task_info.get('status')} | Priority: {task_info.get('priority')}\n"
                                    f"   Description: {task_info.get('description', 'N/A')[:300]}\n"
                                    f"   Comments: {len(task_context.get('comments', []))}, "
                                    f"Related Files: {len(task_context.get('related_files', []))}"
                                )
                    except Exception:
                        pass

                if context_summary_parts:
                    context_summary = "\n\n## Current Work Context\n\n" + "\n".join(context_summary_parts)
                    agent_ctx.base_system_prompt += context_summary

                if tracker:
                    await tracker.step(
                        "project_task_context", "Load project/task context",
                        output_data={
                            "has_project_context": bool(context_summary_parts),
                            "context_summary_length": sum(len(p) for p in context_summary_parts),
                            "context_parts": context_summary_parts,
                        },
                        duration_ms=tracker.elapsed_step_ms(),
                    )
            else:
                # No specific project — load general overview of active projects + agent tasks
                if tracker:
                    tracker.start_step_timer()

                general_context = await engine.load_general_context_overview(str(session.agent_id))
                if general_context:
                    agent_ctx.base_system_prompt += general_context

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

            # ── Step: Build system prompt via engine ──
            protocol_state = session.protocol_state or {}
            current_todo = protocol_state.get("todo_list")
            delegation_stack = protocol_state.get("delegation_stack", [])
            if not delegation_stack and protocol_state.get("active_child_protocol"):
                delegation_stack = [protocol_state["active_child_protocol"]]

            if tracker:
                tracker.start_step_timer()

            system_prompt = engine.build_system_prompt(
                agent_ctx,
                current_todo=current_todo,
                delegation_stack=delegation_stack,
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

        # Build conversation history
        existing_msgs = await msg_svc.get_by_session(session.id)
        existing_msgs.sort(key=lambda m: m.created_at if m.created_at else datetime.min)

        # Check if auto-summarization is needed (AIS-35)
        if should_summarize_session(existing_msgs, context_limit=gen_params.num_ctx or 32768):
            asyncio.create_task(create_summary(session, existing_msgs, db))

        history = await get_session_messages_for_llm(session, existing_msgs, system_prompt)
        history.append({"role": "user", "content": body.content})

        if tracker:
            await tracker.step(
                "history_build", "Build conversation history",
                output_data={
                    "history_messages": len(history),
                    "total_chars": sum(len(m["content"]) for m in history),
                    "has_summary": bool(session.summary),
                    "messages": [
                        {"role": m["role"], "content_length": len(m["content"]), "content": m["content"]}
                        for m in history
                    ],
                },
            )

        start = time.monotonic()

        # ── Step: LLM inference ──
        if tracker:
            tracker.start_step_timer()

        # Check for multi-agent mode
        is_multi_agent = len(session.agent_ids or []) > 1

        if is_multi_agent:
            # Multi-agent chat: each agent responds independently, first synthesizes
            bare_history = []
            for msg in existing_msgs:
                if msg.role != "system" and msg.id != user_msg.id:
                    bare_history.append({"role": msg.role, "content": msg.content})
            bare_history.append({"role": "user", "content": body.content})

            response_data = await _multi_agent_chat(
                session.agent_ids, body.content, bare_history, db, session.temperature
            )
            llm_calls_count = len(session.agent_ids) + 1
            _resolved_model_name = response_data.get("model_name")
            llm_duration_ms = int((time.monotonic() - start) * 1000)

        elif session.multi_model and len(model_ids) > 1:
            response_data = await _multi_model_chat(model_ids, history, gen_params, db)
            llm_calls_count = len(model_ids) + 1
            _resolved_model_name = response_data.get("model_name")
            llm_duration_ms = int((time.monotonic() - start) * 1000)

        elif is_agent_session and agent_ctx:
            # ── Single-agent chat via staged pipeline ──
            # Build clean conversation history (user/assistant only, no system, no current msg)
            staged_history = []
            for msg in existing_msgs:
                if msg.role in ("user", "assistant") and msg.id != user_msg.id:
                    staged_history.append({"role": msg.role, "content": msg.content})

            # Include summary in system prompt if present
            staged_system = system_prompt or ""
            if session.summary:
                staged_system += (
                    f"\n\n**Previous conversation summary:**\n\n{session.summary}"
                )

            try:
                engine_result = await engine.generate_staged(
                    user_input=body.content,
                    history=staged_history,
                    system_prompt=staged_system,
                    agent_context=agent_ctx,
                    model_id=model_ids[0] if model_ids else None,
                    tracker=tracker,
                )
            except Exception as e:
                if tracker:
                    await tracker.step(
                        "llm_call", f"LLM call failed",
                        status="error",
                        error_message=str(e),
                        duration_ms=tracker.elapsed_step_ms(),
                    )
                    await tracker.fail(f"Model error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Model error: {str(e)}")

            llm_calls_count = engine_result.llm_calls_count
            _resolved_model_name = engine_result.model_name
            llm_duration_ms = engine_result.duration_ms

            response_data = {
                "content": engine_result.raw_content,
                "model_name": engine_result.model_name,
                "model_responses": None,
                "total_tokens": engine_result.total_tokens,
                "prompt_tokens": engine_result.prompt_tokens,
                "completion_tokens": engine_result.completion_tokens,
            }

        else:
            # Non-agent single-model chat
            model_id = model_ids[0]
            provider, base_url, model_name, api_key = await _resolve_model(model_id, db)
            _resolved_model_name = model_name
            try:
                llm_resp = await _chat_with_model(
                    provider, base_url, model_name, api_key,
                    history, gen_params,
                )
            except Exception as e:
                if tracker:
                    await tracker.step(
                        "llm_call", f"LLM call to {model_name}",
                        input_data={"model": model_name, "provider": provider, "history_len": len(history)},
                        status="error",
                        error_message=str(e),
                        duration_ms=tracker.elapsed_step_ms(),
                    )
                    await tracker.fail(f"Model error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Model error: {str(e)}")

            llm_calls_count = 1
            llm_duration_ms = int((time.monotonic() - start) * 1000)
            response_data = {
                "content": llm_resp.content,
                "model_name": model_name,
                "model_responses": None,
                "total_tokens": llm_resp.total_tokens,
                "prompt_tokens": getattr(llm_resp, "prompt_tokens", 0),
                "completion_tokens": getattr(llm_resp, "completion_tokens", 0),
            }

        if tracker:
            # Staged pipeline already recorded its own detailed steps,
            # so we record a summary "llm_call" step only for non-staged paths
            is_staged = engine_result and engine_result.metadata.get("pipeline") == "staged"
            if not is_staged:
                await tracker.step(
                    "llm_call", f"LLM inference ({_resolved_model_name})",
                    input_data={
                        "model": _resolved_model_name,
                        "history_messages": len(history),
                        "multi_model": bool(session.multi_model and len(model_ids) > 1),
                    },
                    output_data={
                        "response_length": len(response_data["content"]),
                        "response": response_data["content"],
                        "total_tokens": response_data.get("total_tokens", 0),
                        "prompt_tokens": response_data.get("prompt_tokens", 0),
                        "completion_tokens": response_data.get("completion_tokens", 0),
                    },
                    duration_ms=llm_duration_ms,
                )

        elapsed_ms = llm_duration_ms

        # ── Protocol response parsing (agent sessions with engine result) ──
        # Skip for staged pipeline (it has its own plan/execution, not protocol markers)
        msg_metadata = {}
        llm_content = response_data["content"]
        is_staged = engine_result and engine_result.metadata.get("pipeline") == "staged"

        if engine_result and agent_ctx and agent_ctx.protocols and not is_staged:
            # Engine already parsed — use engine_result directly
            if tracker:
                tracker.start_step_timer()

            protocol_state = session.protocol_state or {}

            # 1. Todo list from engine result
            if engine_result.todo_list:
                protocol_state["todo_list"] = engine_result.todo_list
                msg_metadata["todo_list"] = engine_result.todo_list

                try:
                    from app.services.todo_sync_service import sync_todos_to_tasks
                    updated_map = await sync_todos_to_tasks(
                        db, session.agent_id, engine_result.todo_list,
                        todo_task_map=protocol_state.get("todo_task_map"),
                    )
                    protocol_state["todo_task_map"] = updated_map
                except Exception as e:
                    print(f"[CHAT] Warning: failed to sync todos to tasks: {e}")

            # 2. Delegation from engine result
            if "delegation_stack" not in protocol_state:
                old_child = protocol_state.get("active_child_protocol")
                protocol_state["delegation_stack"] = [old_child] if old_child else []

            if engine_result.delegate_done:
                if protocol_state["delegation_stack"]:
                    finished_protocol = protocol_state["delegation_stack"].pop()
                    msg_metadata["delegate_done_from"] = finished_protocol
                    msg_metadata["delegate_done_summary"] = engine_result.delegate_done.get("summary", "")
                    if engine_result.delegate_done.get("result"):
                        msg_metadata["delegate_result"] = engine_result.delegate_done["result"]
                protocol_state["active_child_protocol"] = (
                    protocol_state["delegation_stack"][-1]
                    if protocol_state["delegation_stack"] else None
                )

            if engine_result.delegate_to:
                protocol_state["delegation_stack"].append(engine_result.delegate_to)
                protocol_state["active_child_protocol"] = engine_result.delegate_to
                msg_metadata["delegated_to"] = engine_result.delegate_to

            # 3. Skill results from engine
            if engine_result.skill_results:
                msg_metadata["skill_results"] = engine_result.skill_results

            if tracker:
                await tracker.step(
                    "response_parse", "Parse LLM response (todo, delegation, skills)",
                    output_data={
                        "todo_found": bool(engine_result.todo_list),
                        "todo_list": engine_result.todo_list,
                        "delegation_found": bool(engine_result.delegate_to),
                        "delegation_target": engine_result.delegate_to,
                        "delegate_done": bool(engine_result.delegate_done),
                        "delegate_done_data": engine_result.delegate_done,
                        "delegation_stack": protocol_state.get("delegation_stack", []),
                        "skill_calls_found": len(engine_result.skill_results),
                        "skill_results": engine_result.skill_results,
                        "clean_content": engine_result.content,
                        "raw_content": engine_result.raw_content,
                    },
                    duration_ms=tracker.elapsed_step_ms(),
                )

            # Save protocol state
            if tracker:
                tracker.start_step_timer()
            await sess_svc.update(session.id, {
                "protocol_state": protocol_state,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            if tracker:
                await tracker.step(
                    "protocol_update", "Save protocol state",
                    output_data={
                        "has_todo": bool(protocol_state.get("todo_list")),
                        "todo_list": protocol_state.get("todo_list"),
                        "active_child": protocol_state.get("active_child_protocol"),
                        "delegation_stack": protocol_state.get("delegation_stack", []),
                        "full_protocol_state": protocol_state,
                    },
                    duration_ms=tracker.elapsed_step_ms(),
                )

        elif session.agent_id and not is_agent_session:
            # Legacy fallback: parse protocols manually for non-engine paths
            pass

        # Add staged pipeline metadata if available
        if is_staged and engine_result:
            staged_meta = engine_result.metadata or {}
            if staged_meta.get("analysis"):
                msg_metadata["staged_analysis"] = staged_meta["analysis"]
            if staged_meta.get("plan"):
                msg_metadata["staged_plan"] = staged_meta["plan"]
            if staged_meta.get("execution"):
                msg_metadata["staged_execution"] = staged_meta["execution"]

        # Save assistant message
        display_model_name = response_data.get("model_name")
        if is_multi_agent:
            pass
        elif is_agent_session and agent:
            agent_display = agent.name
            if display_model_name:
                display_model_name = f"{agent_display} ({display_model_name})"
            else:
                display_model_name = agent_display

        assistant_msg = MongoChatMessage(
            session_id=session.id,
            role="assistant",
            content=response_data["content"],
            model_name=display_model_name,
            model_responses=response_data.get("model_responses"),
            total_tokens=response_data.get("total_tokens", 0),
            duration_ms=elapsed_ms,
            metadata=msg_metadata or None,
        )
        assistant_msg = await msg_svc.create(assistant_msg)

        # ── Complete thinking log ──
        if tracker:
            await tracker.complete(
                response_data["content"],
                message_id=assistant_msg.id,
                model_name=_resolved_model_name,
                total_tokens=response_data.get("total_tokens", 0),
                prompt_tokens=response_data.get("prompt_tokens", 0),
                completion_tokens=response_data.get("completion_tokens", 0),
                llm_calls_count=llm_calls_count,
            )

        # Auto-title: if first user message, summarize to title
        all_msgs = await msg_svc.get_by_session(session.id)
        if len(all_msgs) <= 2:
            title = body.content[:60]
            if len(body.content) > 60:
                title += "…"
            await sess_svc.update(session.id, {
                "title": title,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        return _message_to_response(assistant_msg)

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        if tracker:
            await tracker.fail(str(e))
        raise


async def _multi_model_chat(
    model_ids: list[str],
    history: list[dict],
    params: GenerationParams,
    db: AsyncIOMotorDatabase,
) -> dict:
    """
    Multi-model mode: query all models in parallel, then synthesize.
    Like Grok's multi-model — each model answers, then a synthesizer combines.
    """
    # Resolve all models
    resolved = []
    for mid in model_ids:
        try:
            provider, base_url, model_name, api_key = await _resolve_model(mid, db)
            resolved.append((mid, provider, base_url, model_name, api_key))
        except Exception:
            continue

    if not resolved:
        raise HTTPException(status_code=400, detail="No valid models could be resolved")

    # Query all models in parallel
    async def query_one(provider, base_url, model_name, api_key):
        try:
            resp = await _chat_with_model(
                provider, base_url, model_name, api_key,
                history, params,
            )
            return {"model": model_name, "content": resp.content, "tokens": resp.total_tokens}
        except Exception as e:
            return {"model": model_name, "content": f"[Error: {str(e)}]", "tokens": 0, "error": True}

    tasks = [query_one(p, b, m, a) for (_, p, b, m, a) in resolved]
    results = await asyncio.gather(*tasks)

    model_responses = {}
    total_tokens = 0
    for r in results:
        model_responses[r["model"]] = r["content"]
        total_tokens += r.get("tokens", 0)

    # If only 1 model succeeded, return its response directly
    successful = [r for r in results if not r.get("error")]
    if len(successful) == 1:
        return {
            "content": successful[0]["content"],
            "model_name": successful[0]["model"],
            "model_responses": model_responses,
            "total_tokens": total_tokens,
        }

    # Synthesize responses using the first model
    if successful:
        synth_provider, synth_base_url, synth_model, synth_api_key = (
            resolved[0][1], resolved[0][2], resolved[0][3], resolved[0][4]
        )

        # Build synthesis prompt
        synthesis_parts = []
        for r in successful:
            synthesis_parts.append(f"=== Response from {r['model']} ===\n{r['content']}")

        synthesis_prompt = (
            "You are a synthesis assistant. Below are responses from multiple AI models to the same question. "
            "Analyze all responses, combine the best insights, resolve any contradictions, "
            "and produce a single comprehensive answer. Be concise but thorough.\n\n"
            + "\n\n".join(synthesis_parts)
            + "\n\n=== Your synthesized answer ==="
        )

        synth_history = [{"role": "user", "content": synthesis_prompt}]

        try:
            synth_resp = await _chat_with_model(
                synth_provider, synth_base_url, synth_model, synth_api_key,
                synth_history, params,
            )
            total_tokens += synth_resp.total_tokens

            return {
                "content": synth_resp.content,
                "model_name": f"multi({','.join(r['model'] for r in successful)})",
                "model_responses": model_responses,
                "total_tokens": total_tokens,
            }
        except Exception:
            # Fallback: return concatenated responses
            pass

    # Fallback: format all responses
    formatted = "\n\n".join(
        f"**{r['model']}:**\n{r['content']}" for r in results
    )
    return {
        "content": formatted,
        "model_name": "multi",
        "model_responses": model_responses,
        "total_tokens": total_tokens,
    }


async def _build_agent_context(agent_id_str: str, db: AsyncIOMotorDatabase, session_temperature: float = 0.7) -> dict:
    """Build full agent context (system prompt, gen params, model) for multi-agent chat."""
    agent_svc = AgentService(db)
    agent = await agent_svc.get_by_id(agent_id_str)
    if not agent:
        return None

    agent_name = agent.name
    agent_config = read_agent_config(agent_name)
    base_system_prompt = agent_config.get("system_prompt", "")

    agent_settings = read_agent_settings(agent_name)
    gen_params = GenerationParams(temperature=session_temperature)
    if agent_settings:
        gen_params = GenerationParams(
            temperature=agent_settings.get("temperature", session_temperature),
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

    protocols = await _load_agent_protocols(agent.id, db)
    skills = await _load_agent_skills(agent.id, db, agent=agent)
    beliefs = read_beliefs(agent_name)
    from app.api.agent_aspirations import read_aspirations
    aspirations = read_aspirations(agent_name)

    if protocols:
        system_prompt = build_agent_system_prompt(
            base_system_prompt=base_system_prompt,
            agent_name=agent_name,
            protocols=protocols,
            available_skills=skills or None,
            beliefs=beliefs,
            aspirations=aspirations,
        )
    else:
        system_prompt = base_system_prompt

    # Resolve model for this agent
    model_id = None
    agent_models = await AgentModelService(db).get_by_agent(agent.id)
    if agent_models:
        model_id = str(sorted(agent_models, key=lambda x: x.priority)[0].model_config_id)
    elif agent.model_id:
        model_id = str(agent.model_id)

    if not model_id:
        base_model = await resolve_model_for_role(db, "base")
        if base_model:
            model_id = str(base_model.id)

    return {
        "agent_id": agent_id_str,
        "agent_name": agent_name,
        "system_prompt": system_prompt,
        "gen_params": gen_params,
        "model_id": model_id,
    }


async def _multi_agent_chat(
    agent_ids: list[str],
    user_content: str,
    conversation_history: list[dict],
    db: AsyncIOMotorDatabase,
    session_temperature: float = 0.7,
) -> dict:
    """
    Multi-agent mode (like GROK multi-model):
    1. Each agent answers independently with its own system prompt
    2. First agent synthesizes all responses into a final answer
    """
    # Build context for each agent
    agent_contexts = []
    for aid in agent_ids:
        ctx = await _build_agent_context(aid, db, session_temperature)
        if ctx and ctx.get("model_id"):
            agent_contexts.append(ctx)

    if not agent_contexts:
        raise HTTPException(status_code=400, detail="No agents could be resolved")

    # Query each agent in parallel
    async def query_agent(ctx: dict):
        try:
            # Build per-agent history with agent's own system prompt
            history = []
            if ctx["system_prompt"]:
                history.append({"role": "system", "content": ctx["system_prompt"]})
            # Add previous conversation (without system messages)
            for msg in conversation_history:
                if msg["role"] != "system":
                    history.append(msg)

            provider, base_url, model_name, api_key = await _resolve_model(ctx["model_id"], db)
            resp = await _chat_with_model(
                provider, base_url, model_name, api_key,
                history, ctx["gen_params"],
            )
            return {
                "agent_name": ctx["agent_name"],
                "model": model_name,
                "content": resp.content,
                "tokens": resp.total_tokens,
            }
        except Exception as e:
            return {
                "agent_name": ctx["agent_name"],
                "model": ctx.get("model_id", "?"),
                "content": f"[Error: {str(e)}]",
                "tokens": 0,
                "error": True,
            }

    tasks = [query_agent(ctx) for ctx in agent_contexts]
    results = await asyncio.gather(*tasks)

    # Build model_responses dict (agent_name -> response)
    agent_responses = {}
    total_tokens = 0
    for r in results:
        agent_responses[r["agent_name"]] = r["content"]
        total_tokens += r.get("tokens", 0)

    successful = [r for r in results if not r.get("error")]

    # If only 1 agent succeeded, return directly
    if len(successful) == 1:
        return {
            "content": successful[0]["content"],
            "model_name": f"{successful[0]['agent_name']} ({successful[0]['model']})",
            "model_responses": agent_responses,
            "total_tokens": total_tokens,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

    # Synthesize using the first agent's context
    if successful:
        synth_ctx = agent_contexts[0]
        synth_provider, synth_base_url, synth_model, synth_api_key = await _resolve_model(
            synth_ctx["model_id"], db
        )

        # Build synthesis prompt
        synthesis_parts = []
        for r in successful:
            synthesis_parts.append(f"=== Response from agent \"{r['agent_name']}\" ===\n{r['content']}")

        synthesis_prompt = (
            f"You are {synth_ctx['agent_name']}. "
            "Below are responses from multiple AI agents to the same user question. "
            "Analyze all responses, combine the best insights, resolve any contradictions, "
            "and produce a single comprehensive answer. Be concise but thorough.\n\n"
            + "\n\n".join(synthesis_parts)
            + "\n\n=== Your synthesized answer ==="
        )

        synth_history = []
        if synth_ctx["system_prompt"]:
            synth_history.append({"role": "system", "content": synth_ctx["system_prompt"]})
        synth_history.append({"role": "user", "content": synthesis_prompt})

        try:
            synth_resp = await _chat_with_model(
                synth_provider, synth_base_url, synth_model, synth_api_key,
                synth_history, synth_ctx["gen_params"],
            )
            total_tokens += synth_resp.total_tokens

            agent_names = ", ".join(r["agent_name"] for r in successful)
            return {
                "content": synth_resp.content,
                "model_name": f"multi-agent({agent_names})",
                "model_responses": agent_responses,
                "total_tokens": total_tokens,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        except Exception:
            pass

    # Fallback: format all responses
    formatted = "\n\n".join(
        f"**🤖 {r['agent_name']}:**\n{r['content']}" for r in results
    )
    return {
        "content": formatted,
        "model_name": "multi-agent",
        "model_responses": agent_responses,
        "total_tokens": total_tokens,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


# ── Auto-title ───────────────────────────────────────────

@router.post("/sessions/{session_id}/auto-title")
async def auto_title_session(
    session_id: str,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Generate a title for the session based on its content."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")

    msg_svc = ChatMessageService(db)
    msgs = await msg_svc.get_by_session(session.id)
    msgs.sort(key=lambda m: m.created_at if m.created_at else datetime.min)
    msgs = msgs[:4]
    if not msgs:
        return {"title": session.title}

    summary = "\n".join(f"{m.role}: {m.content[:200]}" for m in msgs)

    model_ids = session.model_ids or []
    if model_ids:
        try:
            provider, base_url, model_name, api_key = await _resolve_model(model_ids[0], db)
            prompt = [{"role": "user", "content": f"Generate a very short title (3-6 words) for this conversation:\n\n{summary}\n\nTitle:"}]
            resp = await _chat_with_model(provider, base_url, model_name, api_key, prompt, GenerationParams(temperature=0.3))
            new_title = resp.content.strip().strip('"').strip("'")[:100]
            await sess_svc.update(session.id, {
                "title": new_title,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            return {"title": new_title}
        except Exception:
            pass

    return {"title": session.title}


# ── Conversation Summarization (AIS-35) ─────────────────

@router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get the current summary for a chat session."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    
    msg_svc = ChatMessageService(db)
    all_messages = await msg_svc.get_by_session(session.id)
    
    return {
        "has_summary": bool(session.summary),
        "summary": session.summary,
        "summary_up_to_message_id": session.summary_up_to_message_id,
        "summary_created_at": session.summary_created_at,
        "summary_token_count": session.summary_token_count,
        "total_messages": len(all_messages),
        "summarized_messages": len([m for m in all_messages if session.summary_created_at and m.created_at <= session.summary_created_at]) if session.summary_created_at else 0,
    }


@router.post("/sessions/{session_id}/summary")
async def trigger_summarization(
    session_id: str,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Manually trigger summarization for a chat session."""
    sess_svc = ChatSessionService(db)
    session = await sess_svc.get_by_id(session_id)
    if not session or session.user_id != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    
    msg_svc = ChatMessageService(db)
    messages = await msg_svc.get_by_session(session.id)
    messages.sort(key=lambda m: m.created_at if m.created_at else datetime.min)
    
    if len(messages) < 10:
        raise HTTPException(status_code=400, detail="Not enough messages to summarize (minimum: 10)")
    
    # Create summary
    summary_text = await create_summary(session, messages, db)
    if not summary_text:
        raise HTTPException(status_code=500, detail="Failed to create summary")
    
    # Reload session to get updated fields
    session = await sess_svc.get_by_id(session_id)
    
    return {
        "success": True,
        "summary": summary_text,
        "summary_token_count": session.summary_token_count,
        "summarized_messages": len([m for m in messages if session.summary_created_at and m.created_at <= session.summary_created_at]),
    }


@router.get("/search")
async def search_chats(
    query: str = Query(..., description="Search query for chat content"),
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Search chat sessions by title, message content, or summary."""
    sessions_collection = db["chat_sessions"]
    messages_collection = db["chat_messages"]
    
    # Search in session titles and summaries
    title_matches = await sessions_collection.find({
        "user_id": str(user.id),
        "$or": [
            {"title": {"$regex": query, "$options": "i"}},
            {"summary": {"$regex": query, "$options": "i"}},
        ]
    }).to_list(length=50)
    
    # Search in message content
    message_matches = await messages_collection.find({
        "content": {"$regex": query, "$options": "i"}
    }).to_list(length=100)
    
    # Get unique session IDs from message matches
    message_session_ids = {msg["session_id"] for msg in message_matches}
    
    # Fetch those sessions
    message_sessions = await sessions_collection.find({
        "_id": {"$in": list(message_session_ids)},
        "user_id": str(user.id),
    }).to_list(length=50)
    
    # Combine and deduplicate
    session_map = {}
    for sess_doc in title_matches + message_sessions:
        session = MongoChatSession.from_mongo(sess_doc)
        if session.id not in session_map:
            session_map[session.id] = {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
                "chat_type": session.chat_type,
                "project_slug": session.project_slug,
                "task_id": session.task_id,
                "has_summary": bool(session.summary),
                "summary_preview": session.summary[:200] if session.summary else None,
            }
    
    results = list(session_map.values())
    results.sort(key=lambda x: x["updated_at"] or x["created_at"], reverse=True)
    
    return {
        "query": query,
        "results": results,
        "count": len(results),
    }


@router.get("/sessions/by-project/{project_slug}")
async def get_project_chats(
    project_slug: str,
    task_id: Optional[str] = None,
    user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get all chat sessions related to a project or specific task."""
    sessions_collection = db["chat_sessions"]
    
    query = {
        "user_id": str(user.id),
        "project_slug": project_slug,
    }
    if task_id:
        query["task_id"] = task_id
    
    session_docs = await sessions_collection.find(query).sort("updated_at", -1).to_list(length=100)
    
    sessions = []
    for doc in session_docs:
        session = MongoChatSession.from_mongo(doc)
        # Get message count
        msg_svc = ChatMessageService(db)
        messages = await msg_svc.get_by_session(session.id)
        
        sessions.append({
            "id": session.id,
            "title": session.title,
            "summary": session.summary[:200] if session.summary else None,
            "message_count": len(messages),
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        })
    
    return {
        "project_slug": project_slug,
        "task_id": task_id,
        "sessions": sessions,
        "count": len(sessions),
    }
