"""
Global Facts API.

Provides a global view of all facts across all agents.
Also allows creating facts with an explicit agent_id.

Endpoints:
  GET  /api/facts         — list all facts across all agents
  POST /api/facts         — create a fact (agent_id in body)
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import AgentFactService, AgentService
from app.mongodb.models.agent_fact import MongoAgentFact

router = APIRouter(prefix="/api/facts", tags=["global-facts"])


# ── Schemas ──────────────────────────────────────────

class GlobalFactCreate(BaseModel):
    agent_id: str
    type: str = "fact"
    content: str
    source: str = "user"
    verified: bool = False
    confidence: float = 0.8
    category: Optional[str] = None
    tags: List[str] = []


# ── Helpers ──────────────────────────────────────────

def _fact_to_response(f: MongoAgentFact) -> dict:
    return {
        "id": f.id,
        "agent_id": f.agent_id,
        "type": f.type,
        "content": f.content,
        "source": f.source,
        "verified": f.verified,
        "confidence": f.confidence,
        "category": f.category,
        "tags": f.tags,
        "linked_video_ids": getattr(f, 'linked_video_ids', []) or [],
        "linked_analysis_ids": getattr(f, 'linked_analysis_ids', []) or [],
        "linked_idea_ids": getattr(f, 'linked_idea_ids', []) or [],
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat() if isinstance(f.created_at, datetime) else str(f.created_at),
        "updated_at": f.updated_at.isoformat() if isinstance(f.updated_at, datetime) else str(f.updated_at),
    }


# ── Endpoints ────────────────────────────────────────

@router.get("")
async def list_all_facts(
    type: Optional[str] = Query(None, description="Filter by type: fact or hypothesis"),
    verified: Optional[bool] = Query(None, description="Filter by verified status"),
    search: Optional[str] = Query(None, description="Text search in content"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all facts across all agents (global view). Optionally filter by agent."""
    svc = AgentFactService(db)

    if agent_id:
        # Delegate to per-agent method
        items = await svc.get_by_agent(agent_id, fact_type=type, verified=verified, limit=limit, skip=skip)
    else:
        items = await svc.get_all(fact_type=type, verified=verified, search=search, limit=limit, skip=skip)

    # Apply category filter if set
    if category:
        items = [f for f in items if f.category == category]

    return {"items": [_fact_to_response(f) for f in items], "total": len(items)}


@router.post("", status_code=201)
async def create_global_fact(
    body: GlobalFactCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a fact with an explicit agent_id."""
    # Verify agent exists
    agent = await AgentService(db).get_by_id(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.type not in ("fact", "hypothesis"):
        raise HTTPException(status_code=400, detail="type must be 'fact' or 'hypothesis'")

    fact = MongoAgentFact(
        agent_id=body.agent_id,
        type=body.type,
        content=body.content.strip(),
        source=body.source,
        verified=body.verified,
        confidence=body.confidence,
        category=body.category,
        tags=body.tags,
        created_by="user",
    )

    svc = AgentFactService(db)
    created = await svc.create(fact)
    return _fact_to_response(created)


@router.patch("/{fact_id}")
async def update_global_fact(
    fact_id: str,
    body: dict,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update a fact from the global view."""
    svc = AgentFactService(db)
    existing = await svc.get_by_id(fact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Fact not found")

    update_data = {}
    for field in ("type", "content", "source", "verified", "confidence", "category", "tags"):
        if field in body and body[field] is not None:
            update_data[field] = body[field]

    if "type" in update_data and update_data["type"] not in ("fact", "hypothesis"):
        raise HTTPException(status_code=400, detail="type must be 'fact' or 'hypothesis'")
    if "content" in update_data:
        update_data["content"] = update_data["content"].strip()

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(fact_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Fact not found")
        return _fact_to_response(updated)

    return _fact_to_response(existing)


@router.delete("/{fact_id}")
async def delete_global_fact(
    fact_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a fact from the global view."""
    svc = AgentFactService(db)
    existing = await svc.get_by_id(fact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Fact not found")
    await svc.delete(fact_id)
    return {"detail": "Deleted"}


# ── Link / Unlink ────────────────────────────────────

class FactLinkRequest(BaseModel):
    target_type: str  # "video", "analysis", "idea"
    target_id: str


@router.post("/{fact_id}/link")
async def link_entity_to_fact(
    fact_id: str,
    body: FactLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Link a video, analysis topic, or idea to a fact."""
    svc = AgentFactService(db)
    existing = await svc.get_by_id(fact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Fact not found")
    field_map = {"video": "linked_video_ids", "analysis": "linked_analysis_ids", "idea": "linked_idea_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": fact_id}, {"$addToSet": {field: body.target_id}})
    updated = await svc.get_by_id(fact_id)
    return _fact_to_response(updated)


@router.post("/{fact_id}/unlink")
async def unlink_entity_from_fact(
    fact_id: str,
    body: FactLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unlink a video, analysis topic, or idea from a fact."""
    svc = AgentFactService(db)
    existing = await svc.get_by_id(fact_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Fact not found")
    field_map = {"video": "linked_video_ids", "analysis": "linked_analysis_ids", "idea": "linked_idea_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": fact_id}, {"$pull": {field: body.target_id}})
    updated = await svc.get_by_id(fact_id)
    return _fact_to_response(updated)
