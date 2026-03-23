"""
Real Estate addon — backend routes.

Tabs: Affordable Land, Saved / Favorites, Sources, Settings.
Scrapes land listing websites, stores in MongoDB, filters by user criteria.
"""

import asyncio
import hashlib
import logging
import re
import math
import traceback
from datetime import datetime, timezone
from typing import Optional, List

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException, Query, Depends, Body, BackgroundTasks
from pydantic import BaseModel

from app.database import get_mongodb
from app.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/addons/real_estate",
    tags=["addon-real-estate"],
    dependencies=[Depends(get_current_user)],
)

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

COL_LISTINGS = "re_listings"
COL_FAVORITES = "re_favorites"
COL_SOURCES = "re_sources"
COL_META = "re_meta"

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

HTTP_TIMEOUT = 20.0
HTTP_CONNECT_TIMEOUT = 10.0
MAX_RETRIES = 2

# Background scrape state (in-memory, one scrape at a time)
_scrape_lock = asyncio.Lock()
_scrape_progress = {
    "running": False,
    "source": None,
    "states_done": 0,
    "states_total": 0,
    "listings_found": 0,
    "errors": 0,
    "started_at": None,
    "finished_at": None,
    "error_msg": None,
}


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from text like '$17,005.39' or '17005'."""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", text.strip())
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_acreage(text: str) -> Optional[float]:
    """Extract acre value from text like '5 Acres' or '0.32'."""
    if not text:
        return None
    m = re.search(r"([\d.]+)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two lat/lon points in miles."""
    R = 3959  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Default sources
# ---------------------------------------------------------------------------

DEFAULT_SOURCES = [
    {
        "source_id": "landcentral",
        "name": "LandCentral",
        "base_url": "https://www.landcentral.com",
        "enabled": True,
        "scraper_type": "landcentral",
        "description": "Affordable land with owner financing since 1997",
    },
    {
        "source_id": "classiccountryland",
        "name": "Classic Country Land",
        "base_url": "https://www.classiccountryland.com",
        "enabled": True,
        "scraper_type": "classiccountryland",
        "description": "Rural land, owner financing, acreage across US",
    },
]

# LandCentral state slugs
LC_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york",
    "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode-island", "south-carolina", "south-dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west-virginia", "wisconsin", "wyoming",
]

# Classic Country Land state slugs
CCL_STATES = [
    "alabama", "arizona", "arkansas", "california", "colorado", "florida",
    "kansas", "kentucky", "maine", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nevada", "new-mexico", "oklahoma", "tennessee",
    "texas", "utah", "virginia", "west-virginia", "wyoming",
]


def _slug_to_state(slug: str) -> str:
    """Convert 'new-york' to 'New York'."""
    return slug.replace("-", " ").title()


# ═══════════════════════════════════════════════════════════════════════════
# Settings helper
# ═══════════════════════════════════════════════════════════════════════════

async def _get_settings(db) -> dict:
    """Load all re_* settings from system_settings."""
    settings = {}
    cursor = db["system_settings"].find({"key": {"$regex": "^re_"}})
    async for doc in cursor:
        settings[doc["key"]] = doc.get("value", doc.get("default", ""))
    return settings


async def _get_filter_settings(db) -> dict:
    """Load filter-relevant settings as typed values."""
    raw = await _get_settings(db)
    return {
        "max_price": float(raw.get("re_max_price") or 0) or 999999999,
        "max_down_payment": float(raw.get("re_max_down_payment") or 0) or 999999999,
        "max_monthly_payment": float(raw.get("re_max_monthly_payment") or 0) or 999999999,
        "states": [
            s.strip().lower()
            for s in (raw.get("re_states") or "").split(",")
            if s.strip()
        ],
        "zip_codes": [
            z.strip()
            for z in (raw.get("re_zip_codes") or "").split(",")
            if z.strip()
        ],
        "zip_radius_miles": float(raw.get("re_zip_radius_miles") or 50),
        "min_acreage": float(raw.get("re_min_acreage") or 0),
        "max_acreage": float(raw.get("re_max_acreage") or 0),
        "land_types": [
            t.strip().lower()
            for t in (raw.get("re_land_types") or "").split(",")
            if t.strip()
        ],
        "require_building_permit": raw.get("re_require_building_permit", "any"),
        "require_camping": raw.get("re_require_camping", "any"),
        "require_septic": raw.get("re_require_septic", "any"),
    }


