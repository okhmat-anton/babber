"""
Ideas API.

Global and per-agent ideas management.

Endpoints:
  GET    /api/ideas                          — list all ideas (global view)
  POST   /api/ideas                          — create an idea
  GET    /api/ideas/{id}                     — get a single idea
  PATCH  /api/ideas/{id}                     — update an idea
  DELETE /api/ideas/{id}                     — delete an idea
  GET    /api/agents/{agent_id}/ideas        — list ideas for an agent
  POST   /api/agents/{agent_id}/ideas        — create an idea for an agent
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import IdeaService, AgentService
from app.mongodb.models.idea import MongoIdea

router = APIRouter(tags=["ideas"])

VALID_STATUSES = {"new", "in_progress", "done", "archived"}
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_SOURCES = {"user", "agent"}


# ── Schemas ──────────────────────────────────────────

class IdeaCreate(BaseModel):
    title: str
    description: str = ""
    source: str = "user"
    category: Optional[str] = None
    priority: str = "medium"
    status: str = "new"
    tags: List[str] = []


class IdeaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None


# ── Helpers ──────────────────────────────────────────

def _idea_to_response(idea: MongoIdea) -> dict:
    return {
        "id": idea.id,
        "title": idea.title,
        "description": idea.description,
        "source": idea.source,
        "agent_id": idea.agent_id,
        "category": idea.category,
        "priority": idea.priority,
        "status": idea.status,
        "tags": idea.tags,
        "linked_video_ids": getattr(idea, 'linked_video_ids', []) or [],
        "linked_fact_ids": getattr(idea, 'linked_fact_ids', []) or [],
        "linked_analysis_ids": getattr(idea, 'linked_analysis_ids', []) or [],
        "created_by": idea.created_by,
        "created_at": idea.created_at.isoformat() if isinstance(idea.created_at, datetime) else str(idea.created_at),
        "updated_at": idea.updated_at.isoformat() if isinstance(idea.updated_at, datetime) else str(idea.updated_at),
    }


# ── Global Endpoints ─────────────────────────────────

@router.get("/api/ideas")
async def list_all_ideas(
    status: Optional[str] = Query(None, description="Filter by status: new, in_progress, done, archived"),
    source: Optional[str] = Query(None, description="Filter by source: user or agent"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Text search in title/description"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all ideas (global view)."""
    svc = IdeaService(db)
    items = await svc.get_all_ideas(
        status=status, source=source, agent_id=agent_id,
        category=category, search=search, limit=limit, skip=skip,
    )
    return {"items": [_idea_to_response(i) for i in items], "total": len(items)}


@router.post("/api/ideas", status_code=201)
async def create_idea(
    body: IdeaCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create an idea (global, no agent)."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
    if body.source not in VALID_SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(VALID_SOURCES)}")

    idea = MongoIdea(
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        source=body.source,
        agent_id=None,
        category=body.category,
        priority=body.priority,
        status=body.status,
        tags=body.tags,
        created_by=body.source,
    )
    svc = IdeaService(db)
    created = await svc.create(idea)
    return _idea_to_response(created)


@router.get("/api/ideas/{idea_id}")
async def get_idea(
    idea_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single idea."""
    svc = IdeaService(db)
    idea = await svc.get_by_id(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return _idea_to_response(idea)


@router.patch("/api/ideas/{idea_id}")
async def update_idea(
    idea_id: str,
    body: IdeaUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update an idea."""
    svc = IdeaService(db)
    existing = await svc.get_by_id(idea_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Idea not found")

    update_data = {}
    if body.title is not None:
        update_data["title"] = body.title.strip()
    if body.description is not None:
        update_data["description"] = body.description.strip()
    if body.source is not None:
        if body.source not in VALID_SOURCES:
            raise HTTPException(status_code=400, detail=f"source must be one of: {', '.join(VALID_SOURCES)}")
        update_data["source"] = body.source
    if body.category is not None:
        update_data["category"] = body.category if body.category else None
    if body.priority is not None:
        if body.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
        update_data["priority"] = body.priority
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
        update_data["status"] = body.status
    if body.tags is not None:
        update_data["tags"] = body.tags

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(idea_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Idea not found")
        return _idea_to_response(updated)

    return _idea_to_response(existing)


@router.delete("/api/ideas/{idea_id}")
async def delete_idea(
    idea_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete an idea."""
    svc = IdeaService(db)
    existing = await svc.get_by_id(idea_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Idea not found")
    await svc.delete(idea_id)
    return {"detail": "Deleted"}


# ── Link / Unlink ────────────────────────────────────

class IdeaLinkRequest(BaseModel):
    target_type: str  # "video", "fact", "analysis"
    target_id: str


@router.post("/api/ideas/{idea_id}/link")
async def link_entity_to_idea(
    idea_id: str,
    body: IdeaLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Link a video, fact, or analysis topic to an idea."""
    svc = IdeaService(db)
    idea = await svc.get_by_id(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    field_map = {"video": "linked_video_ids", "fact": "linked_fact_ids", "analysis": "linked_analysis_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": idea_id}, {"$addToSet": {field: body.target_id}})
    updated = await svc.get_by_id(idea_id)
    return _idea_to_response(updated)


@router.post("/api/ideas/{idea_id}/unlink")
async def unlink_entity_from_idea(
    idea_id: str,
    body: IdeaLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unlink a video, fact, or analysis topic from an idea."""
    svc = IdeaService(db)
    idea = await svc.get_by_id(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    field_map = {"video": "linked_video_ids", "fact": "linked_fact_ids", "analysis": "linked_analysis_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": idea_id}, {"$pull": {field: body.target_id}})
    updated = await svc.get_by_id(idea_id)
    return _idea_to_response(updated)


# ── Per-Agent Endpoints ──────────────────────────────

@router.get("/api/agents/{agent_id}/ideas")
async def list_agent_ideas(
    agent_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source: user or agent"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List ideas for a specific agent."""
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    svc = IdeaService(db)
    items = await svc.get_by_agent(agent_id, status=status, source=source, limit=limit, skip=skip)
    return {"items": [_idea_to_response(i) for i in items], "total": len(items)}


@router.post("/api/agents/{agent_id}/ideas", status_code=201)
async def create_agent_idea(
    agent_id: str,
    body: IdeaCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create an idea for a specific agent."""
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")

    idea = MongoIdea(
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        source=body.source,
        agent_id=agent_id,
        category=body.category,
        priority=body.priority,
        status=body.status,
        tags=body.tags,
        created_by=body.source,
    )
    svc = IdeaService(db)
    created = await svc.create(idea)
    return _idea_to_response(created)
