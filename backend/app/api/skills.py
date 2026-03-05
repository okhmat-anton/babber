from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.agent import Agent
from app.models.skill import Skill, AgentSkill
from app.schemas.skill import (
    SkillCreate, SkillUpdate, SkillResponse, AgentSkillCreate, AgentSkillResponse,
)
from app.schemas.common import MessageResponse
from app.api.skill_files import init_skill_directory, delete_skill_directory, duplicate_skill_directory
from sqlalchemy.orm import selectinload
from sqlalchemy import or_

router = APIRouter(prefix="/api/skills", tags=["skills"])
agent_skill_router = APIRouter(prefix="/api/agents/{agent_id}/skills", tags=["agent-skills"])


# ------- Skill Catalog -------
@router.get("", response_model=list[SkillResponse])
async def list_skills(
    category: str | None = Query(None),
    is_shared: bool | None = Query(None),
    search: str | None = Query(None),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Skill)
    if category:
        q = q.where(Skill.category == category)
    if is_shared is not None:
        q = q.where(Skill.is_shared == is_shared)
    if search:
        q = q.where(Skill.name.ilike(f"%{search}%") | Skill.description.ilike(f"%{search}%"))
    q = q.order_by(Skill.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Skill).where(Skill.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Skill with this name already exists")
    skill = Skill(**body.model_dump())
    db.add(skill)
    await db.flush()
    await db.refresh(skill)

    # Create skill directory + manifest + default entry file
    init_skill_directory(skill)

    return skill


@router.get("/shared", response_model=list[SkillResponse])
async def list_shared_skills(
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.is_shared == True).order_by(Skill.name))
    return result.scalars().all()


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: UUID,
    body: SkillUpdate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=403, detail="Cannot edit system skill")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(skill, key, value)
    await db.flush()
    await db.refresh(skill)
    return skill