def _matches_filters(listing: dict, filters: dict) -> bool:
    """Check if a listing matches user filter criteria."""
    price = listing.get("price")
    if price and price > filters["max_price"]:
        return False

    down = listing.get("down_payment")
    if down and down > filters["max_down_payment"]:
        return False

    monthly = listing.get("monthly_payment")
    if monthly and monthly > filters["max_monthly_payment"]:
        return False

    if filters["states"]:
        state = (listing.get("state") or "").lower()
        if state and state not in filters["states"]:
            return False

    acreage = listing.get("acreage")
    if acreage:
        if filters["min_acreage"] and acreage < filters["min_acreage"]:
            return False
        if filters["max_acreage"] and acreage > filters["max_acreage"]:
            return False

    return True


# ═══════════════════════════════════════════════════════════════════════════
# SCRAPERS
# ═══════════════════════════════════════════════════════════════════════════


async def _fetch_with_retry(client: httpx.AsyncClient, url: str, retries: int = MAX_RETRIES) -> Optional[httpx.Response]:
    """Fetch URL with retries and per-request timeout."""
    timeout = httpx.Timeout(HTTP_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT)
    for attempt in range(retries + 1):
        try:
            resp = await client.get(
                url, headers=HTTP_HEADERS, timeout=timeout, follow_redirects=True,
            )
            if resp.status_code == 200:
                return resp
            logger.warning(f"HTTP {resp.status_code} for {url} (attempt {attempt+1})")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            logger.warning(f"Fetch error {url} (attempt {attempt+1}): {type(e).__name__}")
            if attempt < retries:
                await asyncio.sleep(1.5 * (attempt + 1))
        except Exception as e:
            logger.error(f"Unexpected fetch error {url}: {e}")
            break
    return None


async def _smart_upsert(col, listing_hash: str, fresh_data: dict):
    """Insert new listing or update only volatile fields (price, availability).

    Preserves detail fields (description, down_payment, monthly_payment, etc.)
    that were scraped separately. Tracks price history.
    """
    existing = await col.find_one({"hash": listing_hash})
    now = datetime.now(timezone.utc).isoformat()

    if existing is None:
        # Brand new listing — insert all fields
        fresh_data["first_seen"] = now
        fresh_data["scraped_at"] = now
        fresh_data["price_history"] = []
        if fresh_data.get("price"):
            fresh_data["price_history"] = [
                {"price": fresh_data["price"], "date": now}
            ]
        await col.insert_one(fresh_data)
        return True

    # Existing listing — only update volatile fields, keep detail data
    update_set = {"scraped_at": now}
    update_push = {}

    # Always update these (may change between scrapes)
    volatile_fields = [
        "price", "original_price", "tracts_available",
        "image_url", "is_foreclosure",
    ]
    for field in volatile_fields:
        new_val = fresh_data.get(field)
        if new_val is not None:
            update_set[field] = new_val

    # Update name/state/county only if existing is empty
    for field in ["name", "state", "county", "acreage", "acreage_max", "property_id"]:
        if not existing.get(field) and fresh_data.get(field):
            update_set[field] = fresh_data[field]

    # Track price changes
    old_price = existing.get("price")
    new_price = fresh_data.get("price")
    if new_price and old_price and abs(new_price - old_price) > 0.01:
        update_push["price_history"] = {
            "price": new_price,
            "old_price": old_price,
            "date": now,
        }
        update_set["price_changed_at"] = now

    ops = {"$set": update_set}
    if update_push:
        ops["$push"] = update_push

    await col.update_one({"hash": listing_hash}, ops)
    return False  # not new


