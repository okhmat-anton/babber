"""
Research Resources API — Trusted sources for agent research.

Agents and users can manage a list of trusted resources (websites, APIs, docs)
that agents use for research. Each resource has trust levels, ratings, and
search instructions.

Two research modes:
  - Simple research: uses resources with trust_level >= "medium"
  - Deep research: uses only resources with trust_level == "highest"

Endpoints:
  GET    /api/research-resources              — list all resources
  POST   /api/research-resources              — create a resource
  GET    /api/research-resources/{id}         — get single resource
  PATCH  /api/research-resources/{id}         — update a resource
  DELETE /api/research-resources/{id}         — delete a resource
  POST   /api/research-resources/{id}/use     — record a usage (increment counter)
  GET    /api/research-resources/by-trust     — get resources by minimum trust level
"""
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.services import ResearchResourceService
from app.mongodb.models.research_resource import MongoResearchResource, RssFeed

router = APIRouter(prefix="/api/research-resources", tags=["research-resources"])


# ── Schemas ──────────────────────────────────────────

class RssFeedCreate(BaseModel):
    url: str
    title: str = ""
    category: str = "general"  # news, blog, releases, updates, discussions
    is_active: bool = True


class ResourceCreate(BaseModel):
    name: str
    url: str
    description: str = ""
    trust_level: str = "medium"  # low, medium, high, highest
    user_rating: float = 5.0
    agent_rating: float = 5.0
    search_instructions: str = ""
    category: str = "general"
    tags: List[str] = []
    rss_feeds: List[RssFeedCreate] = []
    is_active: bool = True
    added_by: str = "user"


class ResourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    trust_level: Optional[str] = None
    user_rating: Optional[float] = None
    agent_rating: Optional[float] = None
    search_instructions: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    rss_feeds: Optional[List[RssFeedCreate]] = None
    is_active: Optional[bool] = None


class RssFeedResponse(BaseModel):
    id: str
    url: str
    title: str
    category: str
    is_active: bool


class ResourceResponse(BaseModel):
    id: str
    name: str
    url: str
    description: str
    trust_level: str
    user_rating: float
    agent_rating: float
    search_instructions: str
    category: str
    tags: List[str]
    rss_feeds: List[RssFeedResponse] = []
    is_active: bool
    added_by: str
    last_used_at: Optional[str] = None
    use_count: int
    created_at: str
    updated_at: str


# ── Helpers ──────────────────────────────────────────

VALID_TRUST_LEVELS = ("low", "medium", "high", "highest")
VALID_CATEGORIES = ("docs", "forum", "wiki", "news", "code", "general", "academic", "social", "search", "patent")


def _resource_to_response(r: MongoResearchResource) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "url": r.url,
        "description": r.description,
        "trust_level": r.trust_level,
        "user_rating": r.user_rating,
        "agent_rating": r.agent_rating,
        "search_instructions": r.search_instructions,
        "category": r.category,
        "tags": r.tags,
        "is_active": r.is_active,
        "added_by": r.added_by,
        "last_used_at": r.last_used_at.isoformat() if isinstance(r.last_used_at, datetime) else r.last_used_at,
        "rss_feeds": [f.model_dump() for f in (r.rss_feeds or [])],
        "use_count": r.use_count,
        "created_at": r.created_at.isoformat() if isinstance(r.created_at, datetime) else str(r.created_at),
        "updated_at": r.updated_at.isoformat() if isinstance(r.updated_at, datetime) else str(r.updated_at),
    }


# ── Endpoints ────────────────────────────────────────

