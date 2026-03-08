"""
Agent Facts & Hypotheses API.

Agents can store facts (verified knowledge) and hypotheses (unverified assumptions).
Each fact belongs to a specific agent and can be managed via UI or agent skills.

Endpoints:
  GET    /api/agents/{agent_id}/facts         — list all facts/hypotheses
  POST   /api/agents/{agent_id}/facts         — create a fact/hypothesis
  PATCH  /api/agents/{agent_id}/facts/{id}    — update a fact/hypothesis
  DELETE /api/agents/{agent_id}/facts/{id}    — delete a fact/hypothesis
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import AgentService, AgentFactService
from app.mongodb.models.agent_fact import MongoAgentFact

router = APIRouter(prefix="/api/agents", tags=["agent-facts"])


# ── Schemas ──────────────────────────────────────────

class FactCreate(BaseModel):
    type: str = "fact"  # "fact" or "hypothesis"
    content: str
    source: str = "user"
    verified: bool = False
    confidence: float = 0.8
    tags: List[str] = []


class FactUpdate(BaseModel):
    type: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    verified: Optional[bool] = None
    confidence: Optional[float] = None
    tags: Optional[List[str]] = None


class FactResponse(BaseModel):
    id: str
    agent_id: str
    type: str
    content: str
    source: str
    verified: bool
    confidence: float
    tags: List[str]
    created_by: str
    created_at: str
    updated_at: str


# ── Helpers ──────────────────────────────────────────

async def _get_agent_or_404(agent_id: str, db: AsyncIOMotorDatabase):
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _fact_to_response(f: MongoAgentFact) -> dict:
    return {
        "id": f.id,
        "agent_id": f.agent_id,
        "type": f.type,
        "content": f.content,
        "source": f.source,
        "verified": f.verified,
        "confidence": f.confidence,
        "tags": f.tags,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat() if isinstance(f.created_at, datetime) else str(f.created_at),
        "updated_at": f.updated_at.isoformat() if isinstance(f.updated_at, datetime) else str(f.updated_at),
    }


# ── Endpoints ────────────────────────────────────────

@router.get("/{agent_id}/facts")
async def list_facts(
    agent_id: str,
    type: Optional[str] = Query(None, description="Filter by type: fact or hypothesis"),
    verified: Optional[bool] = Query(None, description="Filter by verified status"),
    search: Optional[str] = Query(None, description="Text search in content"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all facts & hypotheses for an agent."""
    await _get_agent_or_404(agent_id, db)
    svc = AgentFactService(db)

    if search:
        items = await svc.search_by_text(agent_id, search, limit=limit)
    else:
        items = await svc.get_by_agent(agent_id, fact_type=type, verified=verified, limit=limit, skip=skip)

    return {
        "items": [_fact_to_response(f) for f in items],
        "total": len(items),
    }


@router.post("/{agent_id}/facts", status_code=201)
async def create_fact(
    agent_id: str,
    body: FactCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a new fact or hypothesis."""
    await _get_agent_or_404(agent_id, db)

    if body.type not in ("fact", "hypothesis"):
        raise HTTPException(status_code=400, detail="type must be 'fact' or 'hypothesis'")

    fact = MongoAgentFact(
        agent_id=agent_id,
        type=body.type,
        content=body.content.strip(),
        source=body.source,
        verified=body.verified,
        confidence=body.confidence,
        tags=body.tags,
        created_by="user",
    )

    svc = AgentFactService(db)
    created = await svc.create(fact)
    return _fact_to_response(created)


@router.patch("/{agent_id}/facts/{fact_id}")
async def update_fact(
    agent_id: str,
    fact_id: str,
    body: FactUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update a fact or hypothesis."""
    await _get_agent_or_404(agent_id, db)
    svc = AgentFactService(db)
    existing = await svc.get_by_id(fact_id)
    if not existing or existing.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Fact not found")

    update_data = {}
    if body.type is not None:
        if body.type not in ("fact", "hypothesis"):
            raise HTTPException(status_code=400, detail="type must be 'fact' or 'hypothesis'")
        update_data["type"] = body.type
    if body.content is not None:
        update_data["content"] = body.content.strip()
    if body.source is not None:
        update_data["source"] = body.source
    if body.verified is not None:
        update_data["verified"] = body.verified
    if body.confidence is not None:
        update_data["confidence"] = body.confidence
    if body.tags is not None:
        update_data["tags"] = body.tags

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(fact_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Fact not found")
        return _fact_to_response(updated)

    return _fact_to_response(existing)


@router.delete("/{agent_id}/facts/{fact_id}")
async def delete_fact(
    agent_id: str,
    fact_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a fact or hypothesis."""
    await _get_agent_or_404(agent_id, db)
    svc = AgentFactService(db)
    existing = await svc.get_by_id(fact_id)
    if not existing or existing.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Fact not found")

    await svc.delete(fact_id)
    return {"detail": "Deleted"}