async def _scrape_landcentral(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandCentral.com — one page per state with listings."""
    col = db[COL_LISTINGS]
    count = 0

    states_to_scrape = LC_STATES
    if states_filter:
        states_to_scrape = [
            s for s in LC_STATES
            if _slug_to_state(s).lower() in states_filter
        ]

    _scrape_progress["states_total"] = len(states_to_scrape)
    _scrape_progress["states_done"] = 0

    for state_slug in states_to_scrape:
        url = f"https://www.landcentral.com/land-for-sale/{state_slug}"
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp:
                _scrape_progress["errors"] += 1
                _scrape_progress["states_done"] += 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            state_name = _slug_to_state(state_slug)

            # Parse listings: find h3 > a links that point to individual properties
            titles = soup.find_all("h3")
            for title_el in titles:
                link = title_el.find("a")
                if not link:
                    continue
                href = link.get("href", "")
                if f"/land-for-sale/{state_slug}/" not in href:
                    continue
                if href.startswith("/"):
                    href = f"https://www.landcentral.com{href}"

                name = link.get_text(strip=True)
                if not name:
                    continue

                parent = title_el.parent
                if not parent:
                    continue

                text_block = parent.get_text(" ", strip=True)

                # Extract property #
                prop_match = re.search(r"Property\s*#?\s*(\d+)", text_block)
                prop_id = prop_match.group(1) if prop_match else ""

                # Extract size
                size_match = re.search(r"([\d.]+)\s*Acres?", text_block, re.I)
                acreage = float(size_match.group(1)) if size_match else None

                # Extract county
                county = ""
                county_el = parent.find(string=re.compile(r"County", re.I))
                if county_el:
                    county_text = county_el.parent.get_text(strip=True) if county_el.parent else str(county_el)
                    cm = re.match(r"^(\w[\w\s]*?)$", county_text)
                    if cm:
                        county = county_text.replace("County", "").strip()

                # Extract price — looks for $X,XXX.XX
                price_matches = re.findall(r"\$[\d,]+\.?\d*", text_block)
                price = None
                original_price = None
                for pm in price_matches:
                    p = _parse_price(pm)
                    if p:
                        if price is None or p < price:
                            price = p
                        if original_price is None or p > original_price:
                            original_price = p

                if original_price == price:
                    original_price = None

                listing_hash = _hash(f"landcentral:{href}")

                # Try to get image
                image_url = None
                img = parent.find("img")
                if img:
                    img_src = img.get("src") or img.get("data-src") or ""
                    if img_src and not img_src.startswith("data:"):
                        if img_src.startswith("/"):
                            img_src = f"https://www.landcentral.com{img_src}"
                        image_url = img_src

                fresh = {
                    "hash": listing_hash,
                    "source": "landcentral",
                    "source_name": "LandCentral",
                    "name": name,
                    "url": href,
                    "property_id": prop_id,
                    "state": state_name,
                    "county": county,
                    "acreage": acreage,
                    "price": price,
                    "original_price": original_price,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "building_permitted": None,
                    "camping_allowed": None,
                    "septic_allowed": None,
                    "image_url": image_url,
                    "description": "",
                    "is_foreclosure": "foreclos" in text_block.lower(),
                    "tracts_available": None,
                }

                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] += 1
            # Small delay between states
            await asyncio.sleep(0.3)

        except Exception as e:
            logger.error(f"LandCentral scrape error ({state_slug}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] += 1
            continue

    return count


async def _scrape_classiccountryland(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape ClassicCountryLand.com — main properties page."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] += 1  # single page

    try:
        resp = await _fetch_with_retry(client, "https://www.classiccountryland.com/properties/")
        if not resp:
            _scrape_progress["errors"] += 1
            return 0

        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.find_all("a", href=re.compile(r"/properties/[\w-]+-land-for-sale/[\w-]+"))
        seen = set()

        for link in links:
            href = link.get("href", "")
            if href in seen or not href:
                continue
            seen.add(href)

            if href.startswith("/"):
                href = f"https://www.classiccountryland.com{href}"

            # Walk up to find enclosing card
            card = link
            for _ in range(5):
                if card.parent:
                    card = card.parent
                else:
                    break

            card_text = card.get_text(" ", strip=True)

            name_el = card.find(["h2", "h3", "h4", "strong"])
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                name = link.get_text(strip=True)
            if not name or name == "LEARN MORE":
                continue

            state_match = re.search(r"/properties/([\w-]+)-land-for-sale/", href)
            state_name = _slug_to_state(state_match.group(1)) if state_match else ""

            if states_filter and state_name.lower() not in states_filter:
                continue

            county_match = re.search(r"([\w\s]+?)\s*County", card_text)
            county = county_match.group(1).strip() if county_match else ""

            acre_match = re.search(r"([\d.]+)\s*(?:to\s*([\d.]+))?\s*Acres?", card_text, re.I)
            acreage_min = float(acre_match.group(1)) if acre_match else None
            acreage_max = float(acre_match.group(2)) if acre_match and acre_match.group(2) else acreage_min

            price_match = re.search(r"Starting\s+at\s+\$([\d,]+)", card_text)
            price = _parse_price(price_match.group(1)) if price_match else None
            if not price:
                pm = re.search(r"\$([\d,]+\.?\d*)", card_text)
                price = _parse_price(pm.group(1)) if pm else None

            tract_match = re.search(r"(\d+)\s*Tracts?\s*available", card_text, re.I)
            tracts = int(tract_match.group(1)) if tract_match else None

            img = card.find("img")
            img_url = None
            if img:
                img_src = img.get("src") or img.get("data-src") or ""
                if img_src and not img_src.startswith("data:"):
                    if img_src.startswith("/"):
                        img_src = f"https://www.classiccountryland.com{img_src}"
                    img_url = img_src

            listing_hash = _hash(f"ccl:{href}")
            fresh = {
                "hash": listing_hash,
                "source": "classiccountryland",
                "source_name": "Classic Country Land",
                "name": name,
                "url": href,
                "property_id": "",
                "state": state_name,
                "county": county,
                "acreage": acreage_min,
                "acreage_max": acreage_max,
                "price": price,
                "original_price": None,
                "down_payment": None,
                "monthly_payment": None,
                "financing_available": True,
                "land_type": None,
                "building_permitted": None,
                "camping_allowed": None,
                "septic_allowed": None,
                "tracts_available": tracts,
                "image_url": img_url,
                "description": "",
                "is_foreclosure": False,
            }

            await _smart_upsert(col, listing_hash, fresh)
            count += 1
            _scrape_progress["listings_found"] += 1

        _scrape_progress["states_done"] += 1

    except Exception as e:
        logger.error(f"CCL scrape error: {e}")
        _scrape_progress["errors"] += 1

    return count


async def _scrape_detail_landcentral(
    db, client: httpx.AsyncClient, listing: dict
) -> dict:
    """Scrape a single LandCentral property detail page for financing info."""
    url = listing.get("url")
    if not url:
        return listing

    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Down payment
        dp_match = re.search(r"down\s*(?:payment)?\s*(?:of\s*)?\$([\d,]+\.?\d*)", text, re.I)
        if dp_match:
            listing["down_payment"] = _parse_price(dp_match.group(1))

        # Monthly payment
        mp_match = re.search(r"\$([\d,]+\.?\d*)\s*/?\s*(?:per\s*)?mo", text, re.I)
        if mp_match:
            listing["monthly_payment"] = _parse_price(mp_match.group(1))

        # Description
        desc_el = soup.find("div", class_=re.compile(r"description|details|content", re.I))
        if desc_el:
            listing["description"] = desc_el.get_text(" ", strip=True)[:2000]

        # Additional images
        images = soup.find_all("img", src=re.compile(r"property|listing|land", re.I))
        if images and not listing.get("image_url"):
            src = images[0].get("src", "")
            if src and not src.startswith("data:"):
                if src.startswith("/"):
                    src = f"https://www.landcentral.com{src}"
                listing["image_url"] = src

    except Exception as e:
        logger.warning(f"Detail scrape error: {e}")

    return listing


async def _scrape_detail_ccl(
    db, client: httpx.AsyncClient, listing: dict
) -> dict:
    """Scrape a single CCL property detail page for tract details + financing."""
    url = listing.get("url")
    if not url:
        return listing

    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing

        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Down payment
        dp_match = re.search(r"down\s*(?:payment)?\s*(?:of\s*)?\$\s*([\d,]+\.?\d*)", text, re.I)
        if dp_match:
            listing["down_payment"] = _parse_price(dp_match.group(1))

        # Monthly payment
        mp_match = re.search(r"\$\s*([\d,]+\.?\d*)\s*/\s*mo", text, re.I)
        if not mp_match:
            mp_match = re.search(r"monthly\s*(?:payment)?\s*(?:of\s*)?\$\s*([\d,]+\.?\d*)", text, re.I)
        if mp_match:
            listing["monthly_payment"] = _parse_price(mp_match.group(1))

        # Features / land use info
        for pattern, field in [
            (r"building\s*permit|permitted\s*(?:for\s*)?build", "building_permitted"),
            (r"camp|rv\s*(?:ok|allowed|friendly)", "camping_allowed"),
            (r"septic|sewer", "septic_allowed"),
        ]:
            if re.search(pattern, text, re.I):
                listing[field] = True

        # Description
        desc_el = soup.find("div", class_=re.compile(r"description|detail|content", re.I))
        if desc_el:
            listing["description"] = desc_el.get_text(" ", strip=True)[:2000]

    except Exception as e:
        logger.warning(f"CCL detail scrape error: {e}")

    return listing


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Listings
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/listings")
async def list_listings(
    source: Optional[str] = Query(None, description="Filter by source id"),
    state: Optional[str] = Query(None, description="Filter by state name"),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_acreage: Optional[float] = Query(None),
    max_acreage: Optional[float] = Query(None),
    favorites_only: bool = Query(False),
    sort_by: str = Query("price", description="price, acreage, scraped_at, state"),
    sort_dir: str = Query("asc", description="asc or desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_mongodb),
):
    """List scraped land listings with optional filters."""
    query = {}

    if source:
        query["source"] = source
    if state:
        # Support comma-separated list of states
        states = [s.strip() for s in state.split(",") if s.strip()]
        if len(states) == 1:
            query["state"] = {"$regex": f"^{re.escape(states[0])}$", "$options": "i"}
        elif len(states) > 1:
            query["state"] = {"$in": states}
    if min_price is not None:
        query.setdefault("price", {})["$gte"] = min_price
    if max_price is not None:
        query.setdefault("price", {})["$lte"] = max_price
    if min_acreage is not None:
        query.setdefault("acreage", {})["$gte"] = min_acreage
    if max_acreage is not None:
        query.setdefault("acreage", {})["$lte"] = max_acreage

    if favorites_only:
        fav_hashes = set()
        async for doc in db[COL_FAVORITES].find({}, {"listing_hash": 1}):
            fav_hashes.add(doc["listing_hash"])
        if fav_hashes:
            query["hash"] = {"$in": list(fav_hashes)}
        else:
            return {"items": [], "total": 0}

    sort_field = {
        "price": "price",
        "acreage": "acreage",
        "scraped_at": "scraped_at",
        "state": "state",
        "name": "name",
    }.get(sort_by, "price")

    sort_direction = 1 if sort_dir == "asc" else -1
    col = db[COL_LISTINGS]

    total = await col.count_documents(query)
    cursor = col.find(query).sort(sort_field, sort_direction).skip(offset).limit(limit)

    # Get favorites for marking
    fav_set = set()
    async for doc in db[COL_FAVORITES].find({}, {"listing_hash": 1}):
        fav_set.add(doc["listing_hash"])

    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["is_favorite"] = doc.get("hash", "") in fav_set
        items.append(doc)

    return {"items": items, "total": total}


@router.get("/listings/{listing_hash}")
async def get_listing(listing_hash: str, db=Depends(get_mongodb)):
    """Get a single listing by hash."""
    doc = await db[COL_LISTINGS].find_one({"hash": listing_hash})
    if not doc:
        raise HTTPException(404, "Listing not found")
    doc["_id"] = str(doc["_id"])

    fav = await db[COL_FAVORITES].find_one({"listing_hash": listing_hash})
    doc["is_favorite"] = fav is not None
    return doc


@router.post("/listings/{listing_hash}/scrape-detail")
async def scrape_listing_detail(listing_hash: str, db=Depends(get_mongodb)):
    """Scrape detail page for a specific listing to get financing info."""
    doc = await db[COL_LISTINGS].find_one({"hash": listing_hash})
    if not doc:
        raise HTTPException(404, "Listing not found")

    async with httpx.AsyncClient() as client:
        source = doc.get("source", "")
        if source == "landcentral":
            doc = await _scrape_detail_landcentral(db, client, doc)
        elif source == "classiccountryland":
            doc = await _scrape_detail_ccl(db, client, doc)

    # Save updated listing
    update_data = {
        k: v for k, v in doc.items() if k != "_id"
    }
    await db[COL_LISTINGS].update_one(
        {"hash": listing_hash},
        {"$set": update_data},
    )

    doc["_id"] = str(doc["_id"]) if "_id" in doc else ""
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Favorites
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/favorites/{listing_hash}")
async def add_favorite(listing_hash: str, db=Depends(get_mongodb)):
    """Mark a listing as favorite."""
    listing = await db[COL_LISTINGS].find_one({"hash": listing_hash})
    if not listing:
        raise HTTPException(404, "Listing not found")

    await db[COL_FAVORITES].update_one(
        {"listing_hash": listing_hash},
        {
            "$set": {
                "listing_hash": listing_hash,
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"ok": True}


@router.delete("/favorites/{listing_hash}")
async def remove_favorite(listing_hash: str, db=Depends(get_mongodb)):
    """Remove a listing from favorites."""
    await db[COL_FAVORITES].delete_one({"listing_hash": listing_hash})
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Sources
# ═══════════════════════════════════════════════════════════════════════════


class SourceInput(BaseModel):
    name: str
    base_url: str
    enabled: bool = True
    scraper_type: str = "generic"
    description: str = ""


@router.get("/sources")
async def list_sources(db=Depends(get_mongodb)):
    """List all configured scraping sources."""
    col = db[COL_SOURCES]
    count = await col.count_documents({})

    if count == 0:
        # Seed default sources
        for src in DEFAULT_SOURCES:
            src["created_at"] = datetime.now(timezone.utc).isoformat()
            await col.update_one(
                {"source_id": src["source_id"]},
                {"$set": src},
                upsert=True,
            )

    items = []
    async for doc in col.find({}).sort("name", 1):
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"items": items}


@router.post("/sources")
async def add_source(body: SourceInput, db=Depends(get_mongodb)):
    """Add a new scraping source."""
    source_id = re.sub(r"[^a-z0-9]+", "_", body.name.lower()).strip("_")
    doc = {
        "source_id": source_id,
        "name": body.name,
        "base_url": body.base_url.rstrip("/"),
        "enabled": body.enabled,
        "scraper_type": body.scraper_type,
        "description": body.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COL_SOURCES].update_one(
        {"source_id": source_id},
        {"$set": doc},
        upsert=True,
    )
    doc["_id"] = source_id
    return doc


@router.patch("/sources/{source_id}")
async def update_source(source_id: str, body: dict = Body(...), db=Depends(get_mongodb)):
    """Update a source (toggle enabled, change URL, etc.)."""
    allowed = {"name", "base_url", "enabled", "scraper_type", "description"}
    update = {k: v for k, v in body.items() if k in allowed}
    if not update:
        raise HTTPException(400, "No valid fields to update")

    result = await db[COL_SOURCES].update_one(
        {"source_id": source_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Source not found")
    return {"ok": True}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, db=Depends(get_mongodb)):
    """Delete a source and its listings."""
    await db[COL_SOURCES].delete_one({"source_id": source_id})
    result = await db[COL_LISTINGS].delete_many({"source": source_id})
    return {"ok": True, "deleted_listings": result.deleted_count}


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Scraping
# ═══════════════════════════════════════════════════════════════════════════


async def _run_scrape_background(source_ids: list):
    """Background scrape worker — runs outside the HTTP request lifecycle."""
    from app.database import get_mongodb
    db = get_mongodb()

    _scrape_progress["running"] = True
    _scrape_progress["started_at"] = datetime.now(timezone.utc).isoformat()
    _scrape_progress["finished_at"] = None
    _scrape_progress["listings_found"] = 0
    _scrape_progress["errors"] = 0
    _scrape_progress["states_done"] = 0
    _scrape_progress["states_total"] = 0
    _scrape_progress["error_msg"] = None

    filters = await _get_filter_settings(db)
    results = {}

    try:
        async with httpx.AsyncClient(
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
        ) as client:
            for sid in source_ids:
                _scrape_progress["source"] = sid
                try:
                    if sid == "landcentral":
                        count = await _scrape_landcentral(db, client, filters["states"])
                    elif sid == "classiccountryland":
                        count = await _scrape_classiccountryland(db, client, filters["states"])
                    else:
                        count = 0
                    results[sid] = count

                    await db[COL_META].update_one(
                        {"key": f"last_scrape_{sid}"},
                        {
                            "$set": {
                                "key": f"last_scrape_{sid}",
                                "value": datetime.now(timezone.utc).isoformat(),
                                "count": count,
                            }
                        },
                        upsert=True,
                    )
                except Exception as e:
                    logger.error(f"Scrape error for {sid}: {e}")
                    results[sid] = f"error: {str(e)}"
                    _scrape_progress["error_msg"] = str(e)

        await db[COL_META].update_one(
            {"key": "last_scrape_all"},
            {
                "$set": {
                    "key": "last_scrape_all",
                    "value": datetime.now(timezone.utc).isoformat(),
                    "results": results,
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Background scrape fatal: {e}\n{traceback.format_exc()}")
        _scrape_progress["error_msg"] = str(e)
    finally:
        _scrape_progress["running"] = False
        _scrape_progress["finished_at"] = datetime.now(timezone.utc).isoformat()
        _scrape_progress["source"] = None


@router.get("/scrape/progress")
async def scrape_progress_endpoint():
    """Get live scrape progress (poll from frontend)."""
    return dict(_scrape_progress)


@router.get("/scrape/status")
async def scrape_status(db=Depends(get_mongodb)):
    """Get scrape status for all sources."""
    statuses = {}
    async for doc in db[COL_META].find({"key": {"$regex": "^last_scrape_"}}):
        source = doc["key"].replace("last_scrape_", "")
        statuses[source] = {
            "last_scrape": doc.get("value"),
            "count": doc.get("count", 0),
        }
    return statuses


@router.post("/scrape/{source_id}")
async def scrape_source(source_id: str, db=Depends(get_mongodb)):
    """Start scraping a specific source in background."""
    source = await db[COL_SOURCES].find_one({"source_id": source_id})
    if not source:
        raise HTTPException(404, "Source not found")

    if _scrape_progress["running"]:
        return {
            "ok": False,
            "message": f"Scrape already running ({_scrape_progress['source']})",
            "progress": dict(_scrape_progress),
        }

    asyncio.create_task(_run_scrape_background([source_id]))
    return {"ok": True, "message": f"Scraping {source_id} started in background"}


@router.post("/scrape-all")
async def scrape_all(db=Depends(get_mongodb)):
    """Start scraping all enabled sources in background."""
    if _scrape_progress["running"]:
        return {
            "ok": False,
            "message": f"Scrape already running ({_scrape_progress['source']})",
            "progress": dict(_scrape_progress),
        }

    sources = []
    async for doc in db[COL_SOURCES].find({"enabled": True}):
        sources.append(doc)

    if not sources:
        await list_sources(db=db)
        async for doc in db[COL_SOURCES].find({"enabled": True}):
            sources.append(doc)

    source_ids = [s["source_id"] for s in sources]
    asyncio.create_task(_run_scrape_background(source_ids))
    return {"ok": True, "message": f"Scraping {len(source_ids)} sources in background"}


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Stats & Utilities
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/stats")
async def get_stats(db=Depends(get_mongodb)):
    """Get overall statistics."""
    listings_total = await db[COL_LISTINGS].count_documents({})
    favorites_total = await db[COL_FAVORITES].count_documents({})
    sources_total = await db[COL_SOURCES].count_documents({})

    # Per-source counts
    pipeline = [
        {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    ]
    source_counts = {}
    async for doc in db[COL_LISTINGS].aggregate(pipeline):
        source_counts[doc["_id"]] = doc["count"]

    # State counts
    state_pipeline = [
        {"$group": {"_id": "$state", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    state_counts = {}
    async for doc in db[COL_LISTINGS].aggregate(state_pipeline):
        if doc["_id"]:
            state_counts[doc["_id"]] = doc["count"]

    # Last scrape time
    meta = await db[COL_META].find_one({"key": "last_scrape_all"})
    last_scrape = meta.get("value") if meta else None

    # Price stats
    price_pipeline = [
        {"$match": {"price": {"$gt": 0}}},
        {
            "$group": {
                "_id": None,
                "min_price": {"$min": "$price"},
                "max_price": {"$max": "$price"},
                "avg_price": {"$avg": "$price"},
            }
        },
    ]
    price_stats = {}
    async for doc in db[COL_LISTINGS].aggregate(price_pipeline):
        price_stats = {
            "min_price": round(doc["min_price"], 2) if doc["min_price"] else 0,
            "max_price": round(doc["max_price"], 2) if doc["max_price"] else 0,
            "avg_price": round(doc["avg_price"], 2) if doc["avg_price"] else 0,
        }

    return {
        "listings": listings_total,
        "favorites": favorites_total,
        "sources": sources_total,
        "by_source": source_counts,
        "by_state": state_counts,
        "last_scrape": last_scrape,
        **price_stats,
    }


@router.delete("/clear")
async def clear_all(db=Depends(get_mongodb)):
    """Clear all scraped data."""
    r1 = await db[COL_LISTINGS].delete_many({})
    r2 = await db[COL_META].delete_many({})
    return {
        "ok": True,
        "deleted_listings": r1.deleted_count,
        "deleted_meta": r2.deleted_count,
    }


@router.delete("/clear/{source_id}")
async def clear_source(source_id: str, db=Depends(get_mongodb)):
    """Clear listings from a specific source."""
    result = await db[COL_LISTINGS].delete_many({"source": source_id})
    return {"ok": True, "deleted": result.deleted_count}