@router.get("")
async def list_resources(
    category: Optional[str] = Query(None, description="Filter by category"),
    trust_level: Optional[str] = Query(None, description="Filter by trust level"),
    search: Optional[str] = Query(None, description="Search by name/url/description"),
    active_only: bool = Query(True, description="Only show active resources"),
    limit: int = Query(200, ge=1, le=500),
    skip: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all research resources."""
    svc = ResearchResourceService(db)

    if search:
        items = await svc.search(search, limit=limit)
    else:
        filt = {}
        if active_only:
            filt["is_active"] = True
        if category:
            filt["category"] = category
        if trust_level:
            filt["trust_level"] = trust_level
        cursor = svc.collection.find(filt).sort("user_rating", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        items = [MongoResearchResource.from_mongo(doc) for doc in docs]

    return {
        "items": [_resource_to_response(r) for r in items],
        "total": len(items),
    }


@router.get("/by-trust")
async def get_by_trust_level(
    min_level: str = Query("medium", description="Minimum trust level: low, medium, high, highest"),
    limit: int = Query(100, ge=1, le=500),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get resources by minimum trust level (for research protocols)."""
    if min_level not in VALID_TRUST_LEVELS:
        raise HTTPException(status_code=400, detail=f"trust_level must be one of: {', '.join(VALID_TRUST_LEVELS)}")

    svc = ResearchResourceService(db)
    items = await svc.get_by_trust_level(min_level, limit=limit)
    return {
        "items": [_resource_to_response(r) for r in items],
        "total": len(items),
    }


@router.post("", status_code=201)
async def create_resource(
    body: ResourceCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a new research resource."""
    if body.trust_level not in VALID_TRUST_LEVELS:
        raise HTTPException(status_code=400, detail=f"trust_level must be one of: {', '.join(VALID_TRUST_LEVELS)}")

    resource = MongoResearchResource(
        name=body.name.strip(),
        url=body.url.strip(),
        description=body.description.strip(),
        trust_level=body.trust_level,
        user_rating=max(0, min(10, body.user_rating)),
        agent_rating=max(0, min(10, body.agent_rating)),
        search_instructions=body.search_instructions.strip(),
        category=body.category,
        tags=body.tags,
        rss_feeds=[RssFeed(url=f.url.strip(), title=f.title.strip(), category=f.category, is_active=f.is_active) for f in body.rss_feeds],
        is_active=body.is_active,
        added_by=body.added_by,
    )

    svc = ResearchResourceService(db)
    created = await svc.create(resource)
    return _resource_to_response(created)


@router.get("/{resource_id}")
async def get_resource(
    resource_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single research resource."""
    svc = ResearchResourceService(db)
    resource = await svc.get_by_id(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return _resource_to_response(resource)


@router.patch("/{resource_id}")
async def update_resource(
    resource_id: str,
    body: ResourceUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update a research resource."""
    svc = ResearchResourceService(db)
    existing = await svc.get_by_id(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Resource not found")

    update_data = {}
    if body.name is not None:
        update_data["name"] = body.name.strip()
    if body.url is not None:
        update_data["url"] = body.url.strip()
    if body.description is not None:
        update_data["description"] = body.description.strip()
    if body.trust_level is not None:
        if body.trust_level not in VALID_TRUST_LEVELS:
            raise HTTPException(status_code=400, detail=f"trust_level must be one of: {', '.join(VALID_TRUST_LEVELS)}")
        update_data["trust_level"] = body.trust_level
    if body.user_rating is not None:
        update_data["user_rating"] = max(0, min(10, body.user_rating))
    if body.agent_rating is not None:
        update_data["agent_rating"] = max(0, min(10, body.agent_rating))
    if body.search_instructions is not None:
        update_data["search_instructions"] = body.search_instructions.strip()
    if body.category is not None:
        update_data["category"] = body.category
    if body.tags is not None:
        update_data["tags"] = body.tags
    if body.rss_feeds is not None:
        update_data["rss_feeds"] = [
            RssFeed(url=f.url.strip(), title=f.title.strip(), category=f.category, is_active=f.is_active).model_dump()
            for f in body.rss_feeds
        ]
    if body.is_active is not None:
        update_data["is_active"] = body.is_active

    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = await svc.update(resource_id, update_data)
        if not updated:
            raise HTTPException(status_code=404, detail="Resource not found")
        return _resource_to_response(updated)

    return _resource_to_response(existing)


@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a research resource."""
    svc = ResearchResourceService(db)
    existing = await svc.get_by_id(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Resource not found")

    await svc.delete(resource_id)
    return {"detail": "Deleted"}


@router.post("/{resource_id}/use")
async def record_usage(
    resource_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Record that a resource was used (increments use_count, updates last_used_at)."""
    svc = ResearchResourceService(db)
    existing = await svc.get_by_id(resource_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Resource not found")

    await svc.increment_use(resource_id)
    updated = await svc.get_by_id(resource_id)
    return _resource_to_response(updated)
