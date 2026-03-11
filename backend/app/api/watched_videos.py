"""Watched Videos API — CRUD endpoints for video transcripts fetched via ScrapeCreators."""
import logging
import httpx
from uuid import UUID
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models.user import MongoUser
from app.mongodb.models.watched_video import MongoWatchedVideo
from app.mongodb.services import WatchedVideoService
from app.schemas.common import MessageResponse
from app.api.settings import get_setting_value

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
    category: Optional[str] = None
    credits_used: int = 1
    error: Optional[str] = None
    linked_fact_ids: list[str] = []
    linked_analysis_ids: list[str] = []
    linked_idea_ids: list[str] = []
    linked_chat_session_ids: list[str] = []
    created_at: str


class WatchedVideoListResponse(BaseModel):
    items: list[WatchedVideoResponse]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("", response_model=WatchedVideoListResponse)
async def list_watched_videos(
    platform: Optional[str] = Query(None, description="Filter by platform (youtube, tiktok, instagram, facebook, twitter)"),
    category: Optional[str] = Query(None, description="Filter by category"),
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
    else:
        filt = {}
        if agent_id:
            filt["agent_id"] = agent_id
        if platform:
            filt["platform"] = platform
        if category:
            filt["category"] = category
        if filt:
            cursor = svc.collection.find(filt).sort("created_at", -1).skip(offset).limit(limit)
            docs = await cursor.to_list(length=limit)
            items = [MongoWatchedVideo.from_mongo(doc) for doc in docs]
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


# ── Update video (category, title, etc.) ──────────────────────────────

class UpdateVideoRequest(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    agent_id: Optional[str] = None
    linked_fact_ids: Optional[list[str]] = None
    linked_analysis_ids: Optional[list[str]] = None
    linked_idea_ids: Optional[list[str]] = None
    linked_chat_session_ids: Optional[list[str]] = None


@router.patch("/{video_id}", response_model=WatchedVideoResponse)
async def update_watched_video(
    video_id: UUID,
    body: UpdateVideoRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update a watched video record (category, title, etc.)."""
    svc = WatchedVideoService(db)
    video = await svc.get_by_id(str(video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Watched video not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await svc.collection.update_one({"_id": str(video_id)}, {"$set": updates})
        video = await svc.get_by_id(str(video_id))
    return _to_response(video)


# ── Add video (URL only, no transcript) ───────────────────────────────

class AddVideoRequest(BaseModel):
    url: str
    category: Optional[str] = None


@router.post("", response_model=WatchedVideoResponse, status_code=201)
async def add_video(
    body: AddVideoRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Save a video URL to the list without fetching transcript."""
    from app.services.staged_pipeline import _detect_video_platform

    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    svc = WatchedVideoService(db)

    # Check if already exists
    existing = await svc.get_by_url(url)
    if existing:
        return _to_response(existing)

    platform, _ = _detect_video_platform(url)
    record = MongoWatchedVideo(url=url, platform=platform or "unknown", category=body.category or None)
    created = await svc.create(record)
    return _to_response(created)


# ── Fetch transcript via ScrapeCreators ───────────────────────────────

class FetchTranscriptRequest(BaseModel):
    url: Optional[str] = None
    video_id: Optional[str] = None
    language: Optional[str] = None
    force: bool = False


class FetchTranscriptResponse(BaseModel):
    id: str
    url: str
    platform: str
    video_id: Optional[str] = None
    transcript: Optional[str] = None
    language: Optional[str] = None
    cached: bool = False
    error: Optional[str] = None


@router.post("/fetch", response_model=FetchTranscriptResponse)
async def fetch_video_transcript(
    body: FetchTranscriptRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Fetch video transcript via ScrapeCreators API. Accepts url or video_id of an existing record."""
    from app.services.staged_pipeline import _detect_video_platform, _parse_transcript_response

    logger.info("Transcript fetch request: video_id=%s, url=%s, force=%s", body.video_id, body.url, body.force)
    language = body.language.strip() if body.language else None
    svc = WatchedVideoService(db)
    existing = None

    # Resolve existing record
    if body.video_id:
        existing = await svc.get_by_id(body.video_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Video not found")
    elif body.url:
        existing = await svc.get_by_url(body.url.strip())

    url = (existing.url if existing else (body.url or "")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL or video_id is required")

    # Return cached transcript if already fetched (unless force regenerate)
    if existing and existing.transcript and not body.force:
        logger.info("Returning cached transcript for %s (len=%d)", url, len(existing.transcript))
        return FetchTranscriptResponse(
            id=existing.id, url=existing.url, platform=existing.platform,
            video_id=existing.video_id, transcript=existing.transcript,
            language=existing.language, cached=True,
        )

    # Get API key
    api_key = await get_setting_value(db, "scrapecreators_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="ScrapeCreators API key not configured. Add it in Settings.")

    platform, api_path = _detect_video_platform(url)
    if not platform:
        raise HTTPException(status_code=400, detail="Unsupported video URL")

    params = {"url": url}
    if language:
        params["language"] = language

    # Read configurable timeout (default 120s)
    timeout_str = await get_setting_value(db, "transcript_fetch_timeout")
    timeout_sec = int(timeout_str) if timeout_str and timeout_str.isdigit() else 120
    logger.info("Fetching transcript from ScrapeCreators: platform=%s, url=%s, timeout=%ds", platform, url, timeout_sec)

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            resp = await client.get(
                f"https://api.scrapecreators.com{api_path}",
                params=params,
                headers={"x-api-key": api_key},
            )
        logger.info("ScrapeCreators response: status=%d, content_length=%d", resp.status_code, len(resp.content))
        if resp.status_code != 200:
            error_detail = resp.text[:500]
            error_msg = f"HTTP {resp.status_code}: {error_detail}"
            logger.warning("ScrapeCreators API error for %s: %s", url, error_msg)
            if existing:
                await svc.collection.update_one({"_id": existing.id}, {"$set": {"error": error_msg}})
            else:
                failed = MongoWatchedVideo(url=url, platform=platform, error=error_msg)
                await svc.create(failed)
            raise HTTPException(status_code=502, detail=f"ScrapeCreators API error ({resp.status_code}): {error_detail}")
        data = resp.json()
    except httpx.TimeoutException as e:
        logger.error("ScrapeCreators timeout after %ds for %s: %s", timeout_sec, url, e)
        raise HTTPException(status_code=504, detail=f"ScrapeCreators request timed out after {timeout_sec}s. Increase 'transcript_fetch_timeout' in Settings.")
    except httpx.HTTPError as e:
        logger.error("ScrapeCreators HTTP error for %s: %s", url, e)
        raise HTTPException(status_code=502, detail=f"ScrapeCreators request failed: {e}")

    transcript_text, video_id, segments, lang = _parse_transcript_response(platform, data)
    logger.info("Parsed transcript: platform=%s, has_text=%s, video_id=%s, lang=%s, segments=%d",
               platform, bool(transcript_text), video_id, lang, len(segments) if segments else 0)

    if not transcript_text:
        error_msg = "No transcript available"
        logger.warning("No transcript text for %s (response keys: %s)", url, list(data.keys()))
        if existing:
            await svc.collection.update_one({"_id": existing.id}, {"$set": {"error": error_msg, "video_id": video_id, "language": lang}})
        else:
            record = MongoWatchedVideo(url=url, platform=platform, video_id=video_id, language=lang, error=error_msg)
            await svc.create(record)
        raise HTTPException(status_code=404, detail="No transcript available for this video")

    # Update existing record or create new one
    if existing:
        await svc.collection.update_one(
            {"_id": existing.id},
            {"$set": {
                "transcript": transcript_text,
                "transcript_segments": segments,
                "video_id": video_id,
                "language": lang or language,
                "metadata": {"raw_keys": list(data.keys())},
            }},
        )
        return FetchTranscriptResponse(
            id=existing.id, url=url, platform=platform,
            video_id=video_id, transcript=transcript_text,
            language=lang or language, cached=False,
        )
    else:
        record = MongoWatchedVideo(
            url=url, platform=platform, video_id=video_id,
            transcript=transcript_text, transcript_segments=segments,
            language=lang or language, metadata={"raw_keys": list(data.keys())},
        )
        created = await svc.create(record)
        return FetchTranscriptResponse(
            id=created.id, url=url, platform=platform,
            video_id=video_id, transcript=transcript_text,
            language=lang or language, cached=False,
        )


# ── Link / Unlink endpoints ────────────────────────────────────────────

class LinkRequest(BaseModel):
    target_type: str  # "fact", "analysis", "idea", "chat_session"
    target_id: str


@router.post("/{video_id}/link", response_model=WatchedVideoResponse)
async def link_entity_to_video(
    video_id: str,
    body: LinkRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Link a fact, analysis topic, idea, or chat session to a video."""
    svc = WatchedVideoService(db)
    video = await svc.get_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    field_map = {
        "fact": "linked_fact_ids",
        "analysis": "linked_analysis_ids",
        "idea": "linked_idea_ids",
        "chat_session": "linked_chat_session_ids",
    }
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")

    await svc.collection.update_one(
        {"_id": video_id},
        {"$addToSet": {field: body.target_id}},
    )
    video = await svc.get_by_id(video_id)
    return _to_response(video)


@router.post("/{video_id}/unlink", response_model=WatchedVideoResponse)
async def unlink_entity_from_video(
    video_id: str,
    body: LinkRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unlink a fact, analysis topic, idea, or chat session from a video."""
    svc = WatchedVideoService(db)
    video = await svc.get_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    field_map = {
        "fact": "linked_fact_ids",
        "analysis": "linked_analysis_ids",
        "idea": "linked_idea_ids",
        "chat_session": "linked_chat_session_ids",
    }
    field = field_map.get(body.target_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Invalid target_type: {body.target_type}")

    await svc.collection.update_one(
        {"_id": video_id},
        {"$pull": {field: body.target_id}},
    )
    video = await svc.get_by_id(video_id)
    return _to_response(video)


@router.get("/{video_id}/full-transcript")
async def get_full_transcript(
    video_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get the full (non-truncated) transcript of a watched video."""
    svc = WatchedVideoService(db)
    video = await svc.get_by_id(str(video_id))
    if not video:
        raise HTTPException(status_code=404, detail="Watched video not found")
    return {"id": video.id, "transcript": video.transcript or ""}


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
        category=v.category,
        credits_used=v.credits_used,
        error=v.error,
        linked_fact_ids=v.linked_fact_ids or [],
        linked_analysis_ids=v.linked_analysis_ids or [],
        linked_idea_ids=v.linked_idea_ids or [],
        linked_chat_session_ids=v.linked_chat_session_ids or [],
        created_at=v.created_at.isoformat() if hasattr(v.created_at, 'isoformat') else str(v.created_at),
    )
