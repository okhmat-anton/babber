import os
import shutil
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models.agent import MongoAgent, MongoAgentModel, MongoAgentProtocol
from app.mongodb.services import (
    AgentService, AgentModelService, AgentProtocolService,
    ThinkingProtocolService, ModelConfigService,
    TaskService, AgentSkillService, AgentErrorService,
)
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse, AgentStatsResponse, AgentModelResponse
from app.schemas.common import MessageResponse
from app.api.agent_files import (
    init_agent_directory, delete_agent_directory, duplicate_agent_directory,
    sync_agent_to_filesystem, read_agent_config, read_agent_settings,
    write_agent_config, write_agent_settings,
)
from app.api.agent_beliefs import read_beliefs

router = APIRouter(prefix="/api/agents", tags=["agents"])


async def _build_agent_response(
    agent: MongoAgent, db: AsyncIOMotorDatabase
) -> dict:
    """Build response dict — DB identity + filesystem settings as source of truth."""
    data = agent.model_dump()
    data["id"] = agent.id

    # Overlay settings from filesystem (source of truth)
    config = read_agent_config(agent.name)
    if config:
        data["description"] = config.get("description", data.get("description", ""))
        data["mission"] = config.get("mission", "")
        data["system_prompt"] = config.get("system_prompt", data.get("system_prompt", ""))

    file_settings = read_agent_settings(agent.name)
    if file_settings:
        for field in ("temperature", "top_p", "top_k", "max_tokens", "num_ctx",
                      "repeat_penalty", "num_predict", "stop", "num_thread", "num_gpu"):
            if field in file_settings:
                data[field] = file_settings[field]

    # Beliefs from beliefs.json
    beliefs = read_beliefs(agent.name)
    data["beliefs"] = beliefs

    # Aspirations from aspirations.json
    from app.api.agent_aspirations import read_aspirations
    aspirations = read_aspirations(agent.name)
    data["aspirations"] = aspirations

    # Thinking protocol (main)
    if agent.thinking_protocol_id:
        tp_svc = ThinkingProtocolService(db)
        tp = await tp_svc.get_by_id(agent.thinking_protocol_id)
        if tp:
            data["thinking_protocol"] = {
                "id": tp.id,
                "name": tp.name,
                "description": tp.description or "",
                "type": tp.type or "standard",
                "steps": tp.steps or [],
            }
        else:
            data["thinking_protocol"] = None
    else:
        data["thinking_protocol"] = None
    data["thinking_protocol_id"] = agent.thinking_protocol_id

    # All assigned protocols (multi-protocol)
    ap_svc = AgentProtocolService(db)
    tp_svc = ThinkingProtocolService(db)
    agent_protocols = await ap_svc.get_by_agent(agent.id)
    protocols_out = []
    for ap in agent_protocols:
        p = await tp_svc.get_by_id(ap.protocol_id)
        if p:
            protocols_out.append({
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "type": p.type or "standard",
                "steps": p.steps or [],
                "is_main": ap.is_main,
                "priority": ap.priority,
            })
    data["protocols"] = protocols_out

    # Agent models
    am_svc = AgentModelService(db)
    mc_svc = ModelConfigService(db)
    agent_models = await am_svc.get_by_agent(agent.id)
    agent_models_out = []
    for am in agent_models:
        mcr = await mc_svc.get_by_id(am.model_config_id)
        agent_models_out.append(AgentModelResponse(
            id=UUID(am.id),
            model_config_id=UUID(am.model_config_id),
            model_name=mcr.model_id if mcr else None,
            model_display_name=mcr.name if mcr else None,
            task_type=am.task_type,
            tags=am.tags or [],
            priority=am.priority,
            created_at=am.created_at,
        ))
    data["agent_models"] = agent_models_out
    return data


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    filter_dict = {}
    if status:
        filter_dict["status"] = status
    agents = await svc.get_all(filter=filter_dict, skip=offset, limit=limit)
    agents.sort(key=lambda a: a.created_at, reverse=True)
    return [await _build_agent_response(a, db) for a in agents]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)

    agent = MongoAgent(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        top_p=body.top_p,
        top_k=body.top_k,
        max_tokens=body.max_tokens,
        num_ctx=body.num_ctx,
        repeat_penalty=body.repeat_penalty,
        num_predict=body.num_predict,
        stop=body.stop or [],
        num_thread=body.num_thread,
        num_gpu=body.num_gpu,
        filesystem_access=body.filesystem_access,
        system_access=body.system_access,
        max_messages_before_response=body.max_messages_before_response,
        self_thinking=body.self_thinking,
        thinking_protocol_id=body.thinking_protocol_id,
        enabled=body.enabled,
    )
    await svc.create(agent)

    # Create agent_model entries
    am_svc = AgentModelService(db)
    for entry in body.models:
        am = MongoAgentModel(
            agent_id=agent.id,
            model_config_id=str(entry.model_config_id),
            task_type=entry.task_type,
            tags=entry.tags,
            priority=entry.priority,
        )
        await am_svc.create(am)

    # Create agent_protocol entries (multi-protocol)
    ap_svc = AgentProtocolService(db)
    if body.protocol_ids:
        for idx, pid in enumerate(body.protocol_ids):
            ap = MongoAgentProtocol(
                agent_id=agent.id,
                protocol_id=pid,
                is_main=(pid == body.thinking_protocol_id),
                priority=idx,
            )
            await ap_svc.create(ap)
    elif body.thinking_protocol_id:
        ap = MongoAgentProtocol(
            agent_id=agent.id,
            protocol_id=body.thinking_protocol_id,
            is_main=True,
            priority=0,
        )
        await ap_svc.create(ap)

    # Write files as source of truth
    init_agent_directory(agent)
    write_agent_config(agent.name, {
        "name": agent.name,
        "description": body.description or "",
        "mission": body.mission or "",
        "system_prompt": body.system_prompt or "",
    })
    write_agent_settings(agent.name, {
        "temperature": body.temperature,
        "top_p": body.top_p,
        "top_k": body.top_k,
        "max_tokens": body.max_tokens,
        "num_ctx": body.num_ctx,
        "repeat_penalty": body.repeat_penalty,
        "num_predict": body.num_predict,
        "stop": body.stop or [],
        "num_thread": body.num_thread,
        "num_gpu": body.num_gpu,
        "principles": [],
    })

    return await _build_agent_response(agent, db)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _build_agent_response(agent, db)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True, exclude={"models", "protocol_ids"})
    old_name = agent.name

    # Build MongoDB update dict
    mongo_update = {}
    for key in ("name", "filesystem_access", "system_access", "self_thinking", "enabled", "messenger_context_limit"):
        if key in update_data:
            mongo_update[key] = update_data[key]
    if "thinking_protocol_id" in update_data:
        val = update_data["thinking_protocol_id"]
        mongo_update["thinking_protocol_id"] = val if val else None

    mongo_update["updated_at"] = datetime.now(timezone.utc).isoformat()

    if mongo_update:
        await svc.update(str(agent_id), mongo_update)

    # Refresh agent
    agent = await svc.get_by_id(str(agent_id))

    # If models list is provided, replace all agent_model entries
    am_svc = AgentModelService(db)
    if body.models is not None:
        await am_svc.delete_by_agent(str(agent_id))
        for entry in body.models:
            am = MongoAgentModel(
                agent_id=str(agent_id),
                model_config_id=str(entry.model_config_id),
                task_type=entry.task_type,
                tags=entry.tags,
                priority=entry.priority,
            )
            await am_svc.create(am)

    # If protocol_ids list is provided, replace all agent_protocol entries
    ap_svc = AgentProtocolService(db)
    if body.protocol_ids is not None:
        await ap_svc.delete_by_agent(str(agent_id))
        main_id = body.thinking_protocol_id if "thinking_protocol_id" in body.model_dump(exclude_unset=True) else agent.thinking_protocol_id
        for idx, pid in enumerate(body.protocol_ids):
            ap = MongoAgentProtocol(
                agent_id=str(agent_id),
                protocol_id=pid,
                is_main=(pid == main_id),
                priority=idx,
            )
            await ap_svc.create(ap)
    elif "thinking_protocol_id" in update_data:
        # Update is_main flags on existing entries
        existing_aps = await ap_svc.get_by_agent(str(agent_id))
        main_val = update_data["thinking_protocol_id"]
        for ap in existing_aps:
            new_is_main = (ap.protocol_id == main_val) if main_val else False
            if ap.is_main != new_is_main:
                await ap_svc.update(ap.id, {"is_main": new_is_main})

    # Handle rename: move directory
    new_name = agent.name
    if new_name != old_name:
        from app.api.agent_files import _get_agent_dir, _ensure_agents_dir
        _ensure_agents_dir()
        old_dir = _get_agent_dir(old_name)
        new_dir = _get_agent_dir(new_name)
        if old_dir.exists():
            shutil.move(str(old_dir), str(new_dir))

    # Write settings to files (source of truth)
    config = read_agent_config(agent.name)
    settings_data = read_agent_settings(agent.name)

    # Merge updated fields into file config
    config_fields = {"name": agent.name}
    if "description" in update_data:
        config_fields["description"] = update_data["description"]
    else:
        config_fields["description"] = config.get("description", agent.description or "")
    if "mission" in update_data:
        config_fields["mission"] = update_data["mission"]
    else:
        config_fields["mission"] = config.get("mission", "")
    if "system_prompt" in update_data:
        config_fields["system_prompt"] = update_data["system_prompt"]
    else:
        config_fields["system_prompt"] = config.get("system_prompt", agent.system_prompt or "")
    write_agent_config(agent.name, config_fields)

    # Merge updated generation params into settings file
    gen_fields = ("temperature", "top_p", "top_k", "max_tokens", "num_ctx",
                  "repeat_penalty", "num_predict", "stop", "num_thread", "num_gpu")
    new_settings = {}
    for f in gen_fields:
        if f in update_data:
            new_settings[f] = update_data[f]
        elif f in settings_data:
            new_settings[f] = settings_data[f]
        else:
            new_settings[f] = getattr(agent, f, None)
    write_agent_settings(agent.name, new_settings)

    return await _build_agent_response(agent, db)


