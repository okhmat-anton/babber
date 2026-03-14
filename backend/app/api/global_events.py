"""
Global Events API.

Provides a global view of all events across all agents.
Also allows creating events with an explicit agent_id.

Endpoints:
  GET  /api/events         — list all events across all agents
  POST /api/events         — create an event (agent_id in body)
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import AgentEventService, AgentService
from app.mongodb.models.agent_event import MongoAgentEvent

router = APIRouter(prefix="/api/events", tags=["global-events"])

VALID_EVENT_TYPES = {"conversation", "observation", "discovery", "decision", "milestone", "custom"}
VALID_IMPORTANCE = {"low", "medium", "high", "critical"}


# ── Schemas ──────────────────────────────────────────

class GlobalEventCreate(BaseModel):
    agent_id: str
    event_type: str = "observation"
    title: str
    description: str = ""
    comment: str = ""
    source: str = "user"
    importance: str = "medium"
    tags: List[str] = []
    event_date: Optional[str] = None


# ── Helpers ──────────────────────────────────────────

def _event_to_response(e: MongoAgentEvent) -> dict:
    return {
        "id": e.id,
        "agent_id": e.agent_id,
        "event_type": e.event_type,
        "title": e.title,
        "description": e.description,
        "comment": e.comment,
        "source": e.source,
        "importance": e.importance,
        "tags": e.tags,
        "created_by": e.created_by,
        "sort_order": getattr(e, 'sort_order', 0),
        "event_date": e.event_date.isoformat() if isinstance(e.event_date, datetime) else str(e.event_date),
        "created_at": e.created_at.isoformat() if isinstance(e.created_at, datetime) else str(e.created_at),
        "updated_at": e.updated_at.isoformat() if isinstance(e.updated_at, datetime) else str(e.updated_at),
    }


# ── Endpoints ────────────────────────────────────────

@router.get("")
async def list_all_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    importance: Optional[str] = Query(None, description="Filter by importance"),
    search: Optional[str] = Query(None, description="Text search in title/description"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all events across all agents (global view). Optionally filter by agent."""
    svc = AgentEventService(db)

    if agent_id:
        items = await svc.get_by_agent(agent_id, event_type=event_type, importance=importance, limit=limit, skip=skip)
    else:
        items = await svc.get_all(event_type=event_type, importance=importance, search=search, limit=limit, skip=skip)

    return {"items": [_event_to_response(e) for e in items], "total": len(items)}


@router.post("", status_code=201)
async def create_global_event(
    body: GlobalEventCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create an event with an explicit agent_id."""
    agent = await AgentService(db).get_by_id(body.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.event_type not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"event_type must be one of: {', '.join(VALID_EVENT_TYPES)}")
    if body.importance not in VALID_IMPORTANCE:
        raise HTTPException(status_code=400, detail=f"importance must be one of: {', '.join(VALID_IMPORTANCE)}")

    event_date = datetime.now(timezone.utc)
    if body.event_date:
        try:
            event_date = datetime.fromisoformat(body.event_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid event_date format (expected ISO 8601)")

    event = MongoAgentEvent(
        agent_id=body.agent_id,
        event_type=body.event_type,
        title=body.title.strip(),
        description=body.description.strip() if body.description else "",
        comment=body.comment.strip() if body.comment else "",
        source=body.source,
        importance=body.importance,
        tags=body.tags,
        created_by="user",
        event_date=event_date,
    )

    svc = AgentEventService(db)
    created = await svc.create(event)
    return _event_to_response(created)


@router.patch("/{event_id}")
async def update_global_event(
    event_id: str,
    body: dict,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update an event from the global view."""
    svc = AgentEventService(db)
    existing = await svc.get_by_id(event_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")

    update_data = {}
    for field in ("event_type", "title", "description", "comment", "source", "importance", "tags"):
        if field in body and body[field] is not None:
            val = body[field]
            if field in ("title", "description", "comment") and isinstance(val, str):
                val = val.strip()
            update_data[field] = val

    if "event_type" in update_data and update_data["event_type"] not in VALID_EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"event_type must be one of: {', '.join(VALID_EVENT_TYPES)}")
    if "importance" in update_data and update_data["importance"] not in VALID_IMPORTANCE:
        raise HTTPException(status_code=400, detail=f"importance must be one of: {', '.join(VALID_IMPORTANCE)}")

    if "event_date" in body and body["event_date"] is not None:
        try:
            update_data["event_date"] = datetime.fromisoformat(body["event_date"]).isoformat()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid event_date format")

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(event_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Event not found")
        return _event_to_response(updated)

    return _event_to_response(existing)


@router.delete("/{event_id}")
async def delete_global_event(
    event_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete an event from the global view."""
    svc = AgentEventService(db)
    existing = await svc.get_by_id(event_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")
    await svc.delete(event_id)
    return {"detail": "Deleted"}


# ── Reorder ──────────────────────────────────────────

class ReorderRequest(BaseModel):
    ids: List[str]


@router.post("/reorder")
async def reorder_events(
    body: ReorderRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update sort_order for events based on the provided order."""
    svc = AgentEventService(db)
    for idx, item_id in enumerate(body.ids):
        await svc.update(item_id, {"sort_order": idx})
    return {"status": "ok", "updated": len(body.ids)}