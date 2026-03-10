"""
Analysis Topics API.

Topics can be global (agent_id=None) or assigned to a specific agent.
Users can connect existing facts to topics for structured analysis.

Endpoints:
  GET    /api/analysis-topics                              — list all topics (global view)
  POST   /api/analysis-topics                              — create a global topic
  GET    /api/agents/{agent_id}/analysis-topics             — list topics for an agent
  POST   /api/agents/{agent_id}/analysis-topics             — create a topic for an agent
  PATCH  /api/analysis-topics/{id}                         — update a topic
  DELETE /api/analysis-topics/{id}                         — delete a topic
  POST   /api/analysis-topics/{id}/facts/{fact_id}         — connect a fact
  DELETE /api/analysis-topics/{id}/facts/{fact_id}         — disconnect a fact
  GET    /api/analysis-topics/{id}/facts                   — list connected facts
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import AgentService, AnalysisTopicService, AgentFactService
from app.mongodb.models.analysis_topic import MongoAnalysisTopic

router = APIRouter(tags=["analysis-topics"])

VALID_STATUSES = {"draft", "active", "completed", "archived"}


# ── Schemas ──────────────────────────────────────────

class TopicCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "active"
    category: Optional[str] = None
    tags: List[str] = []
    fact_ids: List[str] = []


class TopicUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


# ── Helpers ──────────────────────────────────────────

def _topic_to_response(t: MongoAnalysisTopic) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "agent_id": t.agent_id,
        "category": t.category,
        "fact_ids": t.fact_ids,
        "tags": t.tags,
        "linked_video_ids": getattr(t, 'linked_video_ids', []) or [],
        "linked_idea_ids": getattr(t, 'linked_idea_ids', []) or [],
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if isinstance(t.created_at, datetime) else str(t.created_at),
        "updated_at": t.updated_at.isoformat() if isinstance(t.updated_at, datetime) else str(t.updated_at),
    }


# ── Global Endpoints ─────────────────────────────────

@router.get("/api/analysis-topics")
async def list_all_topics(
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Text search in title/description"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all analysis topics (global view)."""
    svc = AnalysisTopicService(db)
    if search:
        items = await svc.search_by_text(search, limit=limit)
    else:
        items = await svc.get_global(status=status, limit=limit, skip=skip)
    return {"items": [_topic_to_response(t) for t in items], "total": len(items)}


@router.post("/api/analysis-topics", status_code=201)
async def create_global_topic(
    body: TopicCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a global analysis topic (not bound to any agent)."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")

    topic = MongoAnalysisTopic(
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        status=body.status,
        agent_id=None,
        category=body.category,
        fact_ids=body.fact_ids,
        tags=body.tags,
        created_by="user",
    )
    svc = AnalysisTopicService(db)
    created = await svc.create(topic)
    return _topic_to_response(created)


# ── Link / Unlink ────────────────────────────────────

class TopicLinkRequest(BaseModel):
    target_type: str  # "video", "idea"
    target_id: str