@router.delete("/{agent_id}", response_model=MessageResponse)
async def delete_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent_name = agent.name

    # Delete related data
    await AgentModelService(db).delete_by_agent(str(agent_id))
    await AgentProtocolService(db).delete_by_agent(str(agent_id))
    await AgentErrorService(db).delete_by_agent(str(agent_id))
    await svc.delete(str(agent_id))
    delete_agent_directory(agent_name)
    return MessageResponse(message="Agent deleted")


@router.post("/{agent_id}/start", response_model=AgentResponse)
async def start_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = await svc.update(str(agent_id), {
        "status": "running",
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return await _build_agent_response(agent, db)


@router.post("/{agent_id}/stop", response_model=AgentResponse)
async def stop_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = await svc.update(str(agent_id), {
        "status": "stopped",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return await _build_agent_response(agent, db)


@router.post("/{agent_id}/pause", response_model=AgentResponse)
async def pause_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = await svc.update(str(agent_id), {
        "status": "paused",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return await _build_agent_response(agent, db)


@router.post("/{agent_id}/resume", response_model=AgentResponse)
async def resume_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent = await svc.update(str(agent_id), {
        "status": "running",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return await _build_agent_response(agent, db)


@router.post("/{agent_id}/duplicate", response_model=AgentResponse, status_code=201)
async def duplicate_agent(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_name = f"{agent.name} (copy)"
    new_agent = MongoAgent(
        name=new_name,
        thinking_protocol_id=agent.thinking_protocol_id,
    )
    await svc.create(new_agent)

    # Duplicate agent_models
    am_svc = AgentModelService(db)
    agent_models = await am_svc.get_by_agent(agent.id)
    for am in agent_models:
        new_am = MongoAgentModel(
            agent_id=new_agent.id,
            model_config_id=am.model_config_id,
            task_type=am.task_type,
            tags=am.tags,
            priority=am.priority,
        )
        await am_svc.create(new_am)

    # Duplicate agent_protocols
    ap_svc = AgentProtocolService(db)
    agent_protocols = await ap_svc.get_by_agent(agent.id)
    for ap in agent_protocols:
        new_ap = MongoAgentProtocol(
            agent_id=new_agent.id,
            protocol_id=ap.protocol_id,
            is_main=ap.is_main,
            priority=ap.priority,
        )
        await ap_svc.create(new_ap)

    # Duplicate filesystem directory
    duplicate_agent_directory(agent.name, new_name)
    config = read_agent_config(new_name)
    config["name"] = new_name
    write_agent_config(new_name, config)

    return await _build_agent_response(new_agent, db)


@router.get("/{agent_id}/stats", response_model=AgentStatsResponse)
async def agent_stats(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    aid = str(agent_id)
    total_tasks = await TaskService(db).count({"agent_id": aid})
    completed = await TaskService(db).count({"agent_id": aid, "status": "completed"})
    failed = await TaskService(db).count({"agent_id": aid, "status": "failed"})
    skills = len(await AgentSkillService(db).get_by_agent(aid))
    errors = await AgentErrorService(db).count({"agent_id": aid})

    return AgentStatsResponse(
        total_tasks=total_tasks,
        completed_tasks=completed,
        failed_tasks=failed,
        total_logs=0,
        total_memories=0,
        total_skills=skills,
    )


# --------------- Avatar Upload ---------------

AVATAR_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
AVATAR_RESIZE_PX = 256


@router.post("/{agent_id}/avatar")
async def upload_avatar(
    agent_id: UUID,
    file: UploadFile = File(...),
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Upload or replace agent avatar."""
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    content_type = file.content_type or ""
    if content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {content_type}. Allowed: {', '.join(AVATAR_ALLOWED_TYPES)}")

    data = await file.read()
    if len(data) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max {AVATAR_MAX_SIZE // (1024*1024)} MB")

    is_gif = content_type == "image/gif"
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
    ext = ext_map.get(content_type, "png")

    base_dir = os.path.join("..", "data", "agents", agent.name)
    os.makedirs(base_dir, exist_ok=True)

    for old in os.listdir(base_dir):
        if old.startswith("avatar."):
            os.remove(os.path.join(base_dir, old))

    avatar_filename = f"avatar.{ext}"
    avatar_path = os.path.join(base_dir, avatar_filename)

    if is_gif:
        with open(avatar_path, "wb") as f:
            f.write(data)
    else:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        if ext == "jpg" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((AVATAR_RESIZE_PX, AVATAR_RESIZE_PX), Image.LANCZOS)
        img.save(avatar_path, quality=90)

    avatar_url = f"/api/uploads/agents/{agent.name}/{avatar_filename}"
    await svc.update(str(agent_id), {"avatar_url": avatar_url})

    return {"avatar_url": avatar_url}


@router.delete("/{agent_id}/avatar")
async def delete_avatar(
    agent_id: UUID,
    _user = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Remove agent avatar."""
    svc = AgentService(db)
    agent = await svc.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    base_dir = os.path.join("..", "data", "agents", agent.name)
    if os.path.isdir(base_dir):
        for old in os.listdir(base_dir):
            if old.startswith("avatar."):
                os.remove(os.path.join(base_dir, old))

    await svc.update(str(agent_id), {"avatar_url": None})
    return {"detail": "Avatar deleted"}
