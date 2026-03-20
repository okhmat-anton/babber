"""
Geopolitics Monitor addon — backend routes.

Tracks news from configurable sources, monitors Pentagon open-source releases,
and stores articles for agent access.
"""

import html as html_mod
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from app.database import get_mongodb
from app.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/addons/geopolitics",
    tags=["addon-geopolitics"],
    dependencies=[Depends(get_current_user)],
)

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

NEWS_COLLECTION = "geopolitics_news"
PENTAGON_COLLECTION = "geopolitics_pentagon"
SOURCES_COLLECTION = "geopolitics_sources"
BOOKMARKS_COLLECTION = "geopolitics_bookmarks"
SUMMARIES_COLLECTION = "geopolitics_summaries"
META_COLLECTION = "geopolitics_meta"

# ---------------------------------------------------------------------------
# Default news sources
# ---------------------------------------------------------------------------

DEFAULT_NEWS_SOURCES = [
    {"name": "Reuters", "url": "https://www.reuters.com", "category": "wire", "rss": "https://www.rss.reuters.com/news/world"},
    {"name": "AP News", "url": "https://apnews.com", "category": "wire", "rss": "https://apnews.com/feed"},
    {"name": "BBC World", "url": "https://www.bbc.com/news/world", "category": "wire", "rss": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com", "category": "wire", "rss": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "Foreign Affairs", "url": "https://www.foreignaffairs.com", "category": "analysis", "rss": ""},
    {"name": "The Diplomat", "url": "https://thediplomat.com", "category": "analysis", "rss": "https://thediplomat.com/feed/"},
    {"name": "Defense One", "url": "https://www.defenseone.com", "category": "defense", "rss": "https://www.defenseone.com/rss/"},
    {"name": "War on the Rocks", "url": "https://warontherocks.com", "category": "defense", "rss": "https://warontherocks.com/feed/"},
    {"name": "CSIS", "url": "https://www.csis.org", "category": "think_tank", "rss": "https://www.csis.org/rss"},
    {"name": "Brookings", "url": "https://www.brookings.edu", "category": "think_tank", "rss": "https://www.brookings.edu/feed/"},
    {"name": "RAND", "url": "https://www.rand.org", "category": "think_tank", "rss": "https://www.rand.org/pubs.xml"},
    {"name": "Ukrainska Pravda", "url": "https://www.pravda.com.ua", "category": "wire", "rss": "https://www.pravda.com.ua/rss/view_news/"},
    {"name": "South China Morning Post", "url": "https://www.scmp.com", "category": "wire", "rss": "https://www.scmp.com/rss/91/feed"},
    {"name": "Middle East Eye", "url": "https://www.middleeasteye.net", "category": "wire", "rss": "https://www.middleeasteye.net/rss"},
    {"name": "Pentagon - DoD News", "url": "https://www.defense.gov/News/", "category": "defense", "rss": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=10"},
    {"name": "Pentagon - Releases", "url": "https://www.defense.gov/News/Releases/", "category": "defense", "rss": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=2&Site=945&max=10"},
    {"name": "Pentagon - Contracts", "url": "https://www.defense.gov/News/Contracts/", "category": "defense", "rss": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=3&Site=945&max=10"},
]

# Pentagon open-data sources
PENTAGON_SOURCES = [
    {"name": "DoD News", "url": "https://www.defense.gov/News/", "type": "news"},
    {"name": "DoD Releases", "url": "https://www.defense.gov/News/Releases/", "type": "releases"},
    {"name": "DoD Transcripts", "url": "https://www.defense.gov/News/Transcripts/", "type": "transcripts"},
    {"name": "DoD Contracts", "url": "https://www.defense.gov/News/Contracts/", "type": "contracts"},
    {"name": "DoD Advisories", "url": "https://www.defense.gov/News/Advisories/", "type": "advisories"},
    {"name": "CENTCOM", "url": "https://www.centcom.mil/MEDIA/PRESS-RELEASES/", "type": "centcom"},
    {"name": "EUCOM", "url": "https://www.eucom.mil/media-library/pressrelease", "type": "eucom"},
    {"name": "INDOPACOM", "url": "https://www.pacom.mil/Media/News/", "type": "indopacom"},
    {"name": "CRS Reports", "url": "https://crsreports.congress.gov/", "type": "crs_reports"},
    {"name": "SIPRI", "url": "https://www.sipri.org/media/press-releases", "type": "sipri"},
]

# Default keyword categories for filtering
KEYWORD_CATEGORIES = {
    "conflict": ["war", "conflict", "military", "troops", "bombing", "airstrike", "ceasefire", "invasion", "insurgency"],
    "diplomacy": ["diplomacy", "treaty", "agreement", "summit", "negotiations", "bilateral", "multilateral", "ambassador"],
    "sanctions": ["sanctions", "embargo", "tariff", "trade war", "export controls", "economic warfare"],
    "alliances": ["nato", "aukus", "quad", "brics", "g7", "g20", "eu", "asean", "sco", "african union"],
    "defense": ["defense", "pentagon", "missile", "nuclear", "submarine", "aircraft carrier", "drone", "cyber"],
    "intelligence": ["intelligence", "espionage", "cia", "mi6", "mossad", "fsb", "surveillance"],
    "regions": ["ukraine", "taiwan", "south china sea", "middle east", "arctic", "africa", "indo-pacific"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_setting(db, key: str, default: str = "") -> str:
    doc = await db["system_settings"].find_one({"key": key})
    if doc:
        return str(doc.get("value", default))
    return default


# ---------------------------------------------------------------------------
# 1. NEWS ARTICLES
# ---------------------------------------------------------------------------

@router.get("/news")
async def list_news(
    source: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    bookmarked: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List news articles with optional filters."""
    db = get_mongodb()
    query = {}
    if source:
        query["source_name"] = {"$regex": source, "$options": "i"}
    if category:
        query["category"] = category
    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"summary": {"$regex": keyword, "$options": "i"}},
            {"tags": {"$regex": keyword, "$options": "i"}},
        ]
    if bookmarked:
        # Get bookmarked article IDs
        bookmark_ids = []
        async for bm in db[BOOKMARKS_COLLECTION].find({}, {"article_id": 1}):
            bookmark_ids.append(bm["article_id"])
        query["_id"] = {"$in": [__import__("bson").ObjectId(bid) for bid in bookmark_ids if bid]}

    items = []
    async for doc in db[NEWS_COLLECTION].find(query).sort("published_at", -1).skip(offset).limit(limit):
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    total = await db[NEWS_COLLECTION].count_documents(query)
    return {"items": items, "total": total}


@router.post("/news")
async def create_news_article(body: dict):
    """Manually add a news article."""
    db = get_mongodb()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title required")

    doc = {
        "title": title,
        "url": body.get("url", ""),
        "source_name": body.get("source_name", "Manual"),
        "category": body.get("category", "general"),
        "summary": body.get("summary", ""),
        "content": body.get("content", ""),
        "tags": body.get("tags", []),
        "region": body.get("region", ""),
        "importance": body.get("importance", "medium"),
        "published_at": body.get("published_at", datetime.now(timezone.utc).isoformat()),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db[NEWS_COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.delete("/news/{article_id}")
async def delete_news_article(article_id: str):
    from bson import ObjectId
    db = get_mongodb()
    await db[NEWS_COLLECTION].delete_one({"_id": ObjectId(article_id)})
    await db[BOOKMARKS_COLLECTION].delete_many({"article_id": article_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# 2. PENTAGON SECTION
# ---------------------------------------------------------------------------

@router.get("/pentagon")
async def list_pentagon(
    source_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List Pentagon open-source items."""
    db = get_mongodb()
    query = {}
    if source_type:
        query["source_type"] = source_type
    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"summary": {"$regex": keyword, "$options": "i"}},
        ]

    items = []
    async for doc in db[PENTAGON_COLLECTION].find(query).sort("published_at", -1).skip(offset).limit(limit):
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    total = await db[PENTAGON_COLLECTION].count_documents(query)
    return {"items": items, "total": total}


@router.post("/pentagon")
async def create_pentagon_item(body: dict):
    """Manually add a Pentagon source item."""
    db = get_mongodb()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title required")

    doc = {
        "title": title,
        "url": body.get("url", ""),
        "source_name": body.get("source_name", "DoD"),
        "source_type": body.get("source_type", "news"),
        "summary": body.get("summary", ""),
        "content": body.get("content", ""),
        "tags": body.get("tags", []),
        "published_at": body.get("published_at", datetime.now(timezone.utc).isoformat()),
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db[PENTAGON_COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.delete("/pentagon/{item_id}")
async def delete_pentagon_item(item_id: str):
    from bson import ObjectId
    db = get_mongodb()
    await db[PENTAGON_COLLECTION].delete_one({"_id": ObjectId(item_id)})
    return {"ok": True}


@router.get("/pentagon/sources")
async def get_pentagon_sources():
    """List all known Pentagon open-source endpoints."""
    return {"items": PENTAGON_SOURCES}


# ---------------------------------------------------------------------------
# 3. SOURCES MANAGEMENT
# ---------------------------------------------------------------------------

@router.get("/sources")
async def list_sources():
    """List configured news sources."""
    db = get_mongodb()
    items = []
    count = await db[SOURCES_COLLECTION].count_documents({})
    if count == 0:
        # Seed defaults
        for s in DEFAULT_NEWS_SOURCES:
            s["enabled"] = True
            s["created_at"] = datetime.now(timezone.utc).isoformat()
        await db[SOURCES_COLLECTION].insert_many([dict(s) for s in DEFAULT_NEWS_SOURCES])

    async for doc in db[SOURCES_COLLECTION].find().sort("name", 1):
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"items": items}


@router.post("/sources")
async def add_source(body: dict):
    """Add a new news source."""
    db = get_mongodb()
    name = body.get("name", "").strip()
    url = body.get("url", "").strip()
    if not name or not url:
        raise HTTPException(status_code=400, detail="Name and URL required")

    doc = {
        "name": name,
        "url": url,
        "rss": body.get("rss", ""),
        "category": body.get("category", "general"),
        "enabled": body.get("enabled", True),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db[SOURCES_COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, body: dict):
    from bson import ObjectId
    db = get_mongodb()
    body.pop("_id", None)
    await db[SOURCES_COLLECTION].update_one({"_id": ObjectId(source_id)}, {"$set": body})
    return {"ok": True}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    from bson import ObjectId
    db = get_mongodb()
    await db[SOURCES_COLLECTION].delete_one({"_id": ObjectId(source_id)})
    return {"ok": True}


@router.post("/sources/seed")
async def seed_sources():
    """Re-seed default news sources (skips existing by name)."""
    db = get_mongodb()
    added = 0
    for s in DEFAULT_NEWS_SOURCES:
        existing = await db[SOURCES_COLLECTION].find_one({"name": s["name"]})
        if not existing:
            s["enabled"] = True
            s["created_at"] = datetime.now(timezone.utc).isoformat()
            await db[SOURCES_COLLECTION].insert_one(dict(s))
            added += 1
    return {"added": added, "total_defaults": len(DEFAULT_NEWS_SOURCES)}


# ---------------------------------------------------------------------------
# 4. BOOKMARKS
# ---------------------------------------------------------------------------

@router.post("/bookmarks/{article_id}")
async def toggle_bookmark(article_id: str):
    """Toggle bookmark on an article."""
    db = get_mongodb()
    existing = await db[BOOKMARKS_COLLECTION].find_one({"article_id": article_id})
    if existing:
        await db[BOOKMARKS_COLLECTION].delete_one({"article_id": article_id})
        return {"bookmarked": False}
    else:
        await db[BOOKMARKS_COLLECTION].insert_one({
            "article_id": article_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"bookmarked": True}


@router.get("/bookmarks")
async def list_bookmarks():
    db = get_mongodb()
    items = []
    async for bm in db[BOOKMARKS_COLLECTION].find().sort("created_at", -1):
        bm["_id"] = str(bm["_id"])
        items.append(bm)
    return {"items": items}


# ---------------------------------------------------------------------------
# 5. SCRAPE
# ---------------------------------------------------------------------------

@router.post("/scrape")
async def scrape_news(body: dict = None):
    """
    Trigger a scrape of configured sources.
    Uses RSS feeds where available, falls back to web scraping.
    """
    db = get_mongodb()
    body = body or {}
    source_filter = body.get("source_name")

    sources_query = {"enabled": True}
    if source_filter:
        sources_query["name"] = {"$regex": source_filter, "$options": "i"}

    sources = []
    async for s in db[SOURCES_COLLECTION].find(sources_query):
        sources.append(s)

    if not sources:
        return {"scraped": 0, "message": "No enabled sources found. Add sources in the Sources tab."}

    # Read max articles setting
    max_articles_str = await _get_setting(db, "geopolitics_max_articles", "25")
    max_articles = int(max_articles_str) if max_articles_str.isdigit() else 25

    # Read keyword filter
    keywords_str = await _get_setting(db, "geopolitics_keywords", "")
    keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()] if keywords_str else []

    total_added = 0
    results = []

    for source in sources:
        rss_url = source.get("rss", "")
        source_name = source["name"]

        # Try RSS feed
        if rss_url:
            try:
                import httpx
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}
                async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                    resp = await client.get(rss_url, follow_redirects=True)
                if resp.status_code == 200:
                    # Simple RSS XML parsing
                    text = resp.text
                    items_found = _parse_rss_items(text, source_name, source.get("category", "general"), max_articles)

                    added = 0
                    for item in items_found:
                        # Keyword filter
                        if keywords:
                            text_check = (item.get("title", "") + " " + item.get("summary", "")).lower()
                            if not any(kw in text_check for kw in keywords):
                                continue

                        # Skip duplicates by URL
                        if item.get("url"):
                            exists = await db[NEWS_COLLECTION].find_one({"url": item["url"]})
                            if exists:
                                continue

                        item["scraped_at"] = datetime.now(timezone.utc).isoformat()
                        item["created_at"] = datetime.now(timezone.utc).isoformat()
                        await db[NEWS_COLLECTION].insert_one(item)
                        added += 1

                    total_added += added
                    results.append({"source": source_name, "added": added, "method": "rss"})
                else:
                    results.append({"source": source_name, "added": 0, "error": f"HTTP {resp.status_code}"})
            except Exception as e:
                logger.warning(f"RSS scrape failed for {source_name}: {e}")
                results.append({"source": source_name, "added": 0, "error": str(e)})
        else:
            results.append({"source": source_name, "added": 0, "method": "no_rss", "note": "No RSS feed configured"})

    # Update meta
    await db[META_COLLECTION].update_one(
        {"key": "last_scrape"},
        {"$set": {"key": "last_scrape", "value": datetime.now(timezone.utc).isoformat(), "total_added": total_added}},
        upsert=True,
    )

    return {"scraped": total_added, "sources_checked": len(sources), "details": results}


def _extract_article_summary(html: str) -> str:
    """Extract summary from an article page using meta tags and first paragraphs."""
    # Try og:description
    m = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)', html, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description', html, re.IGNORECASE)
    if m and len(m.group(1).strip()) > 30:
        return html_mod.unescape(re.sub(r'<[^>]+>', '', m.group(1).strip()))[:800]

    # Try meta description
    m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+ )', html, re.IGNORECASE)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+ )["\'][^>]+name=["\']description', html, re.IGNORECASE)
    if m and len(m.group(1).strip()) > 30:
        return html_mod.unescape(re.sub(r'<[^>]+>', '', m.group(1).strip()))[:800]

    # Fallback: collect first meaningful <p> tags
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL | re.IGNORECASE)
    text_parts = []
    for p in paragraphs:
        clean = re.sub(r'<[^>]+>', '', p).strip()
        if len(clean) > 40:
            text_parts.append(clean)
            if len(' '.join(text_parts)) > 500:
                break
    if text_parts:
        return html_mod.unescape(' '.join(text_parts))[:800]

    return ""


def _extract_published_date(html: str) -> str:
    """Try to extract a publish date from article page meta tags."""
    for attr in ['article:published_time', 'datePublished', 'date', 'DC.date.issued', 'pubdate']:
        m = re.search(
            rf'<meta[^>]+(?:property|name|itemprop)=["\'](?:{re.escape(attr)})["\'][^>]+content=["\']([^"\']+)',
            html, re.IGNORECASE
        )
        if not m:
            m = re.search(
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\'](?:{re.escape(attr)})',
                html, re.IGNORECASE
            )
        if m:
            return m.group(1).strip()
    # Try <time> tag
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


@router.post("/scrape-pentagon")
async def scrape_pentagon():
    """Trigger a scrape of Pentagon open sources.
    Follows each article link to extract summary, date, and tags.
    """
    db = get_mongodb()

    # Check if Pentagon monitoring is enabled
    enabled = await _get_setting(db, "geopolitics_pentagon_enabled", "true")
    if enabled.lower() != "true":
        return {"scraped": 0, "message": "Pentagon monitoring is disabled in settings."}

    total_added = 0
    results = []
    BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

    for source in PENTAGON_SOURCES:
        try:
            import httpx
            headers = {"User-Agent": BROWSER_UA}
            async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
                resp = await client.get(source["url"])
            if resp.status_code == 200:
                # Extract article links from listing page
                links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', resp.text, re.IGNORECASE | re.DOTALL)

                added = 0
                seen_titles = set()

                for href, link_text in links[:50]:
                    clean_title = re.sub(r'<[^>]+>', '', link_text).strip()
                    if len(clean_title) < 15 or clean_title in seen_titles:
                        continue
                    seen_titles.add(clean_title)

                    # Resolve relative URLs
                    if href.startswith("/"):
                        base = source["url"].split("/")[0] + "//" + source["url"].split("/")[2]
                        href = base + href

                    # Skip non-article links
                    if not href.startswith("http"):
                        continue

                    # Skip duplicates
                    exists = await db[PENTAGON_COLLECTION].find_one({"url": href})
                    if exists:
                        continue

                    # Follow the article link to get summary and date
                    summary = ""
                    pub_date = ""
                    tags = []
                    try:
                        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as detail_client:
                            detail_resp = await detail_client.get(href)
                        if detail_resp.status_code == 200:
                            detail_html = detail_resp.text
                            summary = _extract_article_summary(detail_html)
                            pub_date = _extract_published_date(detail_html)

                            # Extract keywords/tags from meta
                            kw_m = re.search(
                                r'<meta[^>]+name=["\']keywords["\'][^>]+content=["\']([^"\']+)',
                                detail_html, re.IGNORECASE
                            )
                            if kw_m:
                                tags = [t.strip() for t in kw_m.group(1).split(",") if t.strip()][:10]
                    except Exception as detail_err:
                        logger.debug(f"Could not fetch article detail {href}: {detail_err}")

                    doc = {
                        "title": clean_title,
                        "url": href,
                        "source_name": source["name"],
                        "source_type": source["type"],
                        "summary": summary,
                        "tags": tags,
                        "published_at": pub_date or datetime.now(timezone.utc).isoformat(),
                        "scraped_at": datetime.now(timezone.utc).isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    await db[PENTAGON_COLLECTION].insert_one(doc)
                    added += 1
                    if added >= 25:
                        break

                total_added += added
                results.append({"source": source["name"], "added": added})
            else:
                results.append({"source": source["name"], "error": f"HTTP {resp.status_code}"})
        except Exception as e:
            logger.warning(f"Pentagon scrape failed for {source['name']}: {e}")
            results.append({"source": source["name"], "error": str(e)})

    await db[META_COLLECTION].update_one(
        {"key": "last_pentagon_scrape"},
        {"$set": {"key": "last_pentagon_scrape", "value": datetime.now(timezone.utc).isoformat(), "total_added": total_added}},
        upsert=True,
    )

    return {"scraped": total_added, "sources_checked": len(PENTAGON_SOURCES), "details": results}


# ---------------------------------------------------------------------------
# Helpers - RSS parsing
# ---------------------------------------------------------------------------

def _parse_rss_items(xml_text: str, source_name: str, category: str, max_items: int = 25) -> list:
    """Extract items from RSS XML (simple regex-based parser)."""
    items = []
    # Find all <item> or <entry> blocks
    item_blocks = re.findall(r'<item[^>]*>(.*?)</item>', xml_text, re.DOTALL | re.IGNORECASE)
    if not item_blocks:
        item_blocks = re.findall(r'<entry[^>]*>(.*?)</entry>', xml_text, re.DOTALL | re.IGNORECASE)

    for block in item_blocks[:max_items]:
        title_m = re.search(r'<title[^>]*>(.*?)</title>', block, re.DOTALL | re.IGNORECASE)
        link_m = re.search(r'<link[^>]*href=["\']([^"\']+)', block, re.IGNORECASE) or \
                 re.search(r'<link[^>]*>(.*?)</link>', block, re.DOTALL | re.IGNORECASE)
        desc_m = re.search(r'<description[^>]*>(.*?)</description>', block, re.DOTALL | re.IGNORECASE) or \
                 re.search(r'<summary[^>]*>(.*?)</summary>', block, re.DOTALL | re.IGNORECASE)
        date_m = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', block, re.DOTALL | re.IGNORECASE) or \
                 re.search(r'<published[^>]*>(.*?)</published>', block, re.DOTALL | re.IGNORECASE) or \
                 re.search(r'<updated[^>]*>(.*?)</updated>', block, re.DOTALL | re.IGNORECASE)

        title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title_m.group(1).strip()) if title_m else ""
        title = re.sub(r'<[^>]+>', '', title).strip()
        if not title:
            continue

        url = ""
        if link_m:
            url = link_m.group(1).strip()
            url = re.sub(r'<[^>]+>', '', url).strip()

        summary = ""
        if desc_m:
            summary = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', desc_m.group(1).strip())
            summary = re.sub(r'<[^>]+>', '', summary).strip()[:500]

        pub_date = ""
        if date_m:
            pub_date = date_m.group(1).strip()

        items.append({
            "title": title,
            "url": url,
            "source_name": source_name,
            "category": category,
            "summary": summary,
            "published_at": pub_date or datetime.now(timezone.utc).isoformat(),
            "tags": [],
            "region": "",
            "importance": "medium",
        })

    return items


# ---------------------------------------------------------------------------
# 6. KEYWORD CATEGORIES
# ---------------------------------------------------------------------------

@router.get("/keyword-categories")
async def get_keyword_categories():
    """Get built-in keyword categories for geopolitical filtering."""
    return {"categories": KEYWORD_CATEGORIES}


# ---------------------------------------------------------------------------
# 7. STATS & MANAGEMENT
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats():
    db = get_mongodb()
    news = await db[NEWS_COLLECTION].count_documents({})
    pentagon = await db[PENTAGON_COLLECTION].count_documents({})
    sources = await db[SOURCES_COLLECTION].count_documents({})
    bookmarks = await db[BOOKMARKS_COLLECTION].count_documents({})

    last_scrape = await db[META_COLLECTION].find_one({"key": "last_scrape"})
    last_pentagon = await db[META_COLLECTION].find_one({"key": "last_pentagon_scrape"})

    return {
        "news_articles": news,
        "pentagon_items": pentagon,
        "sources": sources,
        "bookmarks": bookmarks,
        "last_scrape": last_scrape.get("value") if last_scrape else None,
        "last_pentagon_scrape": last_pentagon.get("value") if last_pentagon else None,
    }


@router.delete("/clear")
async def clear_all():
    db = get_mongodb()
    n1 = await db[NEWS_COLLECTION].delete_many({})
    n2 = await db[PENTAGON_COLLECTION].delete_many({})
    n3 = await db[BOOKMARKS_COLLECTION].delete_many({})
    n4 = await db[META_COLLECTION].delete_many({})
    return {
        "deleted_news": n1.deleted_count,
        "deleted_pentagon": n2.deleted_count,
        "deleted_bookmarks": n3.deleted_count,
        "deleted_meta": n4.deleted_count,
    }


@router.delete("/clear-news")
async def clear_news():
    db = get_mongodb()
    result = await db[NEWS_COLLECTION].delete_many({})
    return {"deleted": result.deleted_count}


@router.delete("/clear-pentagon")
async def clear_pentagon():
    db = get_mongodb()
    result = await db[PENTAGON_COLLECTION].delete_many({})
    return {"deleted": result.deleted_count}


# ---------------------------------------------------------------------------
# 8. DAILY / MONTHLY SUMMARY (LLM)
# ---------------------------------------------------------------------------

def _build_news_context(news_items: list, pentagon_items: list) -> str:
    """Build a text context block from news and Pentagon articles."""
    context_parts = []
    if news_items:
        context_parts.append("## News Articles")
        for i, art in enumerate(news_items, 1):
            title = html_mod.unescape(art.get("title", ""))
            summary = html_mod.unescape(art.get("summary", ""))
            source = art.get("source_name", "Unknown")
            category = art.get("category", "")
            entry = f"{i}. [{source} / {category}] {title}"
            if summary:
                entry += f"\n   Summary: {summary[:400]}"
            context_parts.append(entry)
    if pentagon_items:
        context_parts.append("\n## Pentagon / Defense Data")
        for i, item in enumerate(pentagon_items, 1):
            title = html_mod.unescape(item.get("title", ""))
            summary = html_mod.unescape(item.get("summary", ""))
            source = item.get("source_name", "Unknown")
            stype = item.get("source_type", "")
            entry = f"{i}. [{source} / {stype}] {title}"
            if summary:
                entry += f"\n   Summary: {summary[:400]}"
            context_parts.append(entry)
    return "\n".join(context_parts)


async def _generate_summary(db, model_id: str, language: str, news_context: str, scope: str = "daily") -> str:
    """Call LLM with the news context and return the summary text."""
    from app.api.chat import _resolve_model, _chat_with_model
    from app.llm.base import GenerationParams

    language_instruction = ""
    if language and language != "English":
        language_instruction = f"\n\nIMPORTANT: Write the ENTIRE briefing in {language}. All headings, analysis, and text must be in {language}.\n"

    scope_label = "daily" if scope == "daily" else "monthly (last 30 days)"

    prompt = f"""You are a senior geopolitical intelligence analyst. Produce a concise {scope_label} intelligence briefing based on the following news and Pentagon data.{language_instruction}

Structure your briefing as:
1. **Executive Summary** — 2-3 sentence overview of the most critical developments
2. **Key Developments** — bullet points of the most important stories, grouped by region or topic
3. **Defense & Military** — any Pentagon/military-related developments
4. **Risk Assessment** — emerging threats or escalation risks
5. **Watch List** — things to monitor in the coming days
6. **Money-Making Opportunities** — exactly 3 concrete, actionable ideas on how to profit or earn money based on the current geopolitical situation (e.g. investment opportunities, market moves, business ideas, sectors to watch)

Be analytical, not just descriptive. Identify patterns, connections between events, and potential implications.

---

{news_context}"""

    try:
        provider, base_url, model_name, api_key = await _resolve_model(model_id, db)
        params = GenerationParams(temperature=0.4, max_tokens=4096, num_ctx=32768)
        response = await _chat_with_model(
            provider, base_url, model_name, api_key,
            [
                {"role": "system", "content": "You are a geopolitical intelligence analyst producing briefings. Be concise, analytical, and focus on actionable intelligence. Always end with 3 concrete money-making opportunities based on the geopolitical landscape."},
                {"role": "user", "content": prompt},
            ],
            params,
        )
        return response.content
    except Exception as e:
        logger.error(f"Summary LLM call failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM summarization failed: {str(e)}")

@router.post("/summarize-day")
async def summarize_day(body: dict = None):
    """Use LLM to produce an intelligence briefing from today's news and Pentagon data."""
    from app.api.chat import _resolve_model, _chat_with_model
    from app.llm.base import GenerationParams

    db = get_mongodb()
    body = body or {}
    model_id = body.get("model_id", "role:default")
    language = body.get("language", "English")

    # Strictly today's articles only
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    news_query = {"created_at": {"$gte": today_start}}
    news_items = []
    async for doc in db[NEWS_COLLECTION].find(news_query).sort("published_at", -1).limit(100):
        news_items.append(doc)

    pentagon_items = []
    async for doc in db[PENTAGON_COLLECTION].find(news_query).sort("published_at", -1).limit(100):
        pentagon_items.append(doc)

    if not news_items and not pentagon_items:
        raise HTTPException(status_code=400, detail="No news or Pentagon data from today. Run scraping first.")

    news_context = _build_news_context(news_items, pentagon_items)
    summary_text = await _generate_summary(db, model_id, language, news_context, scope="daily")

    summary_doc = {
        "summary": summary_text,
        "model": (await _resolve_model(model_id, db))[2],
        "language": language,
        "scope": "daily",
        "news_count": len(news_items),
        "pentagon_count": len(pentagon_items),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db[SUMMARIES_COLLECTION].insert_one(summary_doc)
    summary_doc["_id"] = str(result.inserted_id)
    return summary_doc


@router.post("/summarize-month")
async def summarize_month(body: dict = None):
    """Use LLM to produce a monthly intelligence briefing from all available data."""
    from app.api.chat import _resolve_model, _chat_with_model
    from app.llm.base import GenerationParams

    db = get_mongodb()
    body = body or {}
    model_id = body.get("model_id", "role:default")
    language = body.get("language", "English")

    # All articles from the last 30 days
    from datetime import timedelta
    month_start = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    news_query = {"created_at": {"$gte": month_start}}
    news_items = []
    async for doc in db[NEWS_COLLECTION].find(news_query).sort("published_at", -1).limit(200):
        news_items.append(doc)

    pentagon_items = []
    async for doc in db[PENTAGON_COLLECTION].find(news_query).sort("published_at", -1).limit(200):
        pentagon_items.append(doc)

    # If nothing in last 30 days, grab everything available
    if not news_items:
        async for doc in db[NEWS_COLLECTION].find().sort("created_at", -1).limit(200):
            news_items.append(doc)
    if not pentagon_items:
        async for doc in db[PENTAGON_COLLECTION].find().sort("created_at", -1).limit(200):
            pentagon_items.append(doc)

    if not news_items and not pentagon_items:
        raise HTTPException(status_code=400, detail="No news or Pentagon data available. Run scraping first.")

    news_context = _build_news_context(news_items, pentagon_items)
    summary_text = await _generate_summary(db, model_id, language, news_context, scope="monthly")

    summary_doc = {
        "summary": summary_text,
        "model": (await _resolve_model(model_id, db))[2],
        "language": language,
        "scope": "monthly",
        "news_count": len(news_items),
        "pentagon_count": len(pentagon_items),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db[SUMMARIES_COLLECTION].insert_one(summary_doc)
    summary_doc["_id"] = str(result.inserted_id)
    return summary_doc


# ---------------------------------------------------------------------------
# 9. SUMMARIES HISTORY
# ---------------------------------------------------------------------------

@router.get("/summaries")
async def list_summaries(limit: int = Query(50, ge=1, le=200)):
    """Return saved daily intelligence briefings, newest first."""
    db = get_mongodb()
    items = []
    async for doc in db[SUMMARIES_COLLECTION].find().sort("created_at", -1).limit(limit):
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"items": items}


@router.delete("/summaries/{summary_id}")
async def delete_summary(summary_id: str):
    """Delete a single summary from history."""
    from bson import ObjectId
    db = get_mongodb()
    result = await db[SUMMARIES_COLLECTION].delete_one({"_id": ObjectId(summary_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Summary not found")
    return {"deleted": True}


@router.delete("/clear-summaries")
async def clear_summaries():
    """Delete all saved summaries."""
    db = get_mongodb()
    result = await db[SUMMARIES_COLLECTION].delete_many({})
    return {"deleted": result.deleted_count}