@router.delete("/{skill_id}", response_model=MessageResponse)
async def delete_skill(
    skill_id: UUID,
    force: bool = Query(False),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system skill")
    if not force:
        usage = await db.execute(select(AgentSkill).where(AgentSkill.skill_id == skill_id))
        if usage.scalars().first():
            raise HTTPException(status_code=409, detail="Skill is in use. Use force=true to delete")
    skill_name = skill.name
    await db.delete(skill)

    # Remove skill directory from filesystem
    delete_skill_directory(skill_name)

    return MessageResponse(message="Skill deleted")


@router.post("/{skill_id}/share", response_model=SkillResponse)
async def share_skill(
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill.is_shared = True
    await db.flush()
    await db.refresh(skill)
    return skill


@router.post("/{skill_id}/unshare", response_model=SkillResponse)
async def unshare_skill(
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill.is_shared = False
    await db.flush()
    await db.refresh(skill)
    return skill


@router.post("/{skill_id}/duplicate", response_model=SkillResponse, status_code=201)
async def duplicate_skill(
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    new_skill = Skill(
        name=f"{skill.name}_copy",
        display_name=f"{skill.display_name} (copy)",
        description=skill.description,
        description_for_agent=skill.description_for_agent,
        category=skill.category,
        version=skill.version,
        code=skill.code,
        input_schema=skill.input_schema,
        output_schema=skill.output_schema,
    )
    db.add(new_skill)
    await db.flush()
    await db.refresh(new_skill)

    # Copy entire skill directory
    duplicate_skill_directory(skill.name, new_skill.name)

    return new_skill


# ------- Agent Skills -------
@agent_skill_router.get("", response_model=list[AgentSkillResponse])
async def list_agent_skills(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id)
    )
    agent_skills = result.scalars().all()

    responses = []
    for asl in agent_skills:
        skill_result = await db.execute(select(Skill).where(Skill.id == asl.skill_id))
        skill = skill_result.scalar_one_or_none()
        responses.append(AgentSkillResponse(
            skill_id=asl.skill_id,
            agent_id=asl.agent_id,
            is_enabled=asl.is_enabled,
            config=asl.config,
            added_at=asl.added_at,
            skill=skill,
        ))
    return responses


@agent_skill_router.post("", response_model=MessageResponse, status_code=201)
async def attach_skill(
    agent_id: UUID,
    body: AgentSkillCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await db.execute(select(Skill).where(Skill.id == body.skill_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Skill not found")

    existing = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == body.skill_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Skill already attached")

    asl = AgentSkill(agent_id=agent_id, skill_id=body.skill_id, config=body.config)
    db.add(asl)
    await db.flush()
    return MessageResponse(message="Skill attached")


@agent_skill_router.delete("/{skill_id}", response_model=MessageResponse)
async def detach_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id)
    )
    asl = result.scalar_one_or_none()
    if not asl:
        raise HTTPException(status_code=404, detail="Skill not attached to agent")
    await db.delete(asl)
    return MessageResponse(message="Skill detached")


@agent_skill_router.put("/{skill_id}", response_model=MessageResponse)
async def update_agent_skill(
    agent_id: UUID,
    skill_id: UUID,
    is_enabled: bool | None = Query(None),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id)
    )
    asl = result.scalar_one_or_none()
    if not asl:
        raise HTTPException(status_code=404, detail="Skill not attached to agent")
    if is_enabled is not None:
        asl.is_enabled = is_enabled
    await db.flush()
    return MessageResponse(message="Updated")


# ------- All available skills for an agent -------

@agent_skill_router.get("/available", response_model=list[dict])
async def list_available_skills(
    agent_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns ALL skills available to this agent:
    - System skills (is_system=true)
    - Shared/public skills (is_shared=true)
    - Agent's personal skills (author_agent_id=agent_id)

    Each skill includes 'enabled' flag showing whether agent has it active
    and 'ownership' field: 'system' | 'public' | 'personal'
    """
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get all skills available to this agent
    result = await db.execute(
        select(Skill).where(
            or_(
                Skill.is_system == True,
                Skill.is_shared == True,
                Skill.author_agent_id == agent_id,
            )
        ).order_by(Skill.category, Skill.name)
    )
    all_skills = result.scalars().all()

    # Get agent's enabled/disabled state
    result = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id)
    )
    agent_skill_map = {str(ask.skill_id): ask for ask in result.scalars().all()}

    items = []
    for s in all_skills:
        sid = str(s.id)
        ask = agent_skill_map.get(sid)
        ownership = "system" if s.is_system else "personal" if s.author_agent_id == agent_id else "public"
        # Default: public/system skills are enabled unless explicitly disabled
        # Personal skills are disabled unless explicitly enabled
        if ask:
            enabled = ask.is_enabled
        elif ownership in ("system", "public"):
            enabled = True
        else:
            enabled = False
        items.append({
            "id": sid,
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description or "",
            "description_for_agent": s.description_for_agent or "",
            "category": s.category,
            "version": s.version,
            "is_system": s.is_system,
            "is_shared": s.is_shared,
            "ownership": ownership,
            "author_agent_id": str(s.author_agent_id) if s.author_agent_id else None,
            "enabled": enabled,
            "attached": ask is not None,
        })
    return items


@agent_skill_router.post("/toggle/{skill_id}", response_model=MessageResponse)
async def toggle_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a skill on/off for an agent. Creates AgentSkill if needed."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Check if already attached
    result = await db.execute(
        select(AgentSkill).where(AgentSkill.agent_id == agent_id, AgentSkill.skill_id == skill_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.is_enabled = not existing.is_enabled
        state = "enabled" if existing.is_enabled else "disabled"
    else:
        # Attach and enable
        asl = AgentSkill(agent_id=agent_id, skill_id=skill_id, is_enabled=True)
        db.add(asl)
        state = "enabled"

    await db.flush()
    return MessageResponse(message=f"Skill {state}")


@agent_skill_router.post("/personal", response_model=dict, status_code=201)
async def create_personal_skill(
    agent_id: UUID,
    body: SkillCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a personal skill owned by this agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check for name conflict
    existing = await db.execute(select(Skill).where(Skill.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Skill with this name already exists")

    skill = Skill(
        **body.model_dump(),
        author_agent_id=agent_id,
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)

    # Create skill directory
    init_skill_directory(skill)

    # Auto-attach and enable for this agent
    asl = AgentSkill(agent_id=agent_id, skill_id=skill.id, is_enabled=True)
    db.add(asl)
    await db.flush()

    return {
        "id": str(skill.id),
        "name": skill.name,
        "display_name": skill.display_name,
        "description": skill.description,
        "description_for_agent": skill.description_for_agent,
        "category": skill.category,
        "version": skill.version,
        "is_system": skill.is_system,
        "is_shared": skill.is_shared,
        "ownership": "personal",
        "author_agent_id": str(agent_id),
        "enabled": True,
        "attached": True,
    }


@agent_skill_router.post("/{skill_id}/share", response_model=MessageResponse)
async def agent_share_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Share an agent's personal skill publicly."""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=400, detail="Cannot share system skills")
    skill.is_shared = True
    await db.flush()
    return MessageResponse(message="Skill shared")


@agent_skill_router.post("/{skill_id}/unshare", response_model=MessageResponse)
async def agent_unshare_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unshare a skill (make private)."""
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=400, detail="Cannot modify system skills")
    skill.is_shared = False
    await db.flush()
    return MessageResponse(message="Skill unshared")
