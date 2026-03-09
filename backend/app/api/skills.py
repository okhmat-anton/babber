from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models.user import MongoUser
from app.mongodb.models.agent import MongoAgent
from app.mongodb.models.skill import MongoSkill, MongoAgentSkill
from app.mongodb.services import SkillService, AgentSkillService, AgentService
from app.schemas.skill import (
    SkillCreate, SkillUpdate, SkillResponse, AgentSkillCreate, AgentSkillResponse,
)
from app.schemas.common import MessageResponse
from app.api.skill_files import init_skill_directory, delete_skill_directory, duplicate_skill_directory

router = APIRouter(prefix="/api/skills", tags=["skills"])
agent_skill_router = APIRouter(prefix="/api/agents/{agent_id}/skills", tags=["agent-skills"])


# ------- Skill Catalog -------
@router.get("", response_model=list[SkillResponse])
async def list_skills(
    category: str | None = Query(None),
    is_shared: bool | None = Query(None),
    search: str | None = Query(None),
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    all_skills = await skill_service.get_all(skip=0, limit=1000)
    
    # Apply filters
    filtered_skills = all_skills
    if category:
        filtered_skills = [s for s in filtered_skills if s.category == category]
    if is_shared is not None:
        filtered_skills = [s for s in filtered_skills if s.is_shared == is_shared]
    if search:
        search_lower = search.lower()
        filtered_skills = [s for s in filtered_skills 
                          if search_lower in s.name.lower() or search_lower in s.description.lower()]
    
    # Sort by created_at desc
    filtered_skills.sort(key=lambda s: s.created_at, reverse=True)
    return filtered_skills


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    existing = await skill_service.get_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail="Skill with this name already exists")
    
    skill = MongoSkill(**body.model_dump())
    created = await skill_service.create(skill)

    # Create skill directory + manifest + default entry file
    init_skill_directory(created)

    return created


@router.get("/shared", response_model=list[SkillResponse])
async def list_shared_skills(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    all_skills = await skill_service.get_all(skip=0, limit=1000)
    shared = [s for s in all_skills if s.is_shared]
    shared.sort(key=lambda s: s.name)
    return shared


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: UUID,
    body: SkillUpdate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=403, detail="Cannot edit system skill")
    
    update_data = body.model_dump(exclude_unset=True)
    updated = await skill_service.update(str(skill_id), update_data)
    return updated


