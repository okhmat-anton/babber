"""
DARPA Monitor addon — backend routes.

Scrapes DARPA JSON endpoints for opportunities, programs, news, and events.
Stores items in MongoDB with deduplication by nid and change detection.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends

from app.database import get_mongodb
from app.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/addons/darpa_monitor",
    tags=["addon-darpa-monitor"],
    dependencies=[Depends(get_current_user)],
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DARPA_BASE = "https://www.darpa.mil"
DARPA_ENDPOINTS = {
    "opportunities": "/json/opportunity.json",
    "programs": "/json/program.json",
    "news": "/json/news.json",
    "events": "/json/event.json",
}
DARPA_TAXONOMY_URL = f"{DARPA_BASE}/json/taxonomy.json"

COLLECTION = "darpa_items"   # single collection, discriminated by `category`
META_COLLECTION = "darpa_meta"  # scrape metadata (last run, stats)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_html(html: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_date(raw: Optional[str]) -> Optional[str]:
    """Parse various DARPA date formats into ISO string."""
    if not raw:
        return None
    raw = raw.strip()
    # Strip HTML time tags
    m = re.search(r'datetime="([^"]+)"', raw)
    if m:
        raw = m.group(1)
    # Try ISO parse
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw


def _normalize_opportunity(item: dict) -> dict:
    """Normalize an opportunity JSON item into our storage schema."""
    return {
        "nid": str(item.get("nid", "")),
        "category": "opportunities",
        "title": (item.get("title") or "").strip(),
        "body": _strip_html(item.get("field_body_with_summary") or item.get("field_body_with_summary_1") or ""),
        "opportunity_number": item.get("field_opportunity_number", ""),
        "office": item.get("field_taxonomy_office", ""),
        "topics": [t.strip() for t in (item.get("field_research_topics") or "").split("|") if t.strip()],
        "open_date": _parse_date(item.get("field_open_date")),
        "close_date": _parse_date(item.get("field_close_date")),
        "external_url": item.get("field_external_url", ""),
        "darpa_url": "",
    }


def _normalize_program(item: dict) -> dict:
    """Normalize a program JSON item."""
    return {
        "nid": str(item.get("nid", "")),
        "category": "programs",
        "title": (item.get("title") or "").strip(),
        "body": _strip_html(item.get("body") or ""),
        "summary": _strip_html(item.get("summary") or ""),
        "office": item.get("field_taxonomy_office", ""),
        "topics": [t.strip() for t in (item.get("field_research_topics") or "").split(",") if t.strip()],
        "status": item.get("field_program_status", ""),
        "start_date": _parse_date(item.get("field_start_date")),
        "program_manager": " ".join(filter(None, [
            item.get("field_program_manager__field_first_name", ""),
            item.get("field_program_manager__field_last_name", ""),
        ])).strip(),
        "image_url": item.get("field_media_image", "") or item.get("field_image", ""),
        "darpa_url": f"{DARPA_BASE}{item['view_node']}" if item.get("view_node") else "",
    }


def _normalize_news(item: dict) -> dict:
    """Normalize a news JSON item."""
    return {
        "nid": str(item.get("nid", "")),
        "category": "news",
        "title": (item.get("title") or "").strip(),
        "body": _strip_html(item.get("body") or ""),
        "summary": _strip_html(item.get("summary") or item.get("summary_trimmed") or ""),
        "office": item.get("field_taxonomy_office", ""),
        "topics": [t.strip() for t in (item.get("field_research_topics") or "").split(",") if t.strip()],
        "publish_date": _parse_date(item.get("field_publish_date") or item.get("field_publish_date__raw")),
        "news_category": item.get("field_category", ""),
        "image_url": item.get("field_media_image_url", "") or item.get("field_image", ""),
        "darpa_url": f"{DARPA_BASE}{item['view_node']}" if item.get("view_node") else "",
    }


def _normalize_event(item: dict) -> dict:
    """Normalize an event JSON item."""
    return {
        "nid": str(item.get("nid", "")),
        "category": "events",
        "title": (item.get("title") or "").strip(),
        "body": _strip_html(item.get("body") or ""),
        "summary": _strip_html(item.get("summary") or item.get("summary_trimmed") or ""),
        "office": item.get("field_taxonomy_office", ""),
        "topics": [t.strip() for t in (item.get("field_research_topics") or "").split(",") if t.strip()],
        "event_date": _parse_date(item.get("field_event_date__raw") or item.get("field_event_date")),
        "location": _strip_html(item.get("field_location_name") or ""),
        "address": _strip_html(item.get("field_address") or ""),
        "event_category": item.get("field_category", ""),
        "image_url": item.get("field_media_image_url", "") or item.get("field_image", ""),
        "darpa_url": f"{DARPA_BASE}{item['view_node']}" if item.get("view_node") else "",
    }


NORMALIZERS = {
    "opportunities": _normalize_opportunity,
    "programs": _normalize_program,
    "news": _normalize_news,
    "events": _normalize_event,
}


# ---------------------------------------------------------------------------
# Scraper core
# ---------------------------------------------------------------------------

async def _fetch_darpa_json(client: httpx.AsyncClient, category: str) -> list[dict]:
    """Fetch and normalize items from a DARPA JSON endpoint."""
    path = DARPA_ENDPOINTS[category]
    url = f"{DARPA_BASE}{path}"
    resp = await client.get(url)
    resp.raise_for_status()
    raw_items = resp.json()
    normalizer = NORMALIZERS[category]
    return [normalizer(item) for item in raw_items]


async def run_scrape(categories: Optional[list[str]] = None) -> dict:
    """
    Scrape DARPA data and upsert into MongoDB.
    Returns stats: {category: {total, new, updated}}.
    """
    db = get_mongodb()
    col = db[COLLECTION]
    meta = db[META_COLLECTION]

    if categories is None:
        categories = list(DARPA_ENDPOINTS.keys())

    now = datetime.now(timezone.utc)
    stats = {}

    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        headers=HTTP_HEADERS,
    ) as client:
        for cat in categories:
            try:
                items = await _fetch_darpa_json(client, cat)
            except Exception as e:
                logger.error("DARPA scrape %s failed: %s", cat, e)
                stats[cat] = {"total": 0, "new": 0, "updated": 0, "error": str(e)}
                continue

            new_count = 0
            updated_count = 0

            for item in items:
                nid = item["nid"]
                existing = await col.find_one({"nid": nid, "category": cat})

                if existing is None:
                    # New item
                    item["first_seen_at"] = now.isoformat()
                    item["last_seen_at"] = now.isoformat()
                    item["is_new"] = True
                    item["scrape_count"] = 1
                    await col.insert_one(item)
                    new_count += 1
                else:
                    # Check for changes (compare key fields)
                    changes = {}
                    for key in ("title", "body", "summary", "status", "close_date",
                                "open_date", "external_url", "office", "topics"):
                        if key in item and item[key] != existing.get(key):
                            changes[key] = item[key]

                    update_set = {
                        "last_seen_at": now.isoformat(),
                        "scrape_count": existing.get("scrape_count", 1) + 1,
                    }
                    if changes:
                        update_set.update(changes)
                        updated_count += 1

                    await col.update_one(
                        {"_id": existing["_id"]},
                        {"$set": update_set},
                    )

            stats[cat] = {"total": len(items), "new": new_count, "updated": updated_count}

    # Save scrape metadata
    await meta.update_one(
        {"_id": "last_scrape"},
        {"$set": {
            "timestamp": now.isoformat(),
            "stats": stats,
        }},
        upsert=True,
    )

    # Clear is_new flags from previous scrapes (keep only current new items)
    current_new_nids = []
    for cat in categories:
        cat_items = await col.find(
            {"category": cat, "first_seen_at": now.isoformat()}
        ).to_list(None)
        current_new_nids.extend([i["_id"] for i in cat_items])

    if current_new_nids:
        # Mark everything as not new first, then set current new items
        await col.update_many(
            {"category": {"$in": categories}, "_id": {"$nin": current_new_nids}},
            {"$set": {"is_new": False}},
        )

    logger.info("DARPA scrape completed: %s", stats)
    return stats


# ---------------------------------------------------------------------------
# Ensure indexes
# ---------------------------------------------------------------------------

async def _ensure_indexes():
    db = get_mongodb()
    col = db[COLLECTION]
    await col.create_index([("nid", 1), ("category", 1)], unique=True)
    await col.create_index([("category", 1), ("last_seen_at", -1)])
    await col.create_index([("category", 1), ("is_new", -1)])
    await col.create_index([("title", "text"), ("body", "text"), ("summary", "text")])


# Run on import (addon load)
_indexes_created = False


async def _maybe_create_indexes():
    global _indexes_created
    if not _indexes_created:
        try:
            await _ensure_indexes()
            _indexes_created = True
        except Exception as e:
            logger.warning("Failed to create DARPA indexes: %s", e)


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@router.get("/items")
async def list_items(
    category: str = Query(..., description="opportunities, programs, news, or events"),
    search: Optional[str] = Query(None),
    office: Optional[str] = Query(None),
    topic: Optional[str] = Query(None),
    new_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_field: str = Query("last_seen_at"),
    sort_dir: int = Query(-1),
):
    """List DARPA items with filters."""
    await _maybe_create_indexes()
    db = get_mongodb()
    col = db[COLLECTION]

    query: dict = {"category": category}
    if search:
        query["$text"] = {"$search": search}
    if office:
        query["office"] = {"$regex": office, "$options": "i"}
    if topic:
        query["topics"] = {"$regex": topic, "$options": "i"}
    if new_only:
        query["is_new"] = True

    total = await col.count_documents(query)
    cursor = col.find(query).sort(sort_field, sort_dir).skip(offset).limit(limit)
    items = await cursor.to_list(length=limit)

    for item in items:
        item["_id"] = str(item["_id"])

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/items/{nid}")
async def get_item(nid: str, category: str = Query(...)):
    """Get a single DARPA item by nid."""
    db = get_mongodb()
    col = db[COLLECTION]
    item = await col.find_one({"nid": nid, "category": category})
    if not item:
        raise HTTPException(404, "Item not found")
    item["_id"] = str(item["_id"])
    return item


@router.post("/scrape")
async def trigger_scrape(
    categories: Optional[list[str]] = Query(None),
):
    """Manually trigger a DARPA scrape."""
    await _maybe_create_indexes()
    valid = set(DARPA_ENDPOINTS.keys())
    if categories:
        invalid = set(categories) - valid
        if invalid:
            raise HTTPException(400, f"Invalid categories: {invalid}. Valid: {valid}")
    else:
        categories = list(valid)

    stats = await run_scrape(categories)
    return {"status": "ok", "stats": stats}


@router.get("/scrape/status")
async def scrape_status():
    """Get last scrape metadata."""
    db = get_mongodb()
    meta = db[META_COLLECTION]
    doc = await meta.find_one({"_id": "last_scrape"})
    if not doc:
        return {"last_scrape": None}
    doc.pop("_id", None)
    return {"last_scrape": doc}


@router.get("/stats")
async def get_stats():
    """Get item counts per category."""
    db = get_mongodb()
    col = db[COLLECTION]

    pipeline = [
        {"$group": {
            "_id": "$category",
            "total": {"$sum": 1},
            "new": {"$sum": {"$cond": [{"$eq": ["$is_new", True]}, 1, 0]}},
        }},
    ]
    results = {}
    async for doc in col.aggregate(pipeline):
        results[doc["_id"]] = {"total": doc["total"], "new": doc["new"]}

    meta = db[META_COLLECTION]
    meta_doc = await meta.find_one({"_id": "last_scrape"})
    last_scrape = meta_doc.get("timestamp") if meta_doc else None

    return {"categories": results, "last_scrape": last_scrape}


@router.get("/offices")
async def list_offices():
    """Get distinct offices across all items."""
    db = get_mongodb()
    col = db[COLLECTION]
    offices = await col.distinct("office")
    return {"offices": sorted([o for o in offices if o])}


@router.get("/topics")
async def list_topics():
    """Get distinct topics across all items."""
    db = get_mongodb()
    col = db[COLLECTION]
    # Topics are stored as arrays, so we need to unwind
    pipeline = [
        {"$unwind": "$topics"},
        {"$group": {"_id": "$topics"}},
        {"$sort": {"_id": 1}},
    ]
    topics = []
    async for doc in col.aggregate(pipeline):
        if doc["_id"]:
            topics.append(doc["_id"])
    return {"topics": topics}


@router.get("/agent-summary")
async def agent_summary(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    """Text summary for agent consumption."""
    db = get_mongodb()
    col = db[COLLECTION]

    query: dict = {}
    if category:
        query["category"] = category
    if search:
        query["$text"] = {"$search": search}

    items = await col.find(query).sort("last_seen_at", -1).limit(limit).to_list(length=limit)

    if not items:
        return {"summary": "No DARPA items found matching the query."}

    lines = [f"DARPA Monitor — {len(items)} items:"]
    for item in items:
        cat = item.get("category", "")
        title = item.get("title", "")
        office = item.get("office", "")
        topics = ", ".join(item.get("topics", []))
        is_new = " [NEW]" if item.get("is_new") else ""
        url = item.get("darpa_url") or item.get("external_url", "")

        line = f"- [{cat.upper()}]{is_new} {title}"
        if office:
            line += f" | Office: {office}"
        if topics:
            line += f" | Topics: {topics}"

        # Category-specific info
        if cat == "opportunities":
            close = item.get("close_date", "")
            opp_num = item.get("opportunity_number", "")
            if opp_num:
                line += f" | #{opp_num}"
            if close:
                line += f" | Closes: {close}"
        elif cat == "programs":
            status = item.get("status", "")
            pm = item.get("program_manager", "")
            if status:
                line += f" | Status: {status}"
            if pm:
                line += f" | PM: {pm}"
        elif cat == "news":
            pub = item.get("publish_date", "")
            if pub:
                line += f" | Published: {pub}"
        elif cat == "events":
            edate = item.get("event_date", "")
            loc = item.get("location", "")
            if edate:
                line += f" | Date: {edate}"
            if loc:
                line += f" | Location: {loc}"

        if url:
            line += f" | URL: {url}"

        # Add summary/body snippet
        summary = item.get("summary") or item.get("body", "")
        if summary:
            snippet = summary[:200]
            if len(summary) > 200:
                snippet += "..."
            line += f"\n  {snippet}"

        lines.append(line)

    return {"summary": "\n".join(lines)}


@router.delete("/items")
async def clear_items(category: Optional[str] = Query(None)):
    """Delete all stored items (optionally by category). For maintenance."""
    db = get_mongodb()
    col = db[COLLECTION]
    query = {"category": category} if category else {}
    result = await col.delete_many(query)
    return {"deleted": result.deleted_count}