@router.post("/api/analysis-topics/{topic_id}/link")
async def link_entity_to_topic(
    topic_id: str,
    body: TopicLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Link a video or idea to an analysis topic."""
    svc = AnalysisTopicService(db)
    topic = await svc.get_by_id(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Analysis topic not found")
    field_map = {"video": "linked_video_ids", "idea": "linked_idea_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": topic_id}, {"$addToSet": {field: body.target_id}})
    updated = await svc.get_by_id(topic_id)
    return _topic_to_response(updated)


@router.post("/api/analysis-topics/{topic_id}/unlink")
async def unlink_entity_from_topic(
    topic_id: str,
    body: TopicLinkRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unlink a video or idea from an analysis topic."""
    svc = AnalysisTopicService(db)
    topic = await svc.get_by_id(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Analysis topic not found")
    field_map = {"video": "linked_video_ids", "idea": "linked_idea_ids"}
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")
    await svc.collection.update_one({"_id": topic_id}, {"$pull": {field: body.target_id}})
    updated = await svc.get_by_id(topic_id)
    return _topic_to_response(updated)


@router.get("/api/analysis-topics/{topic_id}")
async def get_topic(
    topic_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single analysis topic."""
    svc = AnalysisTopicService(db)
    topic = await svc.get_by_id(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Analysis topic not found")
    return _topic_to_response(topic)


@router.patch("/api/analysis-topics/{topic_id}")
async def update_topic(
    topic_id: str,
    body: TopicUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update an analysis topic."""
    svc = AnalysisTopicService(db)
    existing = await svc.get_by_id(topic_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Analysis topic not found")

    update_data = {}
    if body.title is not None:
        update_data["title"] = body.title.strip()
    if body.description is not None:
        update_data["description"] = body.description.strip()
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
        update_data["status"] = body.status
    if body.tags is not None:
        update_data["tags"] = body.tags
    if body.category is not None:
        update_data["category"] = body.category if body.category else None

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(topic_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Analysis topic not found")
        return _topic_to_response(updated)

    return _topic_to_response(existing)


@router.delete("/api/analysis-topics/{topic_id}")
async def delete_topic(
    topic_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete an analysis topic."""
    svc = AnalysisTopicService(db)
    existing = await svc.get_by_id(topic_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Analysis topic not found")
    await svc.delete(topic_id)
    return {"detail": "Deleted"}


# ── Fact connection endpoints ────────────────────────

@router.post("/api/analysis-topics/{topic_id}/facts/{fact_id}", status_code=200)
async def connect_fact(
    topic_id: str,
    fact_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Connect an existing fact to a topic."""
    svc = AnalysisTopicService(db)
    topic = await svc.get_by_id(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Analysis topic not found")

    # Verify fact exists
    fact_svc = AgentFactService(db)
    fact = await fact_svc.get_by_id(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    await svc.add_fact(topic_id, fact_id)
    updated = await svc.get_by_id(topic_id)
    return _topic_to_response(updated)


@router.delete("/api/analysis-topics/{topic_id}/facts/{fact_id}")
async def disconnect_fact(
    topic_id: str,
    fact_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Disconnect a fact from a topic."""
    svc = AnalysisTopicService(db)
    topic = await svc.get_by_id(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Analysis topic not found")

    await svc.remove_fact(topic_id, fact_id)
    updated = await svc.get_by_id(topic_id)
    return _topic_to_response(updated)


@router.get("/api/analysis-topics/{topic_id}/facts")
async def list_topic_facts(
    topic_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all facts connected to a topic."""
    svc = AnalysisTopicService(db)
    topic = await svc.get_by_id(topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Analysis topic not found")

    fact_svc = AgentFactService(db)
    facts = []
    for fid in topic.fact_ids:
        f = await fact_svc.get_by_id(fid)
        if f:
            facts.append({
                "id": f.id,
                "agent_id": f.agent_id,
                "type": f.type,
                "content": f.content,
                "source": f.source,
                "verified": f.verified,
                "confidence": f.confidence,
                "tags": f.tags,
                "created_at": f.created_at.isoformat() if isinstance(f.created_at, datetime) else str(f.created_at),
            })
    return {"items": facts, "total": len(facts)}


# ── Per-Agent Endpoints ──────────────────────────────

@router.get("/api/agents/{agent_id}/analysis-topics")
async def list_agent_topics(
    agent_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Text search"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List analysis topics for a specific agent."""
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    svc = AnalysisTopicService(db)
    if search:
        items = await svc.search_by_text(search, agent_id=agent_id, limit=limit)
    else:
        items = await svc.get_by_agent(agent_id, status=status, limit=limit, skip=skip)
    return {"items": [_topic_to_response(t) for t in items], "total": len(items)}


@router.post("/api/agents/{agent_id}/analysis-topics", status_code=201)
async def create_agent_topic(
    agent_id: str,
    body: TopicCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create an analysis topic for a specific agent."""
    agent = await AgentService(db).get_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")

    topic = MongoAnalysisTopic(
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        status=body.status,
        agent_id=agent_id,
        category=body.category,
        fact_ids=body.fact_ids,
        tags=body.tags,
        created_by="user",
    )
    svc = AnalysisTopicService(db)
    created = await svc.create(topic)
    return _topic_to_response(created)