@router.delete("/{skill_id}", response_model=MessageResponse)
async def delete_skill(
    skill_id: UUID,
    force: bool = Query(False),
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system skill")
    
    if not force:
        agent_skill_service = AgentSkillService(db)
        all_agent_skills = await agent_skill_service.get_all(skip=0, limit=1000)
        usage = [ass for ass in all_agent_skills if ass.skill_id == str(skill_id)]
        if usage:
            raise HTTPException(status_code=409, detail="Skill is in use. Use force=true to delete")
    
    skill_name = skill.name
    await skill_service.delete(str(skill_id))

    # Remove skill directory from filesystem
    delete_skill_directory(skill_name)

    return MessageResponse(message="Skill deleted")


@router.post("/{skill_id}/share", response_model=SkillResponse)
async def share_skill(
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    updated = await skill_service.update(str(skill_id), {"is_shared": True})
    return updated


@router.post("/{skill_id}/unshare", response_model=SkillResponse)
async def unshare_skill(
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    updated = await skill_service.update(str(skill_id), {"is_shared": False})
    return updated


@router.post("/{skill_id}/toggle", response_model=SkillResponse)
async def toggle_skill_enabled(
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Toggle skill enabled/disabled globally."""
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=403, detail="Cannot disable system skill")

    new_enabled = not getattr(skill, "enabled", True)
    updated = await skill_service.update(str(skill_id), {"enabled": new_enabled})
    return updated


@router.post("/{skill_id}/duplicate", response_model=SkillResponse, status_code=201)
async def duplicate_skill(
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    new_skill = MongoSkill(
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
    created = await skill_service.create(new_skill)

    # Copy entire skill directory
    duplicate_skill_directory(skill.name, created.name)

    return created


# ------- Agent Skills -------
@agent_skill_router.get("", response_model=list[AgentSkillResponse])
async def list_agent_skills(
    agent_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    agent_service = AgentService(db)
    agent = await agent_service.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_skill_service = AgentSkillService(db)
    skill_service = SkillService(db)
    
    agent_skills = await agent_skill_service.get_by_agent(str(agent_id))

    responses = []
    for asl in agent_skills:
        skill = await skill_service.get_by_id(asl.skill_id)
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
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    agent_service = AgentService(db)
    agent = await agent_service.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(body.skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    agent_skill_service = AgentSkillService(db)
    existing = await agent_skill_service.get_by_agent_and_skill(str(agent_id), str(body.skill_id))
    if existing:
        raise HTTPException(status_code=409, detail="Skill already attached")

    asl = MongoAgentSkill(agent_id=str(agent_id), skill_id=str(body.skill_id), config=body.config)
    await agent_skill_service.create(asl)
    return MessageResponse(message="Skill attached")


@agent_skill_router.delete("/{skill_id}", response_model=MessageResponse)
async def detach_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    agent_skill_service = AgentSkillService(db)
    asl = await agent_skill_service.get_by_agent_and_skill(str(agent_id), str(skill_id))
    if not asl:
        raise HTTPException(status_code=404, detail="Skill not attached to agent")
    await agent_skill_service.delete(asl.id)
    return MessageResponse(message="Skill detached")


@agent_skill_router.put("/{skill_id}", response_model=MessageResponse)
async def update_agent_skill(
    agent_id: UUID,
    skill_id: UUID,
    is_enabled: bool | None = Query(None),
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    agent_skill_service = AgentSkillService(db)
    asl = await agent_skill_service.get_by_agent_and_skill(str(agent_id), str(skill_id))
    if not asl:
        raise HTTPException(status_code=404, detail="Skill not attached to agent")
    if is_enabled is not None:
        await agent_skill_service.update(asl.id, {"is_enabled": is_enabled})
    return MessageResponse(message="Updated")


# ------- All available skills for an agent -------

@agent_skill_router.get("/available", response_model=list[dict])
async def list_available_skills(
    agent_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """
    Returns ALL skills available to this agent:
    - System skills (is_system=true)
    - Shared/public skills (is_shared=true)
    - Agent's personal skills (author_agent_id=agent_id)

    Each skill includes 'enabled' flag showing whether agent has it active
    and 'ownership' field: 'system' | 'public' | 'personal'
    """
    agent_service = AgentService(db)
    agent = await agent_service.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get all skills available to this agent
    skill_service = SkillService(db)
    all_skills_list = await skill_service.get_all(skip=0, limit=1000)
    
    # Filter: system OR shared OR authored by this agent
    available = [s for s in all_skills_list 
                if s.is_system or s.is_shared or s.author_agent_id == str(agent_id)]
    available.sort(key=lambda s: (s.category, s.name))

    # Get agent's enabled/disabled state
    agent_skill_service = AgentSkillService(db)
    agent_skills = await agent_skill_service.get_by_agent(str(agent_id))
    agent_skill_map = {ask.skill_id: ask for ask in agent_skills}

    items = []
    for s in available:
        sid = s.id
        ask = agent_skill_map.get(sid)
        ownership = "system" if s.is_system else "personal" if s.author_agent_id == str(agent_id) else "public"
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
            "author_agent_id": s.author_agent_id,
            "enabled": enabled,
            "attached": ask is not None,
        })
    return items


@agent_skill_router.post("/toggle/{skill_id}", response_model=MessageResponse)
async def toggle_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Toggle a skill on/off for an agent. Creates AgentSkill if needed."""
    agent_service = AgentService(db)
    agent = await agent_service.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Check if already attached
    agent_skill_service = AgentSkillService(db)
    existing = await agent_skill_service.get_by_agent_and_skill(str(agent_id), str(skill_id))

    if existing:
        new_state = not existing.is_enabled
        await agent_skill_service.update(existing.id, {"is_enabled": new_state})
        state = "enabled" if new_state else "disabled"
    else:
        # Attach and enable
        asl = MongoAgentSkill(agent_id=str(agent_id), skill_id=str(skill_id), is_enabled=True)
        await agent_skill_service.create(asl)
        state = "enabled"

    return MessageResponse(message=f"Skill {state}")


@agent_skill_router.post("/personal", response_model=dict, status_code=201)
async def create_personal_skill(
    agent_id: UUID,
    body: SkillCreate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a personal skill owned by this agent."""
    agent_service = AgentService(db)
    agent = await agent_service.get_by_id(str(agent_id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check for name conflict
    skill_service = SkillService(db)
    existing = await skill_service.get_by_name(body.name)
    if existing:
        raise HTTPException(status_code=409, detail="Skill with this name already exists")

    skill = MongoSkill(
        **body.model_dump(),
        author_agent_id=str(agent_id),
    )
    created_skill = await skill_service.create(skill)

    # Create skill directory
    init_skill_directory(created_skill)

    # Auto-attach and enable for this agent
    agent_skill_service = AgentSkillService(db)
    asl = MongoAgentSkill(agent_id=str(agent_id), skill_id=created_skill.id, is_enabled=True)
    await agent_skill_service.create(asl)

    return {
        "id": created_skill.id,
        "name": created_skill.name,
        "display_name": created_skill.display_name,
        "description": created_skill.description,
        "description_for_agent": created_skill.description_for_agent,
        "category": created_skill.category,
        "version": created_skill.version,
        "is_system": created_skill.is_system,
        "is_shared": created_skill.is_shared,
        "ownership": "personal",
        "author_agent_id": str(agent_id),
        "enabled": True,
        "attached": True,
    }


@agent_skill_router.post("/{skill_id}/share", response_model=MessageResponse)
async def agent_share_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Share an agent's personal skill publicly."""
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=400, detail="Cannot share system skills")
    
    await skill_service.update(str(skill_id), {"is_shared": True})
    return MessageResponse(message="Skill shared")


@agent_skill_router.post("/{skill_id}/unshare", response_model=MessageResponse)
async def agent_unshare_skill(
    agent_id: UUID,
    skill_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unshare a skill (make private)."""
    skill_service = SkillService(db)
    skill = await skill_service.get_by_id(str(skill_id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if skill.is_system:
        raise HTTPException(status_code=400, detail="Cannot unshare system skills")
    
    await skill_service.update(str(skill_id), {"is_shared": False})
    return MessageResponse(message="Skill unshared")
