"""Watched Videos API — CRUD endpoints for video transcripts fetched via ScrapeCreators."""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models.user import MongoUser
from app.mongodb.models.watched_video import MongoWatchedVideo
from app.mongodb.services import WatchedVideoService
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/api/watched-videos", tags=["watched-videos"])


# ── Response schemas ──────────────────────────────────────────────────

class WatchedVideoResponse(BaseModel):
    id: str
    url: str
    platform: str
    video_id: Optional[str] = None
    title: Optional[str] = None
    transcript: Optional[str] = None
    language: Optional[str] = None
    author: Optional[str] = None
    agent_id: Optional[str] = None
    credits_used: int = 1
    error: Optional[str] = None
    created_at: str


class WatchedVideoListResponse(BaseModel):
    items: list[WatchedVideoResponse]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("", response_model=WatchedVideoListResponse)
async def list_watched_videos(
    platform: Optional[str] = Query(None, description="Filter by platform (youtube, tiktok, instagram, facebook, twitter)"),
    search: Optional[str] = Query(None, description="Search by URL, title, or transcript text"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List watched videos with optional filters."""
    svc = WatchedVideoService(db)

    if search:
        items = await svc.search(search, limit=limit)
    elif agent_id:
        items = await svc.get_by_agent(agent_id, limit=limit, skip=offset)
    elif platform:
        items = await svc.get_by_platform(platform, limit=limit, skip=offset)
    else:
        items = await svc.get_all(skip=offset, limit=limit)

    total = await svc.count({})
    return WatchedVideoListResponse(
        items=[_to_response(v) for v in items],
        total=total,
    )


@router.get("/{video_id}", response_model=WatchedVideoResponse)
async def get_watched_video(
    video_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single watched video by ID."""
    svc = WatchedVideoService(db)
    video = await svc.get_by_id(str(video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Watched video not found")
    return _to_response(video)


@router.delete("/{video_id}", response_model=MessageResponse)
async def delete_watched_video(
    video_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a watched video record."""
    svc = WatchedVideoService(db)
    video = await svc.get_by_id(str(video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Watched video not found")
    await svc.delete(str(video_id))
    return MessageResponse(message="Watched video deleted")


@router.delete("", response_model=MessageResponse)
async def delete_all_watched_videos(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete all watched video records."""
    svc = WatchedVideoService(db)
    result = await svc.collection.delete_many({})
    return MessageResponse(message=f"Deleted {result.deleted_count} watched video(s)")


# ── Helpers ───────────────────────────────────────────────────────────

def _to_response(v: MongoWatchedVideo) -> WatchedVideoResponse:
    return WatchedVideoResponse(
        id=v.id,
        url=v.url,
        platform=v.platform,
        video_id=v.video_id,
        title=v.title,
        transcript=v.transcript[:2000] if v.transcript else None,
        language=v.language,
        author=v.author,
        agent_id=v.agent_id,
        credits_used=v.credits_used,
        error=v.error,
        created_at=v.created_at.isoformat() if hasattr(v.created_at, 'isoformat') else str(v.created_at),
    )
