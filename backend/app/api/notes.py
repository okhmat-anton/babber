"""
Notes API.

User notes management.

Endpoints:
  GET    /api/notes                          — list all notes
  POST   /api/notes                          — create a note
  GET    /api/notes/{id}                     — get a single note
  PATCH  /api/notes/{id}                     — update a note
  DELETE /api/notes/{id}                     — delete a note
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import NoteService
from app.mongodb.models.note import MongoNote

router = APIRouter(tags=["notes"])

VALID_STATUSES = {"active", "completed", "archived"}
VALID_PRIORITIES = {"low", "medium", "high"}


# ── Schemas ──────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    content: str = ""
    category: Optional[str] = None
    priority: str = "medium"
    status: str = "active"
    tags: List[str] = []
    in_context: bool = True


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    in_context: Optional[bool] = None


# ── Helpers ──────────────────────────────────────────

def _note_to_response(note: MongoNote) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "category": note.category,
        "priority": note.priority,
        "status": note.status,
        "tags": note.tags,
        "in_context": note.in_context,
        "sort_order": getattr(note, 'sort_order', 0),
        "linked_idea_ids": getattr(note, 'linked_idea_ids', []) or [],
        "linked_fact_ids": getattr(note, 'linked_fact_ids', []) or [],
        "created_at": note.created_at.isoformat() if isinstance(note.created_at, datetime) else str(note.created_at),
        "updated_at": note.updated_at.isoformat() if isinstance(note.updated_at, datetime) else str(note.updated_at),
    }


# ── Endpoints ────────────────────────────────────────

@router.get("/api/notes")
async def list_notes(
    status: Optional[str] = Query(None, description="Filter by status: active, completed, archived"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Text search in title/content"),
    in_context: Optional[bool] = Query(None, description="Filter by in_context flag"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all notes."""
    svc = NoteService(db)
    items = await svc.get_all_notes(
        status=status, category=category, search=search,
        in_context=in_context, limit=limit, skip=skip,
    )
    return {"items": [_note_to_response(n) for n in items], "total": len(items)}


@router.post("/api/notes", status_code=201)
async def create_note(
    body: NoteCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a note."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")

    note = MongoNote(
        title=body.title.strip(),
        content=body.content.strip() if body.content else "",
        category=body.category,
        priority=body.priority,
        status=body.status,
        tags=body.tags or [],
        in_context=body.in_context,
    )
    svc = NoteService(db)
    created = await svc.create(note)
    return _note_to_response(created)


@router.get("/api/notes/{note_id}")
async def get_note(
    note_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single note by ID."""
    svc = NoteService(db)
    note = await svc.get_by_id(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return _note_to_response(note)


@router.patch("/api/notes/{note_id}")
async def update_note(
    note_id: str,
    body: NoteUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update a note."""
    svc = NoteService(db)
    existing = await svc.get_by_id(note_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(VALID_STATUSES)}")
    if "priority" in update_data and update_data["priority"] not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"priority must be one of: {', '.join(VALID_PRIORITIES)}")
    if "title" in update_data:
        update_data["title"] = update_data["title"].strip()
    if "content" in update_data:
        update_data["content"] = update_data["content"].strip() if update_data["content"] else ""

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = await svc.update(note_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Note not found")
    return _note_to_response(updated)


@router.delete("/api/notes/{note_id}")
async def delete_note(
    note_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a note."""
    svc = NoteService(db)
    existing = await svc.get_by_id(note_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Note not found")
    await svc.delete(note_id)
    return {"status": "deleted"}


# ── Reorder ──────────────────────────────────────────

class ReorderRequest(BaseModel):
    ids: List[str]  # ordered list of item IDs within a category


@router.post("/api/notes/reorder")
async def reorder_notes(
    body: ReorderRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update sort_order for notes based on the provided order."""
    svc = NoteService(db)
    for idx, item_id in enumerate(body.ids):
        await svc.update(item_id, {"sort_order": idx})
    return {"status": "ok", "updated": len(body.ids)}
