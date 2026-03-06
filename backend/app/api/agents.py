import os
import shutil
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.agent import Agent
from app.models.agent_model import AgentModel
from app.models.task import Task
from app.models.log import AgentLog
from app.models.memory import Memory
from app.models.skill import AgentSkill
from app.schemas.agent import AgentCreate, AgentUpdate, AgentResponse, AgentStatsResponse, AgentModelResponse
from app.schemas.common import MessageResponse
from app.api.agent_files import (
    init_agent_directory, delete_agent_directory, duplicate_agent_directory,
    sync_agent_to_filesystem, read_agent_config, read_agent_settings,
    write_agent_config, write_agent_settings,
)
from app.api.agent_beliefs import read_beliefs

from app.models.thinking_protocol import ThinkingProtocol
from app.models.agent_protocol import AgentProtocol

router = APIRouter(prefix="/api/agents", tags=["agents"])


async def _load_agent(db: AsyncSession, agent_id) -> Agent | None:
    """Load agent with agent_models + nested model_config_rel eagerly."""
    result = await db.execute(
        select(Agent)
        .where(Agent.id == agent_id)
        .options(
            selectinload(Agent.agent_models).selectinload(AgentModel.model_config_rel),
            selectinload(Agent.thinking_protocol),
            selectinload(Agent.agent_protocols).selectinload(AgentProtocol.protocol),
        )
    )
    return result.scalar_one_or_none()


def _build_agent_response(agent: Agent) -> dict:
    """Build response dict — DB identity + filesystem settings as source of truth."""
    data = {c.key: getattr(agent, c.key) for c in agent.__table__.columns}

    # Overlay settings from filesystem (source of truth)
    config = read_agent_config(agent.name)
    if config:
        data["description"] = config.get("description", data.get("description", ""))
        data["mission"] = config.get("mission", data.get("mission", ""))
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
    if agent.thinking_protocol:
        tp = agent.thinking_protocol
        data["thinking_protocol"] = {
            "id": str(tp.id),
            "name": tp.name,
            "description": tp.description or "",
            "type": tp.type or "standard",
            "steps": tp.steps or [],
        }
    else:
        data["thinking_protocol"] = None
    data["thinking_protocol_id"] = str(agent.thinking_protocol_id) if agent.thinking_protocol_id else None

    # All assigned protocols (multi-protocol)
    protocols_out = []
    for ap in (agent.agent_protocols or []):
        p = ap.protocol
        if p:
            protocols_out.append({
                "id": str(p.id),
                "name": p.name,
                "description": p.description or "",
                "type": p.type or "standard",
                "steps": p.steps or [],
                "is_main": ap.is_main,
                "priority": ap.priority,
            })
    data["protocols"] = protocols_out

    agent_models_out = []
    for am in (agent.agent_models or []):
        mcr = am.model_config_rel
        agent_models_out.append(AgentModelResponse(
            id=am.id,
            model_config_id=am.model_config_id,
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
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Agent).options(
        selectinload(Agent.agent_models).selectinload(AgentModel.model_config_rel),
        selectinload(Agent.thinking_protocol),
        selectinload(Agent.agent_protocols).selectinload(AgentProtocol.protocol),
    )
    if status:
        q = q.where(Agent.status == status)
    q = q.order_by(Agent.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    agents = result.scalars().all()
    return [_build_agent_response(a) for a in agents]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: AgentCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent_data = body.model_dump(exclude={"models", "thinking_protocol_id", "protocol_ids", "mission"})
    # Handle thinking_protocol_id separately
    if body.thinking_protocol_id:
        agent_data["thinking_protocol_id"] = body.thinking_protocol_id
    # self_thinking is already in agent_data from model_dump
    agent = Agent(**agent_data)
    db.add(agent)
    await db.flush()

    # Create agent_model entries
    for entry in body.models:
        am = AgentModel(
            agent_id=agent.id,
            model_config_id=entry.model_config_id,
            task_type=entry.task_type,
            tags=entry.tags,
            priority=entry.priority,
        )
        db.add(am)

    # Create agent_protocol entries (multi-protocol)
    if body.protocol_ids:
        for idx, pid in enumerate(body.protocol_ids):
            ap = AgentProtocol(
                agent_id=agent.id,
                protocol_id=UUID(pid),
                is_main=(pid == body.thinking_protocol_id),
                priority=idx,
            )
            db.add(ap)
    elif body.thinking_protocol_id:
        # If only main protocol specified, add it to the join table too
        ap = AgentProtocol(
            agent_id=agent.id,
            protocol_id=UUID(body.thinking_protocol_id),
            is_main=True,
            priority=0,
        )
        db.add(ap)

    await db.flush()
    await db.refresh(agent)

    # Write files as source of truth
    init_agent_directory(agent)
    # Write config files from the provided data (not from DB defaults)
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

    agent = await _load_agent(db, agent.id)
    return _build_agent_response(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _build_agent_response(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True, exclude={"models", "protocol_ids"})
    old_name = agent.name

    # Update DB identity fields
    if "name" in update_data:
        agent.name = update_data["name"]
    if "filesystem_access" in update_data:
        agent.filesystem_access = update_data["filesystem_access"]
    if "system_access" in update_data:
        agent.system_access = update_data["system_access"]
    if "self_thinking" in update_data:
        agent.self_thinking = update_data["self_thinking"]
    if "thinking_protocol_id" in update_data:
        val = update_data["thinking_protocol_id"]
        agent.thinking_protocol_id = val if val else None

    # If models list is provided, replace all agent_model entries
    if body.models is not None:
        await db.execute(delete(AgentModel).where(AgentModel.agent_id == agent_id))
        for entry in body.models:
            am = AgentModel(
                agent_id=agent.id,
                model_config_id=entry.model_config_id,
                task_type=entry.task_type,
                tags=entry.tags,
                priority=entry.priority,
            )
            db.add(am)

    # If protocol_ids list is provided, replace all agent_protocol entries
    if body.protocol_ids is not None:
        await db.execute(delete(AgentProtocol).where(AgentProtocol.agent_id == agent_id))
        main_id = body.thinking_protocol_id if "thinking_protocol_id" in body.model_dump(exclude_unset=True) else str(agent.thinking_protocol_id) if agent.thinking_protocol_id else None
        for idx, pid in enumerate(body.protocol_ids):
            ap = AgentProtocol(
                agent_id=agent.id,
                protocol_id=UUID(pid),
                is_main=(pid == main_id),
                priority=idx,
            )
            db.add(ap)
    elif "thinking_protocol_id" in update_data:
        # If only main protocol changed but protocol_ids not provided,
        # update the is_main flag on existing entries
        existing_aps = await db.execute(
            select(AgentProtocol).where(AgentProtocol.agent_id == agent_id)
        )
        main_val = update_data["thinking_protocol_id"]
        for ap in existing_aps.scalars().all():
            ap.is_main = (str(ap.protocol_id) == main_val) if main_val else False

    await db.flush()
    await db.refresh(agent)

    # Handle rename: move directory
    if agent.name != old_name:
        import shutil
        from app.api.agent_files import _get_agent_dir, _ensure_agents_dir
        _ensure_agents_dir()
        old_dir = _get_agent_dir(old_name)
        new_dir = _get_agent_dir(agent.name)
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
            new_settings[f] = getattr(agent, f)
    new_settings["principles"] = settings_data.get("principles", [])
    write_agent_settings(agent.name, new_settings)

    agent = await _load_agent(db, agent.id)
    return _build_agent_response(agent)


@router.delete("/{agent_id}", response_model=MessageResponse)
async def delete_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent_name = agent.name
    await db.delete(agent)
    delete_agent_directory(agent_name)
    return MessageResponse(message="Agent deleted")


@router.post("/{agent_id}/start", response_model=AgentResponse)
async def start_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "running"
    from datetime import datetime, timezone
    agent.last_run_at = datetime.now(timezone.utc)
    await db.flush()
    agent = await _load_agent(db, agent_id)
    return _build_agent_response(agent)


@router.post("/{agent_id}/stop", response_model=AgentResponse)
async def stop_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "stopped"
    await db.flush()
    agent = await _load_agent(db, agent_id)
    return _build_agent_response(agent)


@router.post("/{agent_id}/pause", response_model=AgentResponse)
async def pause_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "paused"
    await db.flush()
    agent = await _load_agent(db, agent_id)
    return _build_agent_response(agent)


@router.post("/{agent_id}/resume", response_model=AgentResponse)
async def resume_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.status = "running"
    await db.flush()
    agent = await _load_agent(db, agent_id)
    return _build_agent_response(agent)


@router.post("/{agent_id}/duplicate", response_model=AgentResponse, status_code=201)
async def duplicate_agent(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    agent = await _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_name = f"{agent.name} (copy)"
    new_agent = Agent(name=new_name, thinking_protocol_id=agent.thinking_protocol_id)
    db.add(new_agent)
    await db.flush()

    # Duplicate agent_models
    for am in agent.agent_models:
        new_am = AgentModel(
            agent_id=new_agent.id,
            model_config_id=am.model_config_id,
            task_type=am.task_type,
            tags=am.tags,
            priority=am.priority,
        )
        db.add(new_am)

    # Duplicate agent_protocols
    for ap in (agent.agent_protocols or []):
        new_ap = AgentProtocol(
            agent_id=new_agent.id,
            protocol_id=ap.protocol_id,
            is_main=ap.is_main,
            priority=ap.priority,
        )
        db.add(new_ap)
    await db.flush()

    # Duplicate filesystem directory (copies all files including settings)
    duplicate_agent_directory(agent.name, new_name)
    # Update agent.json with new name
    config = read_agent_config(new_name)
    config["name"] = new_name
    write_agent_config(new_name, config)

    new_agent = await _load_agent(db, new_agent.id)
    return _build_agent_response(new_agent)


@router.get("/{agent_id}/stats", response_model=AgentStatsResponse)
async def agent_stats(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify agent exists
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    total_tasks = (await db.execute(select(func.count(Task.id)).where(Task.agent_id == agent_id))).scalar() or 0
    completed = (await db.execute(select(func.count(Task.id)).where(Task.agent_id == agent_id, Task.status == "completed"))).scalar() or 0
    failed = (await db.execute(select(func.count(Task.id)).where(Task.agent_id == agent_id, Task.status == "failed"))).scalar() or 0
    logs = (await db.execute(select(func.count(AgentLog.id)).where(AgentLog.agent_id == agent_id))).scalar() or 0
    memories = (await db.execute(select(func.count(Memory.id)).where(Memory.agent_id == agent_id))).scalar() or 0
    skills = (await db.execute(select(func.count(AgentSkill.skill_id)).where(AgentSkill.agent_id == agent_id))).scalar() or 0

    return AgentStatsResponse(
        total_tasks=total_tasks,
        completed_tasks=completed,
        failed_tasks=failed,
        total_logs=logs,
        total_memories=memories,
        total_skills=skills,
    )


# --------------- Avatar Upload ---------------

AVATAR_MAX_SIZE = 10 * 1024 * 1024  # 10 MB
AVATAR_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
AVATAR_RESIZE_PX = 256  # Max width/height for non-GIF images


@router.post("/{agent_id}/avatar")
async def upload_avatar(
    agent_id: UUID,
    file: UploadFile = File(...),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload or replace agent avatar. Photos are resized; GIFs are kept as-is."""
    agent = await _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Validate content type
    content_type = file.content_type or ""
    if content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported image type: {content_type}. Allowed: {', '.join(AVATAR_ALLOWED_TYPES)}")

    # Read file data
    data = await file.read()
    if len(data) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max {AVATAR_MAX_SIZE // (1024*1024)} MB")

    is_gif = content_type == "image/gif"

    # Determine extension
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
    ext = ext_map.get(content_type, "png")

    # Agent avatar directory
    base_dir = os.path.join("..", "data", "agents", agent.name)
    os.makedirs(base_dir, exist_ok=True)

    # Remove old avatar files
    for old in os.listdir(base_dir):
        if old.startswith("avatar."):
            os.remove(os.path.join(base_dir, old))

    avatar_filename = f"avatar.{ext}"
    avatar_path = os.path.join(base_dir, avatar_filename)

    if is_gif:
        # GIF — save as-is, no resize
        with open(avatar_path, "wb") as f:
            f.write(data)
    else:
        # Resize photo using Pillow
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))

        # Convert RGBA/P to RGB for JPEG
        if ext == "jpg" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize keeping aspect ratio, fit within AVATAR_RESIZE_PX x AVATAR_RESIZE_PX
        img.thumbnail((AVATAR_RESIZE_PX, AVATAR_RESIZE_PX), Image.LANCZOS)
        img.save(avatar_path, quality=90)

    # Build URL relative path (served via /api/uploads/agents/<name>/avatar.<ext>)
    avatar_url = f"/api/uploads/agents/{agent.name}/{avatar_filename}"

    # Update DB
    agent.avatar_url = avatar_url
    await db.commit()

    return {"avatar_url": avatar_url}


@router.delete("/{agent_id}/avatar")
async def delete_avatar(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove agent avatar."""
    agent = await _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    base_dir = os.path.join("..", "data", "agents", agent.name)
    if os.path.isdir(base_dir):
        for old in os.listdir(base_dir):
            if old.startswith("avatar."):
                os.remove(os.path.join(base_dir, old))

    agent.avatar_url = None
    await db.commit()

    return {"detail": "Avatar deleted"}
