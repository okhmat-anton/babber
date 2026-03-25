"""
Creator Profile API — manage info about the bot owner/creator.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Literal
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import CreatorProfileService, NoteService
from app.mongodb.models.creator_profile import GoalItem, DreamItem, IdeaItem, NoteItem, CityItem
from app.mongodb.models.note import MongoNote

router = APIRouter(prefix="/api/creator", tags=["creator"])


class CreatorProfileRequest(BaseModel):
    name: Optional[str] = None
    who: Optional[str] = None
    goals: Optional[List[GoalItem]] = None
    dreams: Optional[List[DreamItem]] = None
    skills_and_abilities: Optional[str] = None
    current_situation: Optional[str] = None
    principles: Optional[str] = None
    successes: Optional[str] = None
    failures: Optional[str] = None
    action_history: Optional[str] = None
    ideas: Optional[List[IdeaItem]] = None
    notes: Optional[List[NoteItem]] = None
    cities: Optional[List[CityItem]] = None


class CreatorProfileResponse(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    who: Optional[str] = None
    goals: Optional[List[GoalItem]] = None
    dreams: Optional[List[DreamItem]] = None
    skills_and_abilities: Optional[str] = None
    current_situation: Optional[str] = None
    principles: Optional[str] = None
    successes: Optional[str] = None
    failures: Optional[str] = None
    action_history: Optional[str] = None
    ideas: Optional[List[IdeaItem]] = None
    notes: Optional[List[NoteItem]] = None
    cities: Optional[List[CityItem]] = None


@router.get("", response_model=CreatorProfileResponse)
async def get_creator_profile(
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get creator profile."""
    svc = CreatorProfileService(db)
    profile = await svc.get_profile()
    if not profile:
        return CreatorProfileResponse()
    return CreatorProfileResponse(**profile.model_dump(exclude={"created_at", "updated_at"}))


@router.put("", response_model=CreatorProfileResponse)
async def update_creator_profile(
    body: CreatorProfileRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create or update creator profile."""
    svc = CreatorProfileService(db)
    data = body.model_dump(exclude_none=False)
    profile = await svc.upsert(data)
    return CreatorProfileResponse(**profile.model_dump(exclude={"created_at", "updated_at"}))


# ── Append single item to a list field ──────────────────

class AppendItemRequest(BaseModel):
    """Append a single item to goals, dreams, ideas, notes, or cities."""
    target: Literal["goals", "dreams", "ideas", "notes", "cities"]
    title: str = ""
    content: str = ""          # used for notes, ideas, and as description for goals/dreams
    priority: int = 1          # 0=high, 1=medium, 2=low (not used for notes)
    # City-specific fields
    country: str = ""          # country for cities
    state: str = ""            # state / region for cities
    zip_code: str = ""         # zip / postal code for cities
    city_type: str = "interest"  # home, frequent, interest


@router.post("/append-item", status_code=201)
async def append_creator_item(
    body: AppendItemRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Append a single item to a Creator profile list (goals/dreams/ideas/notes).

    Creates the profile if it does not exist yet.
    Returns the newly created item.
    """
    # Notes go to the dedicated 'notes' collection (not embedded in creator_profile)
    if body.target == "notes":
        note_svc = NoteService(db)
        note = MongoNote(
            title=body.title.strip(),
            content=body.content.strip() if body.content else "",
        )
        created = await note_svc.create(note)
        return {"ok": True, "item": {
            "id": created.id,
            "title": created.title,
            "content": created.content,
            "created_at": created.created_at.isoformat() if isinstance(created.created_at, datetime) else str(created.created_at),
        }}

    svc = CreatorProfileService(db)
    profile = await svc.get_profile()

    item_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    if body.target == "goals":
        new_item = GoalItem(id=item_id, title=body.title, description=body.content, priority=body.priority)
    elif body.target == "dreams":
        new_item = DreamItem(id=item_id, title=body.title, description=body.content, priority=body.priority)
    elif body.target == "ideas":
        new_item = IdeaItem(id=item_id, title=body.title, description=body.content, priority=body.priority)
    elif body.target == "cities":
        new_item = CityItem(id=item_id, name=body.title, country=body.country, state=body.state, zip_code=body.zip_code, type=body.city_type)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown target: {body.target}")

    # Use $push to append atomically — first ensure the field is an array (may be null)
    col = db["creator_profile"]
    if profile:
        # If the target field is null in the document, initialise it as empty array first
        await col.update_one(
            {"_id": profile.id, body.target: {"$eq": None}},
            {"$set": {body.target: []}},
        )
        await col.update_one(
            {"_id": profile.id},
            {"$push": {body.target: new_item.model_dump()}},
        )
    else:
        # No profile yet — create with single item
        from app.mongodb.models.creator_profile import MongoCreatorProfile
        new_profile = MongoCreatorProfile(**{body.target: [new_item]})
        doc = new_profile.model_dump()
        doc["_id"] = doc.pop("id")
        await col.insert_one(doc)

    return {"ok": True, "item": new_item.model_dump()}
