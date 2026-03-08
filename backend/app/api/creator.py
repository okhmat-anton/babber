"""
Creator Profile API — manage info about the bot owner/creator.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import CreatorProfileService

router = APIRouter(prefix="/api/creator", tags=["creator"])


class CreatorProfileRequest(BaseModel):
    name: Optional[str] = None
    who: Optional[str] = None
    goals: Optional[str] = None
    dreams: Optional[str] = None
    skills_and_abilities: Optional[str] = None
    current_situation: Optional[str] = None
    principles: Optional[str] = None
    successes: Optional[str] = None
    failures: Optional[str] = None
    action_history: Optional[str] = None
    ideas: Optional[str] = None


class CreatorProfileResponse(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    who: Optional[str] = None
    goals: Optional[str] = None
    dreams: Optional[str] = None
    skills_and_abilities: Optional[str] = None
    current_situation: Optional[str] = None
    principles: Optional[str] = None
    successes: Optional[str] = None
    failures: Optional[str] = None
    action_history: Optional[str] = None
    ideas: Optional[str] = None


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
