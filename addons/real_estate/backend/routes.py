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
from curl_cffi.requests import AsyncSession as CffiSession
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
COL_WATCHED = "re_watched"
COL_SOURCES = "re_sources"
COL_META = "re_meta"
COL_FILTER_PRESETS = "re_filter_presets"

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
_scrape_stop_requested = False
_scrape_progress = {
    "running": False,
    "source": None,
    "source_index": 0,
    "sources_total": 0,
    "states_done": 0,
    "states_total": 0,
    "listings_found": 0,
    "new_count": 0,
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


# ── Zoning normalization ─────────────────────────────────────────────────
ZONING_PATTERNS = {
    "Residential": r"\b(residential|r-?[1-5]|rr-?\d|sfr|single.?family|multi.?family|townhome|housing|subdivision|dwelling|home.?site)\b",
    "Agricultural": r"\b(agricultur|farm|ranch|ag\b|ag-?\d|grazing|crop|timber|forestry|pasture|orchard|livestock)\b",
    "Commercial": r"\b(commercial|c-?\d|retail|office|business|storefront)\b",
    "Industrial": r"\b(industrial|i-?\d|manufactur|warehouse|factory|heavy.?use)\b",
    "Rural / Unzoned": r"\b(rural|unzoned|no.?zoning|none|unrestricted|open.?use|vacant.?land|county|unincorporated)\b",
    "Mixed Use": r"\b(mixed.?use|planned.?unit|pud|overlay|transitional|general.?use)\b",
    "Recreational": r"\b(recreat|hunt|fish|camp|conservation|wilderness|park|leisure|resort)\b",
}


def _normalize_zoning(raw: str) -> str:
    """Map raw zoning text from scrapers to a clean category."""
    if not raw:
        return "Other"
    for category, pattern in ZONING_PATTERNS.items():
        if re.search(pattern, raw, re.IGNORECASE):
            return category
    return "Other"


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
    {
        "source_id": "landmodo",
        "name": "Landmodo",
        "base_url": "https://www.landmodo.com",
        "enabled": True,
        "scraper_type": "landmodo",
        "description": "Owner-financed land marketplace, 8000+ listings across all US states",
    },
    {
        "source_id": "discountlots",
        "name": "Discount Lots",
        "base_url": "https://discountlots.com",
        "enabled": True,
        "scraper_type": "discountlots",
        "description": "Affordable vacant lots, avg 47% off, $1 down payment",
    },
    {
        "source_id": "landcentury",
        "name": "Land Century",
        "base_url": "https://www.landcentury.com",
        "enabled": True,
        "scraper_type": "landcentury",
        "description": "Owner finance deals, under $1000 land deals, 2000+ listings",
    },
    {
        "source_id": "ownerfinancedland",
        "name": "Owner Financed Land",
        "base_url": "https://www.ownerfinancedland.com",
        "enabled": True,
        "scraper_type": "ownerfinancedland",
        "description": "Family-owned, no brokers. OR, AZ, CO, NV, CA, TX, FL. No credit checks.",
    },
    {
        "source_id": "landzero",
        "name": "LandZero",
        "base_url": "https://www.landzero.com",
        "enabled": True,
        "scraper_type": "landzero",
        "description": "Zero down, zero credit checks. AZ, CO, FL, NV, NM, UT, MI, CA.",
    },
    {
        "source_id": "billyland",
        "name": "BillyLand",
        "base_url": "https://www.billyland.com",
        "enabled": True,
        "scraper_type": "billyland",
        "description": "Cheap land auctions across 16 states, owner financing, no credit check",
    },
    {
        "source_id": "elegmentland",
        "name": "Elegment Land",
        "base_url": "https://land.elegment.com",
        "enabled": True,
        "scraper_type": "elegmentland",
        "description": "Affordable land with owner financing in AL, CA, AR, SC, NC, TX, CO, OK, TN, WA",
    },
    {
        "source_id": "landequities",
        "name": "Land Equities",
        "base_url": "https://landequities.com",
        "enabled": True,
        "scraper_type": "landequities",
        "description": "Land 50-80% below market value. AZ, CA, CO, HI, NV, NM, OR, TX",
    },
    {
        "source_id": "yourcheapland",
        "name": "YourCheapLand",
        "base_url": "https://yourcheapland.com",
        "enabled": True,
        "scraper_type": "yourcheapland",
        "description": "Cheap land in TX, AZ, NM, CO, UT, OK. Off-grid homesteads, recreation.",
    },
    {
        "source_id": "terraprimelots",
        "name": "Terra Prime Lots",
        "base_url": "https://www.terraprimelots.com",
        "enabled": True,
        "scraper_type": "terraprimelots",
        "description": "Affordable land, full owner financing, no credit check. FL, TX, CO, NV, NM.",
    },
    {
        "source_id": "rawestate",
        "name": "Raw Estate Enterprise",
        "base_url": "https://www.rawestateenterprise.com",
        "enabled": True,
        "scraper_type": "rawestate",
        "description": "AZ, TX, NV land. FSBO, no credit checks, low monthly payments.",
    },
    {
        "source_id": "landlimited",
        "name": "Land Limited",
        "base_url": "https://landlimited.com",
        "enabled": True,
        "scraper_type": "landlimited",
        "description": "Rural land across all 50 states. Cabin, off-grid, recreation, single family.",
    },
    {
        "source_id": "landandfarm",
        "name": "LandAndFarm",
        "base_url": "https://www.landandfarm.com",
        "enabled": True,
        "scraper_type": "landandfarm",
        "description": "Major marketplace — farms, ranches, cheap land. Owner financing filter.",
    },
    {
        "source_id": "landsearch",
        "name": "LandSearch",
        "base_url": "https://www.landsearch.com",
        "enabled": True,
        "scraper_type": "landsearch",
        "description": "Large aggregator — 370K+ listings, all 50 states. 2,500+ WA properties.",
    },
    {
        "source_id": "landwatch",
        "name": "LandWatch",
        "base_url": "https://www.landwatch.com",
        "enabled": True,
        "scraper_type": "landwatch",
        "description": "Major marketplace — 4,400+ WA listings. Farms, ranches, recreational land.",
    },
    {
        "source_id": "horizonlandsales",
        "name": "Horizon Land Sales",
        "base_url": "https://horizonlandsales.com",
        "enabled": True,
        "scraper_type": "horizonlandsales",
        "description": "Below-market-value land. WA, MT properties. Owner financing, deep discounts.",
    },
    {
        "source_id": "homescom",
        "name": "Homes.com",
        "base_url": "https://www.homes.com",
        "enabled": True,
        "scraper_type": "homescom",
        "description": "Major real estate portal — land & lots for sale across all US states.",
    },
    {
        "source_id": "landcom",
        "name": "Land.com",
        "base_url": "https://www.land.com",
        "enabled": True,
        "scraper_type": "landcom",
        "description": "Major land marketplace — farms, ranches, all land types across US.",
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


# Global scrape mode — set before scraping starts, read by _smart_upsert
_scrape_mode = "full"  # "full" | "new_only" | "favorites"


async def _smart_upsert(col, listing_hash: str, fresh_data: dict):
    """Insert new listing or update only volatile fields (price, availability).

    Preserves detail fields (description, down_payment, monthly_payment, etc.)
    that were scraped separately. Tracks price history.

    In 'new_only' mode: only insert brand-new listings, skip existing entirely.
    """
    existing = await col.find_one({"hash": listing_hash})
    now = datetime.now(timezone.utc).isoformat()

    # Skip soft-deleted listings — never re-insert them
    if existing and existing.get("deleted"):
        return False

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
        _scrape_progress["new_count"] += 1
        return True

    # In new_only mode — skip updates for existing listings entirely
    if _scrape_mode == "new_only":
        return False

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

                # Go up to grandparent (article wrapper) which contains
                # both header and property-details (with acreage, county, etc.)
                card = parent.parent or parent
                text_block = card.get_text(" ", strip=True)

                # Extract property #
                prop_match = re.search(r"Property\s*#?\s*(\d+)", text_block)
                prop_id = prop_match.group(1) if prop_match else ""

                # Extract size
                size_match = re.search(r"([\d.]+)\s*Acres?", text_block, re.I)
                acreage = float(size_match.group(1)) if size_match else None

                # Extract county
                county = ""
                county_el = card.find(string=re.compile(r"County", re.I))
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
                img = card.find("img")
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

        # Zoning info & extra details — LandCentral has a properties table
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) == 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(" ", strip=True)
                    if label == "Size" and value and not listing.get("acreage"):
                        am = re.search(r"([\d.]+)", value)
                        if am:
                            listing["acreage"] = float(am.group(1))
                    elif label == "Zoning" and value:
                        listing["zoning"] = value
                    elif label == "Zoning Code" and value:
                        listing["zoning_code"] = value
                    elif label == "Zoning Definition" and value:
                        listing["zoning_definition"] = value[:2000]
                    elif label == "Road Access" and value:
                        listing["road_access"] = value
                    elif label == "Slope Description" and value:
                        listing["slope"] = value
                    elif label == "On Property Usage/Potential" and value:
                        listing["usage_potential"] = value
                    elif "hoa" in label.lower():
                        if "dues" in label.lower() and value:
                            listing["hoa_dues"] = value
                            # Parse numeric amount
                            dues_match = re.search(r"\$(\d[\d,.]*)", value)
                            if dues_match:
                                amt = _parse_price(dues_match.group(1))
                                listing["hoa_amount"] = amt or 0
                                listing["hoa"] = "yes" if amt and amt > 0 else "no"
                            else:
                                listing["hoa"] = "no" if value.strip() in ("$0", "0", "", "None", "N/A") else "yes"
                        elif label == "HOA" and value.strip():
                            listing["hoa_name"] = value.strip()
                        elif label == "HOA Info" and value.strip():
                            listing["hoa_info"] = value.strip()[:500]
                    elif label == "Estimated Annual Taxes" and value:
                        listing["annual_taxes"] = value

        # Additional images
        images = soup.find_all("img", src=re.compile(r"property|listing|land", re.I))
        if images and not listing.get("image_url"):
            src = images[0].get("src", "")
            if src and not src.startswith("data:"):
                if src.startswith("/"):
                    src = f"https://www.landcentral.com{src}"
                listing["image_url"] = src

        listing["detail_scraped"] = True

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

        # Zoning info — CCL has it in FAQ section
        for btn in soup.find_all("button", class_="faq-question"):
            q = btn.get_text(strip=True).lower()
            if "zoned" in q or "zoning" in q:
                ans_div = btn.find_next_sibling("div", class_="faq-answer")
                if ans_div:
                    ans_text = ans_div.get_text(" ", strip=True)
                    # Extract zoning type from "The zoning allows X" or "zoned X"
                    zm = re.search(
                        r"(?:zoning\s+allows|zoned\s+(?:as\s+)?)([^.;]+)",
                        ans_text, re.I,
                    )
                    if zm:
                        listing["zoning"] = zm.group(1).strip()
                    # Store full answer as definition
                    listing["zoning_definition"] = ans_text[:2000]
                break

        listing["detail_scraped"] = True

    except Exception as e:
        logger.warning(f"CCL detail scrape error: {e}")

    return listing


# ═══════════════════════════════════════════════════════════════════════════
# NEW SCRAPERS — Landmodo, Discount Lots, Land Century, OwnerFinancedLand, LandZero
# ═══════════════════════════════════════════════════════════════════════════

# --- State abbreviation map ---
STATE_ABBREVS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

# Reverse lookup: full name -> abbreviation
STATE_NAME_TO_ABBR = {v.lower(): k for k, v in STATE_ABBREVS.items()}


def _extract_state_from_text(text: str) -> str:
    """Try to extract a US state name from text. Returns title-cased state or ''."""
    if not text:
        return ""
    # Check for abbreviation (2 uppercase letters)
    m = re.search(r"\b([A-Z]{2})\b", text)
    if m and m.group(1) in STATE_ABBREVS:
        return STATE_ABBREVS[m.group(1)]
    # Check for full state name
    text_lower = text.lower()
    for name in sorted(STATE_NAME_TO_ABBR.keys(), key=len, reverse=True):
        if name in text_lower:
            return name.title()
    return ""


# ─────────────────────────────────────────────────────────────────────────
# LANDMODO — https://www.landmodo.com/properties?page=N
# ─────────────────────────────────────────────────────────────────────────

LANDMODO_MAX_PAGES = 25  # 25 per page, scrape first 25 pages = ~625 listings


async def _scrape_landmodo(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape Landmodo.com — paginated properties listing."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = LANDMODO_MAX_PAGES
    _scrape_progress["states_done"] = 0

    for page in range(1, LANDMODO_MAX_PAGES + 1):
        url = f"https://www.landmodo.com/properties?page={page}"
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp:
                _scrape_progress["errors"] += 1
                _scrape_progress["states_done"] = page
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find all property links matching /properties/{id}/{slug}/{title}
            links = soup.find_all("a", href=re.compile(r"/properties/\d+/"))
            seen_urls = set()

            for link in links:
                href = link.get("href", "")
                if not href or href in seen_urls:
                    continue
                # Skip duplicates (title link appears twice per card)
                clean_href = href.split("?")[0]
                if clean_href in seen_urls:
                    continue
                seen_urls.add(clean_href)

                if href.startswith("/"):
                    href = f"https://www.landmodo.com{href}"

                name = link.get_text(strip=True)
                if not name or name == "View More" or len(name) < 5:
                    continue

                # Walk up to find card container
                card = link
                for _ in range(6):
                    if card.parent:
                        card = card.parent
                    else:
                        break

                card_text = card.get_text(" ", strip=True)

                # Extract price — Landmodo shows price like "7,195.00"
                price = None
                price_matches = re.findall(r"([\d,]+\.\d{2})", card_text)
                for pm in price_matches:
                    p = _parse_price(pm)
                    if p and p > 50 and (price is None or p < price):
                        price = p

                # Extract acreage from title or card text
                acreage = None
                acre_m = re.search(r"([\d.]+)\s*(?:-?\s*)?Acres?", card_text, re.I)
                if not acre_m:
                    acre_m = re.search(r"([\d.]+)\s*(?:-?\s*)?Ac\b", card_text, re.I)
                if acre_m:
                    acreage = float(acre_m.group(1))

                # Extract state from address/location text
                state = _extract_state_from_text(card_text)
                if states_filter and state and state.lower() not in states_filter:
                    continue

                # Extract county
                county = ""
                county_m = re.search(r"([\w\s]+?)\s*County", card_text)
                if county_m:
                    county = county_m.group(1).strip()

                # Extract monthly payment
                monthly = None
                mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*mo", card_text, re.I)
                if not mp_m:
                    mp_m = re.search(r"\$([\d,]+\.?\d*)\s*(?:per\s*)?month", card_text, re.I)
                if mp_m:
                    monthly = _parse_price(mp_m.group(1))

                # Down payment
                down = None
                dp_m = re.search(r"\$([\d,]+)\s*(?:down|Down)", card_text)
                if dp_m:
                    down = _parse_price(dp_m.group(1))

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    img_src = img.get("src") or img.get("data-src") or ""
                    if img_src and not img_src.startswith("data:"):
                        if img_src.startswith("/"):
                            img_src = f"https://www.landmodo.com{img_src}"
                        img_url = img_src

                listing_hash = _hash(f"landmodo:{clean_href}")
                fresh = {
                    "hash": listing_hash,
                    "source": "landmodo",
                    "source_name": "Landmodo",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": county,
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": down,
                    "monthly_payment": monthly,
                    "financing_available": True,
                    "land_type": None,
                    "building_permitted": None,
                    "camping_allowed": None,
                    "septic_allowed": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                    "hoa": "no" if "no hoa" in card_text.lower() else None,
                }

                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = page

            # If no property links found, we've hit the end
            if not seen_urls:
                break

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Landmodo scrape error (page {page}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = page

    return count


async def _scrape_detail_landmodo(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Landmodo property detail page."""
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
        dp_m = re.search(r"\$([\d,]+\.?\d*)\s*(?:down|Down)", text)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # Monthly payment
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*mo", text, re.I)
        if not mp_m:
            mp_m = re.search(r"\$([\d,]+\.?\d*)\s*(?:per\s*)?month", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Description
        desc_el = soup.find("div", class_=re.compile(r"description|detail|content|property", re.I))
        if desc_el:
            listing["description"] = desc_el.get_text(" ", strip=True)[:2000]

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"
        elif re.search(r"hoa\s*(?:fee|dues)", text, re.I):
            listing["hoa"] = "yes"

        # Zoning
        zm = re.search(r"(?:zoning|zoned)\s*[:=]?\s*([^.\n]+)", text, re.I)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"Landmodo detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# DISCOUNT LOTS — https://discountlots.com/property-map
# ─────────────────────────────────────────────────────────────────────────


async def _scrape_discountlots(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape DiscountLots.com — property map page with all listings."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = 1
    _scrape_progress["states_done"] = 0

    try:
        resp = await _fetch_with_retry(client, "https://discountlots.com/property-map")
        if not resp:
            _scrape_progress["errors"] += 1
            return 0

        soup = BeautifulSoup(resp.text, "html.parser")

        # Cards link to /property/{id} — find all such links
        links = soup.find_all("a", href=re.compile(r"/property/"))
        seen = set()

        for link in links:
            href = link.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)

            if href.startswith("/"):
                href = f"https://discountlots.com{href}"

            link_text = link.get_text(" ", strip=True)

            # Walk up to card container
            card = link
            for _ in range(5):
                if card.parent:
                    card = card.parent
                else:
                    break

            card_text = card.get_text(" ", strip=True)

            # Skip nav/footer links
            if len(card_text) < 20:
                continue

            # Property ID — e.g., P077960
            prop_m = re.search(r"(P\d{5,})", card_text)
            prop_id = prop_m.group(1) if prop_m else ""

            # Title / name — use property ID + location
            name = ""
            location_parts = []

            # Acreage
            acre_m = re.search(r"([\d.]+)\s*acres?", card_text, re.I)
            acreage = float(acre_m.group(1)) if acre_m else None

            # Monthly payment — "Just $217/month" or "$255/month"
            monthly = None
            mp_m = re.search(r"\$([\d,]+)\s*/\s*month", card_text, re.I)
            if not mp_m:
                mp_m = re.search(r"Just\s*\$([\d,]+)", card_text, re.I)
            if mp_m:
                monthly = _parse_price(mp_m.group(1))

            # Zoning — "Zoning: Residential Agriculture"
            zoning = ""
            zm = re.search(r"Zoning:\s*([^\n]+?)(?:\s*\d+\.?\d*\s*acres?|$)", card_text, re.I)
            if zm:
                zoning = zm.group(1).strip()

            # Location — city, state at bottom of card
            # Pattern: last line before "LEARN MORE" or end
            loc_m = re.search(r"([A-Za-z\s]+),\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)?|[A-Z]{2})\s*$", card_text.replace("LEARN MORE", "").replace("BUY NOW", "").strip())
            if not loc_m:
                loc_m = re.search(r"([A-Z][A-Za-z\s]+),\s*(\w+(?:\s\w+)?)\s*(?:LEARN|BUY|$)", card_text)
            city = ""
            state = ""
            if loc_m:
                city = loc_m.group(1).strip()
                state_str = loc_m.group(2).strip()
                state = STATE_ABBREVS.get(state_str.upper(), state_str.title())
            if not state:
                state = _extract_state_from_text(card_text)

            if states_filter and state and state.lower() not in states_filter:
                continue

            name = f"{acreage} acres in {city}, {state}" if city and acreage else (f"{prop_id} — {city}, {state}" if city else prop_id)

            # Price — try to find cash price (not monthly)
            price = None
            # Discount Lots shows monthly prominently; cash price is on detail page
            # Estimate: monthly * ~48 months (rough)
            if monthly:
                price = round(monthly * 48, 2)

            listing_hash = _hash(f"discountlots:{href}")
            fresh = {
                "hash": listing_hash,
                "source": "discountlots",
                "source_name": "Discount Lots",
                "name": name[:200],
                "url": href,
                "property_id": prop_id,
                "state": state,
                "county": "",
                "acreage": acreage,
                "price": price,
                "original_price": None,
                "down_payment": None,
                "monthly_payment": monthly,
                "financing_available": True,
                "land_type": None,
                "building_permitted": None,
                "camping_allowed": None,
                "septic_allowed": None,
                "image_url": None,
                "description": "",
                "is_foreclosure": False,
                "zoning": zoning if zoning else None,
            }

            await _smart_upsert(col, listing_hash, fresh)
            count += 1
            _scrape_progress["listings_found"] = count

        _scrape_progress["states_done"] = 1

    except Exception as e:
        logger.error(f"DiscountLots scrape error: {e}")
        _scrape_progress["errors"] += 1

    return count


async def _scrape_detail_discountlots(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Discount Lots property detail page for real price, zoning, etc."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Cash price
        cash_m = re.search(r"(?:cash|price|total)\s*(?:price)?\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if cash_m:
            listing["price"] = _parse_price(cash_m.group(1))

        # Down payment
        dp_m = re.search(r"(?:down|deposit)\s*(?:payment)?\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # Monthly
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm and not listing.get("zoning"):
            listing["zoning"] = zm.group(1).strip()[:200]

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # Description
        desc_el = soup.find("div", class_=re.compile(r"description|detail|content", re.I))
        if desc_el:
            listing["description"] = desc_el.get_text(" ", strip=True)[:2000]

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"DiscountLots detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LAND CENTURY — https://www.landcentury.com/owner-finance-deals?page=N
# ─────────────────────────────────────────────────────────────────────────

LANDCENTURY_MAX_PAGES = 30


async def _scrape_landcentury(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandCentury.com — paginated owner finance deals."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = LANDCENTURY_MAX_PAGES
    _scrape_progress["states_done"] = 0

    for page in range(1, LANDCENTURY_MAX_PAGES + 1):
        url = f"https://www.landcentury.com/owner-finance-deals?page={page}"
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp:
                _scrape_progress["errors"] += 1
                _scrape_progress["states_done"] = page
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find property links: /land-for-sale/{state}/{slug}
            links = soup.find_all("a", href=re.compile(r"/land-for-sale/[\w-]+/[\w-]+"))
            seen = set()
            found_any = False

            for link in links:
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)
                found_any = True

                if href.startswith("/"):
                    href = f"https://www.landcentury.com{href}"

                # Walk up to card
                card = link
                for _ in range(4):
                    if card.parent:
                        card = card.parent
                    else:
                        break

                card_text = card.get_text(" ", strip=True)

                # Title: "X.XX Acres for Sale in City, State"
                name = link.get_text(strip=True)
                if not name or len(name) < 5:
                    continue

                # Parse from title: "4.86 Acres for Sale in Mesita, Colorado"
                title_m = re.match(
                    r"([\d.]+)\s*Acres?\s*(?:for\s*Sale\s*)?in\s+(.+?)$",
                    name, re.I,
                )
                acreage = None
                city = ""
                state = ""
                if title_m:
                    acreage = float(title_m.group(1))
                    location = title_m.group(2).strip()
                    parts = [p.strip() for p in location.rsplit(",", 1)]
                    if len(parts) == 2:
                        city = parts[0]
                        state = parts[1]
                    else:
                        state = _extract_state_from_text(location)

                # Also check from URL
                if not state:
                    state_slug_m = re.search(r"/land-for-sale/([\w-]+)/", href)
                    if state_slug_m:
                        state = _slug_to_state(state_slug_m.group(1))

                if states_filter and state and state.lower() not in states_filter:
                    continue

                # Price
                price = None
                price_m = re.search(r"\$([\d,]+\.?\d*)", card_text)
                if price_m:
                    price = _parse_price(price_m.group(1))

                # County
                county = ""
                county_m = re.search(r"([\w\s]+?)\s*County", card_text)
                if county_m:
                    county = county_m.group(1).strip()

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    img_src = img.get("src") or img.get("data-src") or ""
                    if img_src and not img_src.startswith("data:"):
                        if img_src.startswith("/"):
                            img_src = f"https://www.landcentury.com{img_src}"
                        img_url = img_src

                listing_hash = _hash(f"landcentury:{href}")
                fresh = {
                    "hash": listing_hash,
                    "source": "landcentury",
                    "source_name": "Land Century",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": county,
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "building_permitted": None,
                    "camping_allowed": None,
                    "septic_allowed": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }

                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = page

            if not found_any:
                break  # No more pages

            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"LandCentury scrape error (page {page}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = page

    return count


async def _scrape_detail_landcentury(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Land Century property detail page."""
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
        dp_m = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # Monthly payment
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Description
        desc_el = (
            soup.find("div", class_=re.compile(r"description|detail", re.I))
            or soup.find("div", class_=re.compile(r"property", re.I))
        )
        if desc_el:
            listing["description"] = desc_el.get_text(" ", strip=True)[:2000]

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"
        elif re.search(r"hoa\s*(?:fee|dues)", text, re.I):
            listing["hoa"] = "yes"

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandCentury detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# OWNER FINANCED LAND — https://www.ownerfinancedland.com/
# ─────────────────────────────────────────────────────────────────────────


async def _scrape_ownerfinancedland(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape OwnerFinancedLand.com — WordPress property posts."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = 1
    _scrape_progress["states_done"] = 0

    try:
        # Main page + potentially paginated
        for page_url in [
            "https://www.ownerfinancedland.com/",
            "https://www.ownerfinancedland.com/page/2/",
            "https://www.ownerfinancedland.com/page/3/",
        ]:
            resp = await _fetch_with_retry(client, page_url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find property links — WordPress posts with property URLs
            links = soup.find_all("a", href=re.compile(
                r"ownerfinancedland\.com/.+-(?:for-sale|lot|acres)", re.I
            ))
            seen = set()

            for link in links:
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)

                name = link.get_text(strip=True)
                if not name or len(name) < 5 or name.upper() in ("VIEW PROPERTY", "LEARN MORE"):
                    continue

                # Walk up to card
                card = link
                for _ in range(4):
                    if card.parent:
                        card = card.parent
                    else:
                        break

                card_text = card.get_text(" ", strip=True)

                # Parse title: "1.25 Acres For Sale Sun Valley Arizona Lot 110"
                acreage = None
                am = re.search(r"([\d.]+)\s*Acres?", name, re.I)
                if am:
                    acreage = float(am.group(1))

                # State from title
                state = _extract_state_from_text(name)
                if states_filter and state and state.lower() not in states_filter:
                    continue

                # City — try before state name in title
                city = ""
                if state:
                    cm = re.search(
                        rf"(?:Sale|in)\s+([\w\s]+?)\s+{re.escape(state)}", name, re.I
                    )
                    if cm:
                        city = cm.group(1).strip()

                # Price from card text
                price = None
                pm = re.search(r"Cash\s*Price\s*[:=]?\s*\$([\d,]+\.?\d*)", card_text, re.I)
                if pm:
                    price = _parse_price(pm.group(1))
                if not price:
                    all_prices = re.findall(r"\$([\d,]+\.?\d*)", card_text)
                    for pp in all_prices:
                        p = _parse_price(pp)
                        if p and p > 100:
                            price = p
                            break

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    img_src = img.get("src") or img.get("data-src") or ""
                    if img_src and not img_src.startswith("data:"):
                        img_url = img_src

                listing_hash = _hash(f"ofl:{href}")
                fresh = {
                    "hash": listing_hash,
                    "source": "ownerfinancedland",
                    "source_name": "Owner Financed Land",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": "",
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "building_permitted": None,
                    "camping_allowed": None,
                    "septic_allowed": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }

                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            await asyncio.sleep(0.5)

        _scrape_progress["states_done"] = 1

    except Exception as e:
        logger.error(f"OwnerFinancedLand scrape error: {e}")
        _scrape_progress["errors"] += 1

    return count


async def _scrape_detail_ownerfinancedland(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape OwnerFinancedLand property detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Cash price
        pm = re.search(r"Cash\s*Price\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if pm:
            listing["price"] = _parse_price(pm.group(1))

        # Down payment
        dp_m = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # Monthly
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Description
        article = soup.find("article") or soup.find("div", class_=re.compile(r"entry|content|post", re.I))
        if article:
            listing["description"] = article.get_text(" ", strip=True)[:2000]

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # Road access
        if re.search(r"road\s*(?:frontage|access)", text, re.I):
            listing["road_access"] = "Yes"

        # Power
        if re.search(r"power\s*(?:close|available|nearby)", text, re.I):
            listing["usage_potential"] = "Power available"

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"OwnerFinancedLand detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LANDZERO — https://www.landzero.com/land-for-sale-in-america/
# ─────────────────────────────────────────────────────────────────────────

LANDZERO_STATE_URLS = [
    ("arizona", "https://www.landzero.com/arizona-cheap-land/"),
    ("california", "https://www.landzero.com/california-cheap-land-for-sale/"),
    ("colorado", "https://www.landzero.com/colorado-cheap-land/"),
    ("florida", "https://www.landzero.com/florida-cheap-land/"),
    ("michigan", "https://www.landzero.com/michigan-cheap-land/"),
    ("new-mexico", "https://www.landzero.com/new-mexico-cheap-land/"),
    ("nevada", "https://www.landzero.com/nevada-cheap-land/"),
    ("utah", "https://www.landzero.com/utah-cheap-land/"),
]


async def _scrape_landzero(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandZero.com — WooCommerce product pages per state."""
    col = db[COL_LISTINGS]
    count = 0

    pages_to_scrape = LANDZERO_STATE_URLS
    if states_filter:
        pages_to_scrape = [
            (s, u) for s, u in LANDZERO_STATE_URLS
            if _slug_to_state(s).lower() in states_filter
        ]

    # Also scrape the main shop page
    all_urls = [("all", "https://www.landzero.com/land-for-sale-in-america/")] + pages_to_scrape

    _scrape_progress["states_total"] = len(all_urls)
    _scrape_progress["states_done"] = 0

    for idx, (state_slug, page_url) in enumerate(all_urls):
        try:
            resp = await _fetch_with_retry(client, page_url)
            if not resp:
                _scrape_progress["errors"] += 1
                _scrape_progress["states_done"] = idx + 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            state_name = _slug_to_state(state_slug) if state_slug != "all" else ""

            # WooCommerce product links: /product/{slug}/
            links = soup.find_all("a", href=re.compile(r"/product/[\w-]+"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)

                if href.startswith("/"):
                    href = f"https://www.landzero.com{href}"

                # Walk up for card content
                card = link
                for _ in range(5):
                    if card.parent:
                        card = card.parent
                    else:
                        break

                card_text = card.get_text(" ", strip=True)
                name = link.get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                if name.lower() in ("add to cart", "buy now", "view", "select options"):
                    continue

                # Acreage from name/card
                acreage = None
                am = re.search(r"([\d.]+)\s*(?:Acres?|Ac\b)", card_text, re.I)
                if am:
                    acreage = float(am.group(1))

                # Price from card — WooCommerce shows price span
                price = None
                price_el = card.find("span", class_=re.compile(r"price|amount"))
                if price_el:
                    price = _parse_price(price_el.get_text(strip=True))
                if not price:
                    pm = re.findall(r"\$([\d,]+\.?\d*)", card_text)
                    for pp in pm:
                        p = _parse_price(pp)
                        if p and p > 50:
                            price = p
                            break

                # State from context or title
                st = state_name or _extract_state_from_text(name) or _extract_state_from_text(card_text)
                if states_filter and st and st.lower() not in states_filter:
                    continue

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    img_src = img.get("src") or img.get("data-src") or ""
                    if img_src and not img_src.startswith("data:"):
                        img_url = img_src

                listing_hash = _hash(f"landzero:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "landzero",
                    "source_name": "LandZero",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": st,
                    "county": "",
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "building_permitted": None,
                    "camping_allowed": None,
                    "septic_allowed": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }

                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = idx + 1
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"LandZero scrape error ({state_slug}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = idx + 1

    return count


async def _scrape_detail_landzero(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape LandZero product detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Price from WooCommerce
        price_el = soup.find("p", class_="price")
        if price_el:
            pm = re.search(r"\$([\d,]+\.?\d*)", price_el.get_text(strip=True))
            if pm:
                listing["price"] = _parse_price(pm.group(1))

        # Monthly payment
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Down payment
        dp_m = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # Description
        desc_el = soup.find("div", class_=re.compile(r"product.*description|entry-content|summary", re.I))
        if desc_el:
            listing["description"] = desc_el.get_text(" ", strip=True)[:2000]

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandZero detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# BILLYLAND — https://www.billyland.com/{State}-Land-for-Sale/Auctions
# ─────────────────────────────────────────────────────────────────────────

BILLYLAND_STATES = [
    "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Florida", "Georgia", "Hawaii", "Kentucky", "Minnesota",
    "Missouri", "New-Mexico", "Oregon", "South-Carolina",
    "Tennessee", "Texas",
]


async def _scrape_billyland(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape BillyLand.com — auction-style land per state."""
    col = db[COL_LISTINGS]
    count = 0

    states = BILLYLAND_STATES
    if states_filter:
        states = [s for s in BILLYLAND_STATES if _slug_to_state(s).lower() in states_filter]

    _scrape_progress["states_total"] = len(states)
    _scrape_progress["states_done"] = 0

    for idx, state_slug in enumerate(states):
        url = f"https://www.billyland.com/{state_slug}-Land-for-Sale/Auctions"
        state_name = _slug_to_state(state_slug)
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp:
                _scrape_progress["errors"] += 1
                _scrape_progress["states_done"] = idx + 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Auction links: /{State}-Land-for-Sale/Auctions/{id}/ViewAuction
            links = soup.find_all("a", href=re.compile(r"/Auctions/\d+/ViewAuction"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)
                if href.startswith("/"):
                    href = f"https://www.billyland.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 5:
                    continue

                # Walk up for card text
                card = link
                for _ in range(5):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Acreage from title: "5.1 Acres of Colorado Land"
                acreage = None
                am = re.search(r"([\d.]+)\s*Acres?", name, re.I)
                if am:
                    acreage = float(am.group(1))

                # Price: Current Bid: $725.00
                price = None
                pm = re.search(r"Current\s*Bid[:\s]*\$([\d,]+\.?\d*)", card_text, re.I)
                if pm:
                    price = _parse_price(pm.group(1))

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    src = img.get("src") or ""
                    if src and not src.startswith("data:") and "spacer" not in src:
                        if src.startswith("/"):
                            src = f"https://www.billyland.com{src}"
                        img_url = src

                listing_hash = _hash(f"billyland:{href}")
                fresh = {
                    "hash": listing_hash,
                    "source": "billyland",
                    "source_name": "BillyLand",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state_name,
                    "county": "",
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = idx + 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"BillyLand scrape error ({state_slug}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = idx + 1

    return count


async def _scrape_detail_billyland(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape BillyLand auction detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Monthly payment
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Down payment
        dp_m = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # Acreage (backup)
        if not listing.get("acreage"):
            am = re.search(r"([\d.]+)\s*Acres?", text, re.I)
            if am:
                listing["acreage"] = float(am.group(1))

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"BillyLand detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# ELEGMENT LAND — https://land.elegment.com/all-land/
# ─────────────────────────────────────────────────────────────────────────

ELEGMENT_STATES = [
    "alabama", "arkansas", "california", "colorado", "north-carolina",
    "oklahoma", "south-carolina", "tennessee", "texas", "washington",
]


async def _scrape_elegmentland(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape Elegment Land — property pages by state."""
    col = db[COL_LISTINGS]
    count = 0

    states = ELEGMENT_STATES
    if states_filter:
        states = [s for s in ELEGMENT_STATES if _slug_to_state(s).lower() in states_filter]

    # Build URLs: per-state pages + main all-land page
    urls = [("all", "https://land.elegment.com/all-land/")]
    for s in states:
        urls.append((s, f"https://land.elegment.com/land-for-sale/{s}/"))

    _scrape_progress["states_total"] = len(urls)
    _scrape_progress["states_done"] = 0

    for idx, (state_slug, page_url) in enumerate(urls):
        try:
            resp = await _fetch_with_retry(client, page_url)
            if not resp:
                _scrape_progress["states_done"] = idx + 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Property links: /property-for-sale/{slug}
            links = soup.find_all("a", href=re.compile(r"/property-for-sale/[\w_-]+"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)

                if href.startswith("/"):
                    href = f"https://land.elegment.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 5 or name.lower() in ("view property", "view more"):
                    continue

                card = link
                for _ in range(5):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Acreage from title: "0.09 Acre" or "2.06 Acres"
                acreage = None
                am = re.search(r"([\d.]+)\s*Acres?", name, re.I)
                if am:
                    acreage = float(am.group(1))

                # Price: "$46,900 Cash Price"
                price = None
                pm = re.search(r"\$([\d,]+)\s*(?:Cash\s*Price)?", card_text)
                if pm:
                    price = _parse_price(pm.group(1))

                # State from title or context
                state = _extract_state_from_text(name)
                if not state and state_slug != "all":
                    state = _slug_to_state(state_slug)
                if states_filter and state and state.lower() not in states_filter:
                    continue

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    src = img.get("src") or img.get("data-src") or ""
                    if src and not src.startswith("data:"):
                        img_url = src

                listing_hash = _hash(f"elegment:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "elegmentland",
                    "source_name": "Elegment Land",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": "",
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = idx + 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Elegment scrape error ({state_slug}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = idx + 1

    return count


async def _scrape_detail_elegmentland(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Elegment Land property detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Monthly payment
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Down payment
        dp_m = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp_m:
            listing["down_payment"] = _parse_price(dp_m.group(1))

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # Description
        desc = soup.find("div", class_=re.compile(r"product.*description|entry-content|woocommerce-product-details", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"Elegment detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LAND EQUITIES — https://landequities.com/{state}
# ─────────────────────────────────────────────────────────────────────────

LANDEQUITIES_STATES = [
    "arizona", "california", "colorado", "hawaii", "nevada",
    "new-mexico", "oregon", "texas", "other-states",
]


async def _scrape_landequities(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandEquities.com — Squarespace, per-state pages."""
    col = db[COL_LISTINGS]
    count = 0

    states = LANDEQUITIES_STATES
    if states_filter:
        states = [s for s in LANDEQUITIES_STATES
                  if _slug_to_state(s).lower() in states_filter or s == "other-states"]

    _scrape_progress["states_total"] = len(states)
    _scrape_progress["states_done"] = 0

    for idx, state_slug in enumerate(states):
        url = f"https://landequities.com/{state_slug}"
        state_name = _slug_to_state(state_slug)
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp:
                _scrape_progress["states_done"] = idx + 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Links to individual property pages: /oregon/326374 etc
            links = soup.find_all("a", href=re.compile(rf"/{re.escape(state_slug)}/[\w-]+$"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)

                if href.startswith("/"):
                    href = f"https://landequities.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 10:
                    continue
                # Skip non-property links
                if name.lower() in ("home", "contact", "about", "faq", "sign me up!", "sold"):
                    continue

                card = link
                for _ in range(4):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Price: "Sale Price:$12,995.00"
                price = None
                pm = re.search(r"Sale\s*Price\s*:\s*\$([\d,]+\.?\d*)", card_text, re.I)
                if pm:
                    price = _parse_price(pm.group(1))

                # Original price
                orig_price = None
                op = re.search(r"Original\s*Price\s*:\s*\$([\d,]+\.?\d*)", card_text, re.I)
                if op:
                    orig_price = _parse_price(op.group(1))

                # Extract acreage from name
                acreage = None
                am = re.search(r"([\d.]+)\s*ACRES?", name, re.I)
                if am:
                    acreage = float(am.group(1))

                # Extract city from name: often "... LOT #X SOME ST. CITY, STATE"
                # State from URL slug
                state = state_name if state_slug != "other-states" else _extract_state_from_text(name)
                if states_filter and state and state.lower() not in states_filter:
                    continue

                # Check SOLD / AVAILABLE status
                is_sold = "SOLD" in card_text.upper() and "AVAILABLE" not in card_text.upper()
                if is_sold:
                    continue  # Skip sold

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    src = img.get("src") or img.get("data-src") or ""
                    if src and not src.startswith("data:"):
                        img_url = src

                listing_hash = _hash(f"landequities:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "landequities",
                    "source_name": "Land Equities",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": "",
                    "acreage": acreage,
                    "price": price,
                    "original_price": orig_price,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": True,
                    "land_type": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = idx + 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"LandEquities scrape error ({state_slug}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = idx + 1

    return count


async def _scrape_detail_landequities(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Land Equities property detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Monthly payment
        mp_m = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp_m:
            listing["monthly_payment"] = _parse_price(mp_m.group(1))

        # Description
        desc = soup.find("div", class_=re.compile(r"sqs-block-content|entry-content", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandEquities detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# YOURCHEAPLAND — https://yourcheapland.com/land-for-sale/
# ─────────────────────────────────────────────────────────────────────────

YOURCHEAPLAND_STATES = [
    ("arizona", "5"), ("colorado", "9"), ("florida", "10"),
    ("new-mexico", "1"), ("oklahoma", "2"), ("texas", "4"), ("utah", "7"),
]


async def _scrape_yourcheapland(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape YourCheapLand.com — state pages + subdivisions."""
    col = db[COL_LISTINGS]
    count = 0

    states = YOURCHEAPLAND_STATES
    if states_filter:
        states = [(s, i) for s, i in YOURCHEAPLAND_STATES
                  if _slug_to_state(s).lower() in states_filter]

    # Also scrape main land-for-sale page
    urls = [("all", "https://yourcheapland.com/land-for-sale/")]
    for s, sid in states:
        urls.append((s, f"https://yourcheapland.com/state/{s}/{sid}/"))

    _scrape_progress["states_total"] = len(urls)
    _scrape_progress["states_done"] = 0

    for idx, (state_slug, page_url) in enumerate(urls):
        try:
            resp = await _fetch_with_retry(client, page_url)
            if not resp:
                _scrape_progress["states_done"] = idx + 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Property links: /subdivision/{name}/lot/{id} or /subdivision/{name}/{id}
            links = soup.find_all("a", href=re.compile(r"/subdivision/"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)

                if href.startswith("/"):
                    href = f"https://yourcheapland.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 5:
                    continue
                if name.lower() in ("more property details »", "view properties »", "see more info"):
                    # Try parent text  
                    parent_name = link.parent.get_text(strip=True) if link.parent else ""
                    if len(parent_name) > 10 and "$" not in parent_name[:5]:
                        name = parent_name[:200]
                    else:
                        continue

                card = link
                for _ in range(5):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Acreage
                acreage = None
                am = re.search(r"([\d.]+)\s*(?:Acres?|Ac\b)", card_text, re.I)
                if am:
                    acreage = float(am.group(1))

                # Price
                price = None
                pm = re.search(r"\$([\d,]+\.?\d*)", card_text)
                if pm:
                    price = _parse_price(pm.group(1))

                # Monthly payment: $227.96/Month
                monthly = None
                mm = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:Month|mo)", card_text, re.I)
                if mm:
                    monthly = _parse_price(mm.group(1))

                # State
                state = _slug_to_state(state_slug) if state_slug != "all" else ""
                if not state:
                    state = _extract_state_from_text(card_text)
                if states_filter and state and state.lower() not in states_filter:
                    continue

                listing_hash = _hash(f"ycl:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "yourcheapland",
                    "source_name": "YourCheapLand",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": "",
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": monthly,
                    "financing_available": True,
                    "land_type": None,
                    "image_url": None,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = idx + 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"YourCheapLand scrape error ({state_slug}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = idx + 1

    return count


async def _scrape_detail_yourcheapland(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape YourCheapLand property detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Cash price
        cp = re.search(r"Cash\s*Price\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if cp:
            listing["price"] = _parse_price(cp.group(1))

        # Down payment
        dp = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp:
            listing["down_payment"] = _parse_price(dp.group(1))

        # Monthly
        mp = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp:
            listing["monthly_payment"] = _parse_price(mp.group(1))

        # County
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # Description
        desc = soup.find("div", class_=re.compile(r"property.*detail|content|description", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]

        # Acreage (backup)
        if not listing.get("acreage"):
            am = re.search(r"([\d.]+)\s*Acres?", text, re.I)
            if am:
                listing["acreage"] = float(am.group(1))

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"YourCheapLand detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# TERRA PRIME LOTS — https://www.terraprimelots.com/en/properties
# ─────────────────────────────────────────────────────────────────────────


async def _scrape_terraprimelots(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape TerraPrimeLots.com — single properties page."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = 1
    _scrape_progress["states_done"] = 0

    try:
        resp = await _fetch_with_retry(client, "https://www.terraprimelots.com/en/properties")
        if not resp:
            _scrape_progress["errors"] += 1
            return 0

        soup = BeautifulSoup(resp.text, "html.parser")

        # Property links: /en/properties/{slug}
        links = soup.find_all("a", href=re.compile(r"/en/properties/[\w-]+"))
        seen = set()

        for link in links:
            href = link.get("href", "")
            clean = href.split("?")[0].rstrip("/")
            if not href or clean in seen or clean.endswith("/properties"):
                continue
            seen.add(clean)

            if href.startswith("/"):
                href = f"https://www.terraprimelots.com{href}"

            # Card text — walk up
            card = link
            for _ in range(5):
                if card.parent:
                    card = card.parent
                else:
                    break
            card_text = card.get_text(" ", strip=True)

            name = ""
            # Extract meaningful name from card text
            nm = re.search(r"([\d.]+\s*Acres?\s+in\s+.+?)(?:AVAILABLE|STARTING|Land Use|$)", card_text, re.I)
            if nm:
                name = nm.group(1).strip()
            if not name:
                nm2 = re.search(r"(Affordable .+?)(?:AVAILABLE|STARTING|$)", card_text, re.I)
                if nm2:
                    name = nm2.group(1).strip()
            if not name:
                name = link.get_text(strip=True)
            if not name or len(name) < 5 or name.lower() == "view details":
                continue

            # Acreage
            acreage = None
            am = re.search(r"([\d.]+)\s*(?:-?\s*)?Acres?", card_text, re.I)
            if am:
                acreage = float(am.group(1))

            # Cash price: "$7,900cash"
            price = None
            pm = re.search(r"\$([\d,]+)\s*cash", card_text, re.I)
            if pm:
                price = _parse_price(pm.group(1))

            # Monthly: "STARTING AT $149 /month"
            monthly = None
            mm = re.search(r"\$([\d,]+)\s*/\s*month", card_text, re.I)
            if mm:
                monthly = _parse_price(mm.group(1))

            # State and county from text: "Highlands County, FL"
            state = ""
            county = ""
            loc_m = re.search(r"([\w\s]+?)\s*County,\s*([A-Z]{2})", card_text)
            if loc_m:
                county = loc_m.group(1).strip()
                st_abbr = loc_m.group(2)
                state = STATE_ABBREVS.get(st_abbr, st_abbr)

            if not state:
                state = _extract_state_from_text(card_text)
            if states_filter and state and state.lower() not in states_filter:
                continue

            listing_hash = _hash(f"terraprime:{clean}")
            fresh = {
                "hash": listing_hash,
                "source": "terraprimelots",
                "source_name": "Terra Prime Lots",
                "name": name[:200],
                "url": href,
                "property_id": "",
                "state": state,
                "county": county,
                "acreage": acreage,
                "price": price,
                "original_price": None,
                "down_payment": None,
                "monthly_payment": monthly,
                "financing_available": True,
                "land_type": None,
                "image_url": None,
                "description": "",
                "is_foreclosure": False,
            }
            await _smart_upsert(col, listing_hash, fresh)
            count += 1
            _scrape_progress["listings_found"] = count

        _scrape_progress["states_done"] = 1
    except Exception as e:
        logger.error(f"TerraPrimeLots scrape error: {e}")
        _scrape_progress["errors"] += 1

    return count


async def _scrape_detail_terraprimelots(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Terra Prime Lots property detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Cash price
        cp = re.search(r"\$([\d,]+)\s*cash", text, re.I)
        if cp:
            listing["price"] = _parse_price(cp.group(1))

        # Down payment
        dp = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp:
            listing["down_payment"] = _parse_price(dp.group(1))

        # Monthly
        mp = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp:
            listing["monthly_payment"] = _parse_price(mp.group(1))

        # Zoning / land use
        zm = re.search(r"(?:Land\s*Use|Zoning)\s*[:=]?\s*([^.\n<]+)", text, re.I)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        # Road access
        if re.search(r"Road\s*Access", text, re.I):
            listing["road_access"] = "Yes"

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"TerraPrimeLots detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# RAW ESTATE ENTERPRISE — https://www.rawestateenterprise.com/store-2
# ─────────────────────────────────────────────────────────────────────────


async def _scrape_rawestate(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape RawEstateEnterprise.com — Wix product pages."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = 1
    _scrape_progress["states_done"] = 0

    for page_url in [
        "https://www.rawestateenterprise.com/",
        "https://www.rawestateenterprise.com/store-2",
    ]:
        try:
            resp = await _fetch_with_retry(client, page_url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Product links: /product-page/{slug}
            links = soup.find_all("a", href=re.compile(r"/product-page/"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)

                if href.startswith("/"):
                    href = f"https://www.rawestateenterprise.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 8:
                    continue
                # Skip buttons
                if name.lower() in ("reserve now", "buy now", "add to cart", "recently sold"):
                    continue

                card = link
                for _ in range(4):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Title pattern: "4.64-acre $11,000 ($389 Initial Payment) - Apache County, Arizona near Sanders"
                # Acreage
                acreage = None
                am = re.search(r"([\d.]+)\s*-?\s*acres?", name, re.I)
                if am:
                    acreage = float(am.group(1))

                # Price from title: "$11,000"
                price = None
                pm = re.search(r"\$([\d,]+)\s", name)
                if pm:
                    price = _parse_price(pm.group(1))

                # Monthly: "$190/month"
                monthly = None
                mm = re.search(r"\$([\d,]+)\s*/\s*month", card_text, re.I)
                if mm:
                    monthly = _parse_price(mm.group(1))

                # Initial Payment (=down)
                down = None
                ip = re.search(r"\$([\d,]+)\s*Initial\s*Payment", name, re.I)
                if ip:
                    down = _parse_price(ip.group(1))

                # State and county from title
                state = _extract_state_from_text(name)
                county = ""
                cm = re.search(r"([\w\s]+?)\s*County", name)
                if cm:
                    county = cm.group(1).strip()

                if states_filter and state and state.lower() not in states_filter:
                    continue

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    src = img.get("src") or ""
                    if src and not src.startswith("data:"):
                        img_url = src

                # Price from card (Wix shows Price $xxx.00 which is the initial payment, not total)
                # Use the price from title if available
                wix_price = None
                wp = re.search(r"Price\s*\$([\d,]+\.?\d*)", card_text)
                if wp:
                    wix_price = _parse_price(wp.group(1))
                if not price and not down and wix_price:
                    down = wix_price

                listing_hash = _hash(f"rawestate:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "rawestate",
                    "source_name": "Raw Estate Enterprise",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": county,
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": down,
                    "monthly_payment": monthly,
                    "financing_available": True,
                    "land_type": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"RawEstate scrape error: {e}")
            _scrape_progress["errors"] += 1

    _scrape_progress["states_done"] = 1
    return count


async def _scrape_detail_rawestate(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Raw Estate Enterprise product detail page."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Description
        desc = soup.find("div", class_=re.compile(r"product.*description|rich-content", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"RawEstate detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LAND LIMITED — https://landlimited.com/properties/state/{ST}
# ─────────────────────────────────────────────────────────────────────────

LANDLIMITED_STATES_ABBR = [
    "AZ", "AR", "CA", "CO", "FL", "GA", "HI", "ID", "KY",
    "MI", "MO", "MT", "NV", "NM", "NC", "OH", "OK", "OR",
    "SC", "TN", "TX", "UT", "VA", "WA", "WV", "WI", "WY",
]


async def _scrape_landlimited(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandLimited.com — per-state listing pages."""
    col = db[COL_LISTINGS]
    count = 0

    st_list = LANDLIMITED_STATES_ABBR
    if states_filter:
        st_list = [ab for ab in LANDLIMITED_STATES_ABBR
                   if STATE_ABBREVS.get(ab, "").lower() in states_filter]

    _scrape_progress["states_total"] = len(st_list)
    _scrape_progress["states_done"] = 0

    for idx, abbr in enumerate(st_list):
        state_name = STATE_ABBREVS.get(abbr, abbr)
        url = f"https://landlimited.com/properties/state/{abbr}"
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp:
                _scrape_progress["states_done"] = idx + 1
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Property links: /properties/{slug} or /properties/detail/{id}
            links = soup.find_all("a", href=re.compile(r"/properties/(?!state|all)[\w-]+"))
            seen = set()

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)

                if href.startswith("/"):
                    href = f"https://landlimited.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 5:
                    continue
                if name.lower() in ("view all", "see more", "buy", "search"):
                    continue

                card = link
                for _ in range(5):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Acreage
                acreage = None
                am = re.search(r"([\d.]+)\s*(?:Acres?|Ac\b)", card_text, re.I)
                if am:
                    acreage = float(am.group(1))

                # Price
                price = None
                pm = re.search(r"\$([\d,]+\.?\d*)", card_text)
                if pm:
                    price = _parse_price(pm.group(1))

                # Monthly
                monthly = None
                mm = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", card_text, re.I)
                if mm:
                    monthly = _parse_price(mm.group(1))

                # County
                county = ""
                cm = re.search(r"([\w\s]+?)\s*County", card_text)
                if cm:
                    county = cm.group(1).strip()

                # Image
                img = card.find("img")
                img_url = None
                if img:
                    src = img.get("src") or img.get("data-src") or ""
                    if src and not src.startswith("data:"):
                        img_url = src

                listing_hash = _hash(f"landlimited:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "landlimited",
                    "source_name": "Land Limited",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state_name,
                    "county": county,
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": monthly,
                    "financing_available": True,
                    "land_type": None,
                    "image_url": img_url,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = idx + 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"LandLimited scrape error ({abbr}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = idx + 1

    return count


async def _scrape_detail_landlimited(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Land Limited property detail page."""
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
        dp = re.search(r"(?:down\s*(?:payment)?)\s*[:=]?\s*\$([\d,]+\.?\d*)", text, re.I)
        if dp:
            listing["down_payment"] = _parse_price(dp.group(1))

        # Monthly
        mp = re.search(r"\$([\d,]+\.?\d*)\s*/\s*(?:mo|month)", text, re.I)
        if mp:
            listing["monthly_payment"] = _parse_price(mp.group(1))

        # Description
        desc = soup.find("div", class_=re.compile(r"description|detail|content", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandLimited detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LANDANDFARM — https://www.landandfarm.com/search/cheap-land-for-sale/
# ─────────────────────────────────────────────────────────────────────────

LANDANDFARM_MAX_PAGES = 10  # 20 listings per page


async def _scrape_landandfarm(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandAndFarm.com — major marketplace, server-rendered pages.

    Uses curl_cffi with Safari impersonation to bypass bot protection.
    The httpx client parameter is unused (kept for interface compatibility).
    """
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = LANDANDFARM_MAX_PAGES
    _scrape_progress["states_done"] = 0

    async with CffiSession(impersonate="safari17_2_ios") as session:
      for page in range(1, LANDANDFARM_MAX_PAGES + 1):
        if _scrape_stop_requested:
            break
        url = f"https://www.landandfarm.com/search/cheap-land-for-sale/page-{page}/" if page > 1 else "https://www.landandfarm.com/search/cheap-land-for-sale/"
        try:
            resp = await session.get(url, timeout=30)
            if resp.status_code != 200:
                logger.warning(f"LandAndFarm HTTP {resp.status_code} for {url}")
                _scrape_progress["states_done"] = page
                continue
            if len(resp.text) < 2000:
                _scrape_progress["states_done"] = page
                break

            soup = BeautifulSoup(resp.text, "html.parser")

            # Property links: /property/{slug}/
            links = soup.find_all("a", href=re.compile(r"/property/[\w-]+-\d+/$"))
            seen = set()
            found_any = False

            for link in links:
                href = link.get("href", "")
                clean = href.split("?")[0].rstrip("/")
                if not href or clean in seen:
                    continue
                seen.add(clean)
                found_any = True

                if href.startswith("/"):
                    href = f"https://www.landandfarm.com{href}"

                name = link.get_text(strip=True)
                if not name or len(name) < 3:
                    continue
                # Skip nav links
                if name.lower() in ("listing details page", "contact", "more"):
                    continue

                card = link
                for _ in range(6):
                    if card.parent:
                        card = card.parent
                    else:
                        break
                card_text = card.get_text(" ", strip=True)

                # Price and acreage: "$6,944 2 Acres"
                price = None
                acreage = None
                pa = re.search(r"\$([\d,]+)\s+([\d.]+)\s*Acres?", card_text, re.I)
                if pa:
                    price = _parse_price(pa.group(1))
                    acreage = float(pa.group(2))
                else:
                    pm = re.search(r"\$([\d,]+)", card_text)
                    if pm:
                        price = _parse_price(pm.group(1))
                    am = re.search(r"([\d.]+)\s*Acres?", card_text, re.I)
                    if am:
                        acreage = float(am.group(1))

                # Location: city, state, zip, county
                state = ""
                county = ""
                # Pattern: "City, ST, XXXXX, County" or "City, ST, County"
                loc_m = re.search(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Z]{2}),?\s*\d*,?\s*([\w\s]*County)?", card_text)
                if loc_m:
                    state = STATE_ABBREVS.get(loc_m.group(2), loc_m.group(2))
                    if loc_m.group(3):
                        county = loc_m.group(3).replace("County", "").strip()
                if not state:
                    state = _extract_state_from_text(card_text)

                if states_filter and state and state.lower() not in states_filter:
                    continue

                listing_hash = _hash(f"landandfarm:{clean}")
                fresh = {
                    "hash": listing_hash,
                    "source": "landandfarm",
                    "source_name": "LandAndFarm",
                    "name": name[:200],
                    "url": href,
                    "property_id": "",
                    "state": state,
                    "county": county,
                    "acreage": acreage,
                    "price": price,
                    "original_price": None,
                    "down_payment": None,
                    "monthly_payment": None,
                    "financing_available": None,
                    "land_type": None,
                    "image_url": None,
                    "description": "",
                    "is_foreclosure": False,
                }
                await _smart_upsert(col, listing_hash, fresh)
                count += 1
                _scrape_progress["listings_found"] = count

            _scrape_progress["states_done"] = page

            if not found_any:
                break

            await asyncio.sleep(1.0)  # Be polite to larger platforms
        except Exception as e:
            logger.error(f"LandAndFarm scrape error (page {page}): {e}")
            _scrape_progress["errors"] += 1
            _scrape_progress["states_done"] = page

    return count


async def _scrape_detail_landandfarm(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape LandAndFarm property detail page.

    Uses curl_cffi to bypass bot protection.
    """
    url = listing.get("url")
    if not url:
        return listing
    try:
        async with CffiSession(impersonate="safari17_2_ios") as session:
            resp = await session.get(url, timeout=30)
            if resp.status_code != 200:
                return listing
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)

        # Description
        desc = soup.find("div", class_=re.compile(r"description|detail|listing-content", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"
        elif re.search(r"hoa\s*(?:fee|dues)", text, re.I):
            listing["hoa"] = "yes"

        # County (backup)
        cm = re.search(r"([\w\s]+?)\s*County", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandAndFarm detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LANDSEARCH — https://www.landsearch.com/properties/washington
# ─────────────────────────────────────────────────────────────────────────

LANDSEARCH_STATES = [
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

LANDSEARCH_MAX_PAGES = 10  # pages per state


async def _scrape_landsearch(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandSearch.com — large listing aggregator with state-based pages.

    Uses curl_cffi with Safari impersonation to bypass Cloudflare protection.
    The httpx client parameter is unused (kept for interface compatibility).
    """
    col = db[COL_LISTINGS]
    count = 0

    states = LANDSEARCH_STATES
    if states_filter:
        states = [s for s in LANDSEARCH_STATES if _slug_to_state(s).lower() in states_filter]

    _scrape_progress["states_total"] = len(states)
    _scrape_progress["states_done"] = 0

    async with CffiSession(impersonate="safari17_2_ios") as session:
      for si, state_slug in enumerate(states):
        for page in range(1, LANDSEARCH_MAX_PAGES + 1):
            if _scrape_stop_requested:
                break
            if page == 1:
                url = f"https://www.landsearch.com/properties/{state_slug}"
            else:
                url = f"https://www.landsearch.com/properties/{state_slug}/p{page}"
            try:
                resp = await session.get(url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"LandSearch HTTP {resp.status_code} for {url}")
                    break
                if len(resp.text) < 2000:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Property links: /properties/{address-slug}/{id}
                links = soup.find_all("a", href=re.compile(r"/properties/[^/]+/\d+$"))
                seen = set()
                found_any = False

                for link in links:
                    href = link.get("href", "")
                    clean = href.split("?")[0].rstrip("/")
                    if not href or clean in seen:
                        continue
                    seen.add(clean)
                    found_any = True

                    full_url = f"https://www.landsearch.com{href}" if href.startswith("/") else href

                    # Name from link text; fallback to URL slug (links may be image-only)
                    name = link.get_text(strip=True)
                    if not name or len(name) < 5:
                        slug_m = re.search(r"/properties/([^/]+)/\d+", href)
                        if slug_m:
                            name = _slug_to_state(slug_m.group(1))  # converts dashes to title case
                        else:
                            name = href.split("/")[-2] if "/" in href else href
                    if not name:
                        continue

                    # Walk up to find card container
                    card = link
                    for _ in range(6):
                        if card.parent:
                            card = card.parent
                        else:
                            break
                    card_text = card.get_text(" ", strip=True)

                    # Extract price: $174,999
                    price = None
                    pm = re.search(r"\$([\d,]+(?:\.\d+)?)", card_text)
                    if pm:
                        price = _parse_price(pm.group(1))
                    # Skip lease listings
                    if "/mo" in card_text.lower() and not price:
                        continue

                    # Extract acreage: "101 acres" or "0.3 acres"
                    acreage = None
                    am = re.search(r"([\d,.]+)\s*acres?", card_text, re.I)
                    if am:
                        acreage = float(am.group(1).replace(",", ""))

                    # Extract county: "Okanogan County"
                    county = ""
                    cm = re.search(r"([\w\s]+?)\s*County", card_text)
                    if cm:
                        county = cm.group(1).strip()

                    # Extract state: "WA 98855" or state from slug
                    state = _slug_to_state(state_slug)

                    listing_hash = _hash(f"landsearch:{clean}")
                    fresh = {
                        "hash": listing_hash,
                        "source": "landsearch",
                        "source_name": "LandSearch",
                        "name": name[:200],
                        "url": full_url,
                        "property_id": "",
                        "state": state,
                        "county": county,
                        "acreage": acreage,
                        "price": price,
                        "original_price": None,
                        "down_payment": None,
                        "monthly_payment": None,
                        "financing_available": None,
                        "land_type": None,
                        "image_url": None,
                        "description": "",
                        "is_foreclosure": False,
                    }
                    await _smart_upsert(col, listing_hash, fresh)
                    count += 1
                    _scrape_progress["listings_found"] = count

                if not found_any:
                    break
                await asyncio.sleep(0.8)
            except Exception as e:
                logger.error(f"LandSearch scrape error ({state_slug} p{page}): {e}")
                _scrape_progress["errors"] += 1

        _scrape_progress["states_done"] = si + 1
    return count


async def _scrape_detail_landsearch(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape LandSearch.com property detail page.

    Uses curl_cffi to bypass Cloudflare protection.
    """
    url = listing.get("url")
    if not url:
        return listing
    try:
        async with CffiSession(impersonate="safari17_2_ios") as session:
            resp = await session.get(url, timeout=30)
            if resp.status_code != 200:
                return listing
            soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Description
        desc_div = soup.find("div", class_=re.compile(r"description|detail|listing-content", re.I))
        if desc_div:
            listing["description"] = desc_div.get_text(" ", strip=True)[:2000]
        elif not listing.get("description"):
            # Fallback: find large text blocks
            for p in soup.find_all("p"):
                pt = p.get_text(strip=True)
                if len(pt) > 100:
                    listing["description"] = pt[:2000]
                    break

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"
        elif re.search(r"hoa\s*(?:fee|dues|:)", text, re.I):
            listing["hoa"] = "yes"

        # Acreage backup
        if not listing.get("acreage"):
            am = re.search(r"([\d,.]+)\s*acres?", text, re.I)
            if am:
                listing["acreage"] = float(am.group(1).replace(",", ""))

        # County backup
        if not listing.get("county"):
            cm = re.search(r"([\w\s]+?)\s*County", text)
            if cm:
                listing["county"] = cm.group(1).strip()

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandSearch detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LANDWATCH — https://www.landwatch.com/<state>-land-for-sale
# ─────────────────────────────────────────────────────────────────────────

LANDWATCH_STATES = [
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

LANDWATCH_MAX_PAGES = 5  # pages per state


async def _scrape_landwatch(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape LandWatch.com — major land marketplace with thousands of listings.

    Uses curl_cffi with Safari impersonation to bypass bot protection.
    The httpx client parameter is unused (kept for interface compatibility).
    """
    col = db[COL_LISTINGS]
    count = 0

    states = LANDWATCH_STATES
    if states_filter:
        states = [s for s in LANDWATCH_STATES if _slug_to_state(s).lower() in states_filter]

    _scrape_progress["states_total"] = len(states)
    _scrape_progress["states_done"] = 0

    async with CffiSession(impersonate="safari17_2_ios") as session:
      for si, state_slug in enumerate(states):
        for page in range(1, LANDWATCH_MAX_PAGES + 1):
            if _scrape_stop_requested:
                break
            # LandWatch URL: /washington-land-for-sale, page param
            if page == 1:
                url = f"https://www.landwatch.com/{state_slug}-land-for-sale"
            else:
                url = f"https://www.landwatch.com/{state_slug}-land-for-sale?page={page}"
            try:
                resp = await session.get(url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"LandWatch HTTP {resp.status_code} for {url}")
                    break
                if len(resp.text) < 2000:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Property links: /county-state-type-for-sale/pid/{id}
                links = soup.find_all("a", href=re.compile(r"/pid/\d+"))
                seen = set()
                found_any = False

                for link in links:
                    href = link.get("href", "")
                    clean = href.split("?")[0].rstrip("/")
                    if not href or clean in seen:
                        continue
                    seen.add(clean)
                    found_any = True

                    full_url = f"https://www.landwatch.com{href}" if href.startswith("/") else href

                    name = link.get_text(strip=True)
                    if not name or len(name) < 3:
                        continue
                    # Skip nav/control text
                    if name.lower() in ("listing details page", "contact", "map", "video", "videomap"):
                        continue

                    # Walk up to find card container
                    card = link
                    for _ in range(8):
                        if card.parent:
                            card = card.parent
                        else:
                            break
                    card_text = card.get_text(" ", strip=True)

                    # Price: "$3,335,000" or "$49,950"
                    price = None
                    pm = re.search(r"\$([\d,]+(?:\.\d+)?)", card_text)
                    if pm:
                        price = _parse_price(pm.group(1))

                    # Acreage: "390 Acres" or "2.03 Acres"
                    acreage = None
                    am = re.search(r"([\d,.]+)\s*Acres?", card_text, re.I)
                    if am:
                        acreage = float(am.group(1).replace(",", ""))

                    # County from URL slug or text
                    county = ""
                    # URL pattern: /ferry-county-washington-.../pid/...
                    county_m = re.search(r"/([\w-]+)-county-[\w-]+-[\w-]+-for-sale/pid/", href)
                    if county_m:
                        county = _slug_to_state(county_m.group(1))
                    if not county:
                        cm = re.search(r"([\w\s]+?)\s*County", card_text)
                        if cm:
                            county = cm.group(1).strip()

                    state = _slug_to_state(state_slug)

                    # Extract property id from pid
                    pid_m = re.search(r"/pid/(\d+)", href)
                    prop_id = pid_m.group(1) if pid_m else ""

                    listing_hash = _hash(f"landwatch:{prop_id or clean}")
                    fresh = {
                        "hash": listing_hash,
                        "source": "landwatch",
                        "source_name": "LandWatch",
                        "name": name[:200],
                        "url": full_url,
                        "property_id": prop_id,
                        "state": state,
                        "county": county,
                        "acreage": acreage,
                        "price": price,
                        "original_price": None,
                        "down_payment": None,
                        "monthly_payment": None,
                        "financing_available": None,
                        "land_type": None,
                        "image_url": None,
                        "description": "",
                        "is_foreclosure": False,
                    }
                    await _smart_upsert(col, listing_hash, fresh)
                    count += 1
                    _scrape_progress["listings_found"] = count

                if not found_any:
                    break
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"LandWatch scrape error ({state_slug} p{page}): {e}")
                _scrape_progress["errors"] += 1

        _scrape_progress["states_done"] = si + 1
    return count


async def _scrape_detail_landwatch(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape LandWatch.com property detail page.

    Uses curl_cffi to bypass bot protection.
    """
    url = listing.get("url")
    if not url:
        return listing
    try:
        async with CffiSession(impersonate="safari17_2_ios") as session:
            resp = await session.get(url, timeout=30)
            if resp.status_code != 200:
                return listing
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)

        # Description
        desc = soup.find("div", class_=re.compile(r"description|listing-detail|detail-content", re.I))
        if desc:
            listing["description"] = desc.get_text(" ", strip=True)[:2000]
        elif not listing.get("description"):
            for p in soup.find_all("p"):
                pt = p.get_text(strip=True)
                if len(pt) > 100:
                    listing["description"] = pt[:2000]
                    break

        # Zoning
        zm = re.search(r"[Zz]oning\s*[:=]?\s*([^.\n<]+)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        # HOA
        if "no hoa" in text.lower():
            listing["hoa"] = "no"
        elif re.search(r"hoa\s*(?:fee|dues|:)", text, re.I):
            listing["hoa"] = "yes"

        # County backup
        if not listing.get("county"):
            cm = re.search(r"([\w\s]+?)\s*County", text)
            if cm:
                listing["county"] = cm.group(1).strip()

        # Acreage backup
        if not listing.get("acreage"):
            am = re.search(r"([\d,.]+)\s*acres?", text, re.I)
            if am:
                listing["acreage"] = float(am.group(1).replace(",", ""))

        # Owner financing
        if re.search(r"owner\s*financ", text, re.I):
            listing["financing_available"] = True

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"LandWatch detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# HORIZON LAND SALES — https://horizonlandsales.com/
# ─────────────────────────────────────────────────────────────────────────


async def _scrape_horizonlandsales(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape HorizonLandSales.com — small inventory, deep-discount land."""
    col = db[COL_LISTINGS]
    count = 0

    _scrape_progress["states_total"] = 1
    _scrape_progress["states_done"] = 0

    # Scrape homepage which lists all featured properties
    url = "https://horizonlandsales.com/"
    try:
        resp = await _fetch_with_retry(client, url)
        if not resp:
            return count

        soup = BeautifulSoup(resp.text, "html.parser")

        # Property links: /property/{slug}/
        links = soup.find_all("a", href=re.compile(r"horizonlandsales\.com/property/[\w-]+"))
        seen = set()

        for link in links:
            href = link.get("href", "")
            clean = href.split("?")[0].rstrip("/")
            if not href or clean in seen:
                continue
            seen.add(clean)

            full_url = href if href.startswith("http") else f"https://horizonlandsales.com{href}"

            name = link.get_text(strip=True)
            if not name or len(name) < 5:
                continue
            if name.lower() in ("view", "reserve now", "see properties"):
                continue

            # Walk up for card context
            card = link
            for _ in range(6):
                if card.parent:
                    card = card.parent
                else:
                    break
            card_text = card.get_text(" ", strip=True)

            # Price: "$124997" (discounted) or "$249997"
            price = None
            pm = re.search(r"\$([\d,]+)", card_text)
            if pm:
                price = _parse_price(pm.group(1))

            # Original price (strikethrough): second price
            original_price = None
            prices = re.findall(r"\$([\d,]+)", card_text)
            if len(prices) >= 2:
                p1 = _parse_price(prices[0])
                p2 = _parse_price(prices[1])
                if p1 and p2 and p2 > p1:
                    price = p1
                    original_price = p2
                elif p1 and p2 and p1 > p2:
                    price = p2
                    original_price = p1

            # Acreage: "74.03 ACREAGE" or "7.47 ACREAGE"
            acreage = None
            am = re.search(r"([\d.]+)\s*(?:ACREAGE|acres?)", card_text, re.I)
            if am:
                acreage = float(am.group(1))

            # Location: "Lake County, MT LOCATION" or "Jefferson County, WA LOCATION"
            state = ""
            county = ""
            loc_m = re.search(r"([\w\s]+?)\s*County,\s*([A-Z]{2})", card_text)
            if loc_m:
                county = loc_m.group(1).strip()
                state = STATE_ABBREVS.get(loc_m.group(2), loc_m.group(2))

            # Also extract state from name: "... – Forks, WA"
            if not state:
                nm = re.search(r",\s*([A-Z]{2})\b", name)
                if nm:
                    state = STATE_ABBREVS.get(nm.group(1), nm.group(1))
            if not state:
                state = _extract_state_from_text(card_text)

            if states_filter and state and state.lower() not in states_filter:
                continue

            # Financing info from card
            monthly = None
            fm = re.search(r"\$([\d,]+)/mo", card_text)
            if fm:
                monthly = _parse_price(fm.group(1))

            down = None
            dm = re.search(r"\$([\d,]+)\s*down", card_text, re.I)
            if dm:
                down = _parse_price(dm.group(1))

            listing_hash = _hash(f"horizon:{clean}")
            fresh = {
                "hash": listing_hash,
                "source": "horizonlandsales",
                "source_name": "Horizon Land Sales",
                "name": name[:200],
                "url": full_url,
                "property_id": "",
                "state": state,
                "county": county,
                "acreage": acreage,
                "price": price,
                "original_price": original_price,
                "down_payment": down,
                "monthly_payment": monthly,
                "financing_available": True if monthly or down else None,
                "land_type": None,
                "image_url": None,
                "description": "",
                "is_foreclosure": False,
            }
            await _smart_upsert(col, listing_hash, fresh)
            count += 1
            _scrape_progress["listings_found"] = count

    except Exception as e:
        logger.error(f"HorizonLandSales scrape error: {e}")
        _scrape_progress["errors"] += 1

    _scrape_progress["states_done"] = 1
    return count


async def _scrape_detail_horizonlandsales(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape HorizonLandSales property detail page — rich property attributes."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        resp = await client.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200:
            return listing
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Description section
        desc_heading = soup.find(string=re.compile(r"Description", re.I))
        if desc_heading:
            desc_parent = desc_heading.find_parent()
            if desc_parent:
                # Get the next sibling or parent's text
                desc_section = desc_parent.find_next_sibling()
                if desc_section:
                    listing["description"] = desc_section.get_text(" ", strip=True)[:2000]
        if not listing.get("description"):
            for p in soup.find_all("p"):
                pt = p.get_text(strip=True)
                if len(pt) > 150:
                    listing["description"] = pt[:2000]
                    break

        # Property Attributes section
        # Zoning
        zm = re.search(r"Zoning\s*:\s*([^\n]+?)(?:\s*More info|$)", text)
        if zm:
            listing["zoning"] = zm.group(1).strip()[:200]

        # HOA
        hoa_m = re.search(r"HOA\s*:\s*(\w+)", text)
        if hoa_m:
            val = hoa_m.group(1).lower()
            listing["hoa"] = "no" if "none" in val or "no" in val else "yes"

        # County
        cm = re.search(r"County\s*:\s*([\w\s]+?)(?:,\s*[A-Z]{2})?(?:\s|$)", text)
        if cm and not listing.get("county"):
            listing["county"] = cm.group(1).strip()

        # Parcel number
        pn = re.search(r"Parcel\s*(?:Number)?\s*:\s*([\w-]+)", text)
        if pn:
            listing["property_id"] = pn.group(1).strip()

        # Taxes
        tax_m = re.search(r"Taxes?\s*:\s*(?:Approx\.?\s*)?\$([\d,]+)", text)
        if tax_m:
            pass  # Could store if needed

        # Cash price
        cp = re.search(r"Cash\s*Price\s*(?:Discount)?\s*\$?([\d,]+)", text)
        if cp:
            p = _parse_price(cp.group(1))
            if p and (not listing.get("price") or p < listing["price"]):
                listing["price"] = p

        # Finance terms: "$X down" and "$Y/mo for Z months"
        dp = re.search(r"Finance.*?\$([\d,]+)\s*down", text, re.I)
        if dp:
            listing["down_payment"] = _parse_price(dp.group(1))
            listing["financing_available"] = True

        mp = re.search(r"\$([\d,]+)/mo\s*for\s*(\d+)\s*months", text)
        if mp:
            listing["monthly_payment"] = _parse_price(mp.group(1))
            listing["financing_available"] = True

        # Mobile homes
        mob = re.search(r"Mobile\s*Homes?\s*Allowed\s*:\s*(\w+)", text, re.I)
        if mob and "yes" in mob.group(1).lower():
            listing["land_type"] = "Mobile Home OK"

        listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"HorizonLandSales detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# HOMES.COM — https://www.homes.com/{state}/land-for-sale/p{page}/?price-max=X
# Uses curl_cffi to bypass Akamai bot protection (TLS fingerprint impersonation)
# ─────────────────────────────────────────────────────────────────────────

HOMESCOM_STATES = [
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

HOMESCOM_MAX_PAGES = 15  # 40 per page, up to 15 pages = ~600 listings


async def _scrape_homescom(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape Homes.com — major real estate portal, land & lots.

    Uses curl_cffi with Safari impersonation to bypass Akamai bot protection.
    The httpx client parameter is unused (kept for interface compatibility).
    """
    col = db[COL_LISTINGS]
    count = 0
    filters = await _get_filter_settings(db)
    max_price = int(filters["max_price"]) if filters["max_price"] < 999999999 else 50000

    states = HOMESCOM_STATES
    if states_filter:
        states = [s for s in HOMESCOM_STATES if _slug_to_state(s).lower() in states_filter]

    _scrape_progress["states_total"] = len(states)
    _scrape_progress["states_done"] = 0

    async with CffiSession(impersonate="safari17_2_ios") as session:
        for si, state_slug in enumerate(states):
            if _scrape_stop_requested:
                break

            for page in range(1, HOMESCOM_MAX_PAGES + 1):
                if _scrape_stop_requested:
                    break

                if page == 1:
                    url = f"https://www.homes.com/{state_slug}/land-for-sale/?price-max={max_price}"
                else:
                    url = f"https://www.homes.com/{state_slug}/land-for-sale/p{page}/?price-max={max_price}"

                try:
                    resp = await session.get(url, timeout=30)
                    if resp.status_code != 200:
                        logger.warning(f"Homes.com HTTP {resp.status_code} for {url}")
                        break
                    if len(resp.text) < 2000:
                        break

                    soup = BeautifulSoup(resp.text, "html.parser")
                    articles = soup.find_all("article", class_=re.compile(r"placard"))
                    if not articles:
                        break

                    page_new = 0
                    for article in articles:
                        try:
                            # Property link — first link with /property/ href
                            prop_link = article.find("a", href=re.compile(r"/property/[^/]+/[^/]+/"))
                            if not prop_link:
                                continue

                            href = prop_link.get("href", "")
                            full_url = f"https://www.homes.com{href}" if not href.startswith("http") else href
                            clean_url = full_url.split("?")[0].rstrip("/")

                            # Property ID from data-pk attribute
                            property_id = article.get("data-pk", "")

                            # Address from link title/aria-label
                            address = prop_link.get("title", "") or prop_link.get("aria-label", "")

                            # Image: first img with data-image attribute
                            image_url = None
                            img = article.find("img", attrs={"data-image": True})
                            if img:
                                image_url = img.get("data-image", "")

                            # Parse card text for price, acreage, etc.
                            card_text = article.get_text(" ", strip=True)

                            # Price: first "$XX,XXX" in text
                            price = None
                            pm = re.search(r"\$([\d,]+)", card_text)
                            if pm:
                                price = _parse_price(pm.group(1))

                            # Acreage: "X.XX Acre(s)"
                            acreage = None
                            am = re.search(r"([\d.]+)\s*Acres?", card_text, re.I)
                            if am:
                                acreage = float(am.group(1))

                            # State from address (e.g., "... Ocean Park, WA 98640")
                            state = _slug_to_state(state_slug)
                            county = ""

                            # Try to get county from address parsing
                            # Address format: "3507 102nd St, Ocean Park, WA 98640"
                            state_abbr = ""
                            addr_m = re.search(r",\s*([A-Z]{2})\s+\d{5}", address)
                            if addr_m:
                                state_abbr = addr_m.group(1)
                                state = STATE_ABBREVS.get(state_abbr, state)

                            # Build name from address or card text
                            name = address if address else card_text[:150]

                            if not price:
                                continue

                            listing_hash = _hash(f"homescom:{clean_url}")
                            fresh = {
                                "hash": listing_hash,
                                "source": "homescom",
                                "source_name": "Homes.com",
                                "name": name[:200],
                                "url": full_url,
                                "property_id": property_id,
                                "state": state,
                                "county": county,
                                "acreage": acreage,
                                "price": price,
                                "original_price": None,
                                "down_payment": None,
                                "monthly_payment": None,
                                "financing_available": None,
                                "land_type": "Land",
                                "image_url": image_url,
                                "description": "",
                                "is_foreclosure": False,
                            }

                            if not _matches_filters(fresh, filters):
                                continue

                            inserted = await _smart_upsert(col, listing_hash, fresh)
                            count += 1
                            if inserted:
                                page_new += 1
                            _scrape_progress["listings_found"] = count

                        except Exception as e:
                            logger.debug(f"Homes.com card parse error: {e}")
                            continue

                    # If no new listings were found on this page, stop paginating
                    if _scrape_mode == "new_only" and page_new == 0 and page > 1:
                        break

                except Exception as e:
                    logger.error(f"Homes.com page error {url}: {e}")
                    _scrape_progress["errors"] += 1
                    break

                await asyncio.sleep(1.0)  # Throttle between pages

            _scrape_progress["states_done"] = si + 1

    return count


async def _scrape_detail_homescom(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Homes.com property detail page for description, lot size, zoning."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        async with CffiSession(impersonate="safari17_2_ios") as session:
            resp = await session.get(url, timeout=30)
            if resp.status_code != 200:
                return listing
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Description — look for property description sections
            desc = ""
            for sel in [
                soup.find(class_=re.compile(r"description|details-desc|property-desc", re.I)),
                soup.find("div", class_=re.compile(r"listing-description", re.I)),
            ]:
                if sel:
                    desc = sel.get_text(" ", strip=True)
                    break
            if not desc:
                # Fallback: longest paragraph
                for p in soup.find_all("p"):
                    pt = p.get_text(strip=True)
                    if len(pt) > len(desc):
                        desc = pt
            if desc:
                listing["description"] = desc[:2000]

            # Lot size
            lm = re.search(r"Lot\s*Size[:\s]*([\d.,]+)\s*(acre|sqft|sq\s*ft)", text, re.I)
            if lm:
                val = float(lm.group(1).replace(",", ""))
                unit = lm.group(2).lower()
                if "acre" in unit:
                    listing["acreage"] = val
                elif val > 0:
                    listing["acreage"] = round(val / 43560, 2)  # sqft to acres

            # Zoning
            zm = re.search(r"Zoning[:\s]*([^\n.]{3,100})", text, re.I)
            if zm:
                listing["zoning"] = _normalize_zoning(zm.group(1).strip())

            # County
            cm = re.search(r"County[:\s]*([\w\s]+?)(?:\s*County|\s*,|\s*$)", text, re.I)
            if cm and not listing.get("county"):
                listing["county"] = cm.group(1).strip()[:60]

            # Parcel / APN / Tax ID
            pn = re.search(r"(?:Parcel|APN|Tax\s*ID)[:\s#]*([\w-]+)", text, re.I)
            if pn and not listing.get("property_id"):
                listing["property_id"] = pn.group(1).strip()

            # HOA
            hoa_m = re.search(r"HOA[:\s]*\$?([\d,]+|None|No)", text, re.I)
            if hoa_m:
                val = hoa_m.group(1).lower()
                listing["hoa"] = "no" if val in ("none", "no", "0") else "yes"

            listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"Homes.com detail error: {e}")
    return listing


# ─────────────────────────────────────────────────────────────────────────
# LAND.COM — https://www.land.com/{State}/all-land/under-{price}/page-{N}/
# Uses curl_cffi to bypass Akamai bot protection (TLS fingerprint impersonation)
# ─────────────────────────────────────────────────────────────────────────

# Land.com uses Title Case state names in URLs
LANDCOM_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New-Hampshire", "New-Jersey", "New-Mexico", "New-York",
    "North-Carolina", "North-Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode-Island", "South-Carolina", "South-Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West-Virginia", "Wisconsin", "Wyoming",
]

LANDCOM_MAX_PAGES = 15  # 25 per page


async def _scrape_landcom(db, client: httpx.AsyncClient, states_filter: list) -> int:
    """Scrape Land.com — major land marketplace.

    Uses curl_cffi with Safari 15.5 impersonation to bypass Akamai bot protection.
    The httpx client parameter is unused (kept for interface compatibility).
    """
    col = db[COL_LISTINGS]
    count = 0
    filters = await _get_filter_settings(db)
    max_price = int(filters["max_price"]) if filters["max_price"] < 999999999 else 50000

    # Map filter states to Land.com Title Case format
    states = LANDCOM_STATES
    if states_filter:
        states = [
            s for s in LANDCOM_STATES
            if s.lower().replace("-", " ") in states_filter
        ]

    _scrape_progress["states_total"] = len(states)
    _scrape_progress["states_done"] = 0

    async with CffiSession(impersonate="safari17_2_ios") as session:
        for si, state_name in enumerate(states):
            if _scrape_stop_requested:
                break

            for page in range(1, LANDCOM_MAX_PAGES + 1):
                if _scrape_stop_requested:
                    break

                if page == 1:
                    url = f"https://www.land.com/{state_name}/all-land/under-{max_price}/"
                else:
                    url = f"https://www.land.com/{state_name}/all-land/under-{max_price}/page-{page}/"

                try:
                    resp = await session.get(url, timeout=30)
                    if resp.status_code != 200:
                        logger.warning(f"Land.com HTTP {resp.status_code} for {url}")
                        break
                    if len(resp.text) < 2000:
                        break

                    soup = BeautifulSoup(resp.text, "html.parser")

                    # Find all property links: /property/{slug}/{id}/
                    all_prop_links = soup.find_all("a", href=re.compile(r"/property/[^/]+/\d+/"))
                    if not all_prop_links:
                        break

                    # Group links by href to get per-property data
                    # Each property has ~4 links: image, price+acres, address, description
                    from collections import defaultdict
                    groups = defaultdict(list)
                    for a in all_prop_links:
                        href = a.get("href", "").split("?")[0].rstrip("/")
                        groups[href].append(a)

                    if not groups:
                        break

                    page_new = 0
                    for href, links in groups.items():
                        try:
                            full_url = f"https://www.land.com{href}/" if not href.startswith("http") else href
                            clean_url = full_url.split("?")[0].rstrip("/")

                            # Extract property ID from URL: /property/{slug}/{id}
                            id_m = re.search(r"/(\d+)/?$", href)
                            property_id = id_m.group(1) if id_m else ""

                            # Parse data from the grouped links
                            price = None
                            acreage = None
                            address = ""
                            description = ""

                            for a in links:
                                link_text = a.get_text(strip=True)
                                if not link_text:
                                    continue

                                # Price + acreage link: "$49,950•2.03 acres"
                                price_m = re.search(r"\$([\d,]+)", link_text)
                                acre_m = re.search(r"([\d.]+)\s*acres?", link_text, re.I)
                                if price_m and not price:
                                    price = _parse_price(price_m.group(1))
                                if acre_m and not acreage:
                                    try:
                                        acreage = float(acre_m.group(1))
                                    except ValueError:
                                        pass

                                # Address link: "68th Avenue South, Roy, WA, 98411, Pierce County"
                                if re.search(r",\s*[A-Z]{2},?\s*\d{5}", link_text):
                                    address = link_text

                                # Description link: longer text without price pattern
                                if len(link_text) > 60 and not price_m:
                                    description = link_text

                            # Parse state and county from address
                            state = state_name.replace("-", " ")
                            county = ""
                            if address:
                                # "68th Avenue South, Roy, WA, 98411, Pierce County"
                                addr_parts = [p.strip() for p in address.split(",")]
                                for part in addr_parts:
                                    if re.match(r"^[A-Z]{2}$", part.strip()):
                                        state = STATE_ABBREVS.get(part.strip(), state)
                                    if "county" in part.lower() or (len(addr_parts) >= 5 and part == addr_parts[-1]):
                                        county = part.replace("County", "").strip()

                            name = address if address else f"Land in {state}"
                            if not price:
                                continue

                            listing_hash = _hash(f"landcom:{clean_url}")
                            fresh = {
                                "hash": listing_hash,
                                "source": "landcom",
                                "source_name": "Land.com",
                                "name": name[:200],
                                "url": full_url,
                                "property_id": property_id,
                                "state": state,
                                "county": county,
                                "acreage": acreage,
                                "price": price,
                                "original_price": None,
                                "down_payment": None,
                                "monthly_payment": None,
                                "financing_available": None,
                                "land_type": "Land",
                                "image_url": None,
                                "description": description[:2000],
                                "is_foreclosure": False,
                            }

                            if not _matches_filters(fresh, filters):
                                continue

                            inserted = await _smart_upsert(col, listing_hash, fresh)
                            count += 1
                            if inserted:
                                page_new += 1
                            _scrape_progress["listings_found"] = count

                        except Exception as e:
                            logger.debug(f"Land.com card parse error: {e}")
                            continue

                    # If no new listings on this page, stop paginating (new_only mode)
                    if _scrape_mode == "new_only" and page_new == 0 and page > 1:
                        break

                except Exception as e:
                    logger.error(f"Land.com page error {url}: {e}")
                    _scrape_progress["errors"] += 1
                    break

                await asyncio.sleep(1.0)  # Throttle between pages

            _scrape_progress["states_done"] = si + 1

    return count


async def _scrape_detail_landcom(db, client: httpx.AsyncClient, listing: dict) -> dict:
    """Scrape Land.com property detail page for description, zoning, county, etc."""
    url = listing.get("url")
    if not url:
        return listing
    try:
        async with CffiSession(impersonate="safari17_2_ios") as session:
            resp = await session.get(url, timeout=30)
            if resp.status_code != 200:
                return listing
            soup = BeautifulSoup(resp.text, "html.parser")
            text = soup.get_text(" ", strip=True)

            # Description — try common selectors
            desc = ""
            for sel in [
                soup.find(class_=re.compile(r"description|listing-desc|property-desc", re.I)),
                soup.find("div", attrs={"data-testid": re.compile(r"description", re.I)}),
            ]:
                if sel:
                    desc = sel.get_text(" ", strip=True)
                    break
            if not desc:
                for p in soup.find_all("p"):
                    pt = p.get_text(strip=True)
                    if len(pt) > len(desc):
                        desc = pt
            if desc and len(desc) > len(listing.get("description", "")):
                listing["description"] = desc[:2000]

            # Acreage from detail (more precise)
            am = re.search(r"([\d.]+)\s*(?:total\s*)?acres?", text, re.I)
            if am:
                try:
                    val = float(am.group(1))
                    if val > 0:
                        listing["acreage"] = val
                except ValueError:
                    pass

            # Zoning
            zm = re.search(r"Zoning[:\s]*([^\n.]{3,100})", text, re.I)
            if zm:
                listing["zoning"] = _normalize_zoning(zm.group(1).strip())

            # County (update if missing)
            cm = re.search(r"County[:\s]*([\w\s]+?)(?:\s*County|\s*,|\s*$)", text, re.I)
            if cm and not listing.get("county"):
                listing["county"] = cm.group(1).strip()[:60]

            # Parcel / APN
            pn = re.search(r"(?:Parcel|APN)[:\s#]*([\w-]+)", text, re.I)
            if pn and not listing.get("property_id"):
                listing["property_id"] = pn.group(1).strip()

            # Property type refinement
            pt = re.search(r"Property\s*Type[:\s]*([\w\s/]+?)(?:\s*$|\s*\n)", text, re.I)
            if pt:
                ptype = pt.group(1).strip()
                if ptype and ptype.lower() not in ("land",):
                    listing["land_type"] = ptype[:50]

            # JSON-LD structured data
            for script in soup.find_all("script", type="application/ld+json"):
                if script.string:
                    try:
                        import json
                        ld = json.loads(script.string)
                        if isinstance(ld, dict):
                            if ld.get("@type") in ("Product", "RealEstateListing", "Place"):
                                if ld.get("description") and len(ld["description"]) > len(listing.get("description", "")):
                                    listing["description"] = ld["description"][:2000]
                                if ld.get("image") and not listing.get("image_url"):
                                    img = ld["image"]
                                    if isinstance(img, list):
                                        img = img[0]
                                    if isinstance(img, str):
                                        listing["image_url"] = img
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

            listing["detail_scraped"] = True
    except Exception as e:
        logger.warning(f"Land.com detail error: {e}")
    return listing


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Listings
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/zoning-values")
async def get_zoning_values(db=Depends(get_mongodb)):
    """Get normalized zoning categories from all listings."""
    col = db[COL_LISTINGS]
    raw_values = await col.distinct("zoning")
    categories = set()
    for v in raw_values:
        if v:
            categories.add(_normalize_zoning(v))
    return {"values": sorted(categories)}


@router.get("/listings")
async def list_listings(
    source: Optional[str] = Query(None, description="Filter by source id"),
    state: Optional[str] = Query(None, description="Filter by state name"),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_acreage: Optional[float] = Query(None),
    max_acreage: Optional[float] = Query(None),
    zoning: Optional[str] = Query(None, description="Filter by zoning (comma-separated)"),
    hoa: Optional[str] = Query(None, description="Filter by HOA: yes, no, or any"),
    has_comment: Optional[bool] = Query(None, description="Filter only listings with a user comment"),
    search_comment: Optional[str] = Query(None, description="Search within user comments"),
    favorites_only: bool = Query(False),
    watched_only: bool = Query(False),
    exclude_hidden: bool = Query(True, description="Exclude dismissed/hidden listings"),
    sort_by: str = Query("price", description="price, acreage, scraped_at, state"),
    sort_dir: str = Query("asc", description="asc or desc"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_mongodb),
):
    """List scraped land listings with optional filters."""
    query = {"deleted": {"$ne": True}}
    if exclude_hidden:
        query["is_hidden"] = {"$ne": True}

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
    if zoning:
        zoning_values = [z.strip() for z in zoning.split(",") if z.strip()]
        # Expand normalized category names to regex patterns
        patterns = []
        for zv in zoning_values:
            if zv in ZONING_PATTERNS:
                patterns.append(ZONING_PATTERNS[zv])
            elif zv == "Other":
                # "Other" = anything not matching known categories
                # We negate all known patterns (complex), so just skip filter for Other
                # Instead, gather all raw values that normalize to "Other" and use $in
                all_raw = await col.distinct("zoning")
                other_raw = [r for r in all_raw if r and _normalize_zoning(r) == "Other"]
                if other_raw:
                    patterns.append("|".join(re.escape(r) for r in other_raw))
            else:
                patterns.append(re.escape(zv))
        if patterns:
            combined = "|".join(f"({p})" for p in patterns)
            query["zoning"] = {"$regex": combined, "$options": "i"}

    if hoa and hoa.lower() in ("yes", "no"):
        query["hoa"] = hoa.lower()

    if has_comment:
        query["user_comment"] = {"$exists": True, "$ne": ""}
    if search_comment:
        query["user_comment"] = {"$regex": re.escape(search_comment), "$options": "i"}

    if favorites_only:
        fav_hashes = set()
        async for doc in db[COL_FAVORITES].find({}, {"listing_hash": 1}):
            fav_hashes.add(doc["listing_hash"])
        if fav_hashes:
            query["hash"] = {"$in": list(fav_hashes)}
        else:
            return {"items": [], "total": 0}

    if watched_only:
        watch_hashes = set()
        async for doc in db[COL_WATCHED].find({}, {"listing_hash": 1}):
            watch_hashes.add(doc["listing_hash"])
        if watch_hashes:
            query.setdefault("hash", {})
            if isinstance(query.get("hash"), dict) and "$in" in query["hash"]:
                query["hash"]["$in"] = list(set(query["hash"]["$in"]) & watch_hashes)
            else:
                query["hash"] = {"$in": list(watch_hashes)}
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

    # Get favorites and watched for marking
    fav_set = set()
    async for doc in db[COL_FAVORITES].find({}, {"listing_hash": 1}):
        fav_set.add(doc["listing_hash"])
    watch_set = set()
    async for doc in db[COL_WATCHED].find({}, {"listing_hash": 1}):
        watch_set.add(doc["listing_hash"])

    items = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        doc["is_favorite"] = doc.get("hash", "") in fav_set
        doc["is_watched"] = doc.get("hash", "") in watch_set
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


class CommentInput(BaseModel):
    comment: str = ""


@router.delete("/listings/{listing_hash}")
async def soft_delete_listing(listing_hash: str, db=Depends(get_mongodb)):
    """Soft-delete a listing — mark as deleted so it is hidden and never re-scraped."""
    result = await db[COL_LISTINGS].update_one(
        {"hash": listing_hash},
        {"$set": {"deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Listing not found")
    return {"ok": True}


@router.patch("/listings/{listing_hash}/restore")
async def restore_listing(listing_hash: str, db=Depends(get_mongodb)):
    """Restore a soft-deleted listing."""
    result = await db[COL_LISTINGS].update_one(
        {"hash": listing_hash},
        {"$unset": {"deleted": "", "deleted_at": ""}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Listing not found")
    return {"ok": True}


@router.patch("/listings/{listing_hash}/hidden")
async def toggle_listing_hidden(listing_hash: str, db=Depends(get_mongodb)):
    """Toggle the dismissed/hidden status of a listing."""
    doc = await db[COL_LISTINGS].find_one({"hash": listing_hash}, {"is_hidden": 1})
    if not doc:
        raise HTTPException(404, "Listing not found")
    new_val = not doc.get("is_hidden", False)
    await db[COL_LISTINGS].update_one(
        {"hash": listing_hash},
        {"$set": {"is_hidden": new_val}},
    )
    return {"ok": True, "is_hidden": new_val}


@router.post("/listings/bulk-hide")
async def bulk_hide_listings(
    hashes: List[str] = Body(..., embed=True),
    db=Depends(get_mongodb),
):
    """Migrate client-side hidden hashes to server-side is_hidden flag."""
    if not hashes:
        return {"migrated": 0}
    result = await db[COL_LISTINGS].update_many(
        {"hash": {"$in": hashes}},
        {"$set": {"is_hidden": True}},
    )
    return {"migrated": result.modified_count}


@router.get("/hidden-count")
async def get_hidden_count(db=Depends(get_mongodb)):
    """Get count of hidden/dismissed listings."""
    count = await db[COL_LISTINGS].count_documents({"is_hidden": True, "deleted": {"$ne": True}})
    return {"count": count}


@router.patch("/listings/{listing_hash}/comment")
async def update_listing_comment(
    listing_hash: str,
    body: CommentInput,
    db=Depends(get_mongodb),
):
    """Save or update user comment on a listing."""
    result = await db[COL_LISTINGS].update_one(
        {"hash": listing_hash},
        {"$set": {"user_comment": body.comment}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Listing not found")
    return {"ok": True}


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
        elif source == "landmodo":
            doc = await _scrape_detail_landmodo(db, client, doc)
        elif source == "discountlots":
            doc = await _scrape_detail_discountlots(db, client, doc)
        elif source == "landcentury":
            doc = await _scrape_detail_landcentury(db, client, doc)
        elif source == "ownerfinancedland":
            doc = await _scrape_detail_ownerfinancedland(db, client, doc)
        elif source == "landzero":
            doc = await _scrape_detail_landzero(db, client, doc)
        elif source == "billyland":
            doc = await _scrape_detail_billyland(db, client, doc)
        elif source == "elegmentland":
            doc = await _scrape_detail_elegmentland(db, client, doc)
        elif source == "landequities":
            doc = await _scrape_detail_landequities(db, client, doc)
        elif source == "yourcheapland":
            doc = await _scrape_detail_yourcheapland(db, client, doc)
        elif source == "terraprimelots":
            doc = await _scrape_detail_terraprimelots(db, client, doc)
        elif source == "rawestate":
            doc = await _scrape_detail_rawestate(db, client, doc)
        elif source == "landlimited":
            doc = await _scrape_detail_landlimited(db, client, doc)
        elif source == "landandfarm":
            doc = await _scrape_detail_landandfarm(db, client, doc)
        elif source == "landsearch":
            doc = await _scrape_detail_landsearch(db, client, doc)
        elif source == "landwatch":
            doc = await _scrape_detail_landwatch(db, client, doc)
        elif source == "horizonlandsales":
            doc = await _scrape_detail_horizonlandsales(db, client, doc)
        elif source == "homescom":
            doc = await _scrape_detail_homescom(db, client, doc)
        elif source == "landcom":
            doc = await _scrape_detail_landcom(db, client, doc)

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
# API ROUTES — Watched
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/watched/{listing_hash}")
async def add_watched(listing_hash: str, db=Depends(get_mongodb)):
    """Mark a listing as watched/tracked."""
    listing = await db[COL_LISTINGS].find_one({"hash": listing_hash})
    if not listing:
        raise HTTPException(404, "Listing not found")

    await db[COL_WATCHED].update_one(
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


@router.delete("/watched/{listing_hash}")
async def remove_watched(listing_hash: str, db=Depends(get_mongodb)):
    """Remove a listing from watched."""
    await db[COL_WATCHED].delete_one({"listing_hash": listing_hash})
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

    # Always ensure all default sources exist (upsert missing ones)
    for src in DEFAULT_SOURCES:
        existing = await col.find_one({"source_id": src["source_id"]})
        if not existing:
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


async def _run_scrape_background(source_ids: list, mode: str = "full"):
    """Background scrape worker — runs outside the HTTP request lifecycle.

    Modes:
      - full: scrape listings + update existing + detail scrape new (skip hidden)
      - new_only: scrape listings but only INSERT new (skip existing) + detail scrape new
      - favorites: skip listing scrape, only detail-scrape favorited listings
    """
    global _scrape_mode
    _scrape_mode = mode
    from app.database import get_mongodb
    db = get_mongodb()

    global _scrape_stop_requested
    _scrape_stop_requested = False

    _scrape_progress["running"] = True
    _scrape_progress["started_at"] = datetime.now(timezone.utc).isoformat()
    _scrape_progress["finished_at"] = None
    _scrape_progress["listings_found"] = 0
    _scrape_progress["new_count"] = 0
    _scrape_progress["errors"] = 0
    _scrape_progress["states_done"] = 0
    _scrape_progress["states_total"] = 0
    _scrape_progress["source_index"] = 0
    _scrape_progress["sources_total"] = len(source_ids)
    _scrape_progress["error_msg"] = None
    _scrape_progress["mode"] = mode

    filters = await _get_filter_settings(db)
    results = {}

    try:
        # ── Phase 1: Scrape listing pages (skip in favorites mode) ──
        if mode != "favorites":
            async with httpx.AsyncClient(
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=3),
            ) as client:
                for idx, sid in enumerate(source_ids):
                    if _scrape_stop_requested:
                        logger.info("Scrape stopped by user (phase 1)")
                        _scrape_progress["error_msg"] = "Stopped by user"
                        break
                    _scrape_progress["source"] = sid
                    _scrape_progress["source_index"] = idx + 1
                    try:
                        if sid == "landcentral":
                            count = await _scrape_landcentral(db, client, filters["states"])
                        elif sid == "classiccountryland":
                            count = await _scrape_classiccountryland(db, client, filters["states"])
                        elif sid == "landmodo":
                            count = await _scrape_landmodo(db, client, filters["states"])
                        elif sid == "discountlots":
                            count = await _scrape_discountlots(db, client, filters["states"])
                        elif sid == "landcentury":
                            count = await _scrape_landcentury(db, client, filters["states"])
                        elif sid == "ownerfinancedland":
                            count = await _scrape_ownerfinancedland(db, client, filters["states"])
                        elif sid == "landzero":
                            count = await _scrape_landzero(db, client, filters["states"])
                        elif sid == "billyland":
                            count = await _scrape_billyland(db, client, filters["states"])
                        elif sid == "elegmentland":
                            count = await _scrape_elegmentland(db, client, filters["states"])
                        elif sid == "landequities":
                            count = await _scrape_landequities(db, client, filters["states"])
                        elif sid == "yourcheapland":
                            count = await _scrape_yourcheapland(db, client, filters["states"])
                        elif sid == "terraprimelots":
                            count = await _scrape_terraprimelots(db, client, filters["states"])
                        elif sid == "rawestate":
                            count = await _scrape_rawestate(db, client, filters["states"])
                        elif sid == "landlimited":
                            count = await _scrape_landlimited(db, client, filters["states"])
                        elif sid == "landandfarm":
                            count = await _scrape_landandfarm(db, client, filters["states"])
                        elif sid == "landsearch":
                            count = await _scrape_landsearch(db, client, filters["states"])
                        elif sid == "landwatch":
                            count = await _scrape_landwatch(db, client, filters["states"])
                        elif sid == "horizonlandsales":
                            count = await _scrape_horizonlandsales(db, client, filters["states"])
                        elif sid == "homescom":
                            count = await _scrape_homescom(db, client, filters["states"])
                        elif sid == "landcom":
                            count = await _scrape_landcom(db, client, filters["states"])
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

        # ── Phase 2: scrape detail pages ──
        _scrape_progress["source"] = "details"
        col = db[COL_LISTINGS]

        if mode == "favorites":
            # Only detail-scrape favorited listings (force re-scrape)
            fav_hashes = []
            async for fav in db[COL_FAVORITES].find({}, {"listing_hash": 1}):
                fav_hashes.append(fav["listing_hash"])
            if fav_hashes:
                # Reset detail_scraped so we re-fetch fresh data
                await col.update_many(
                    {"hash": {"$in": fav_hashes}},
                    {"$set": {"detail_scraped": False}},
                )
            detail_query = {"hash": {"$in": fav_hashes}} if fav_hashes else {"_never_match_": True}
        else:
            # Detail-scrape listings not yet scraped, excluding hidden listings
            detail_query = {"detail_scraped": {"$ne": True}, "is_hidden": {"$ne": True}}

        no_detail = await col.find(
            detail_query,
            {"hash": 1, "url": 1, "source": 1, "_id": 0},
        ).to_list(length=2000)

        if no_detail:
            _scrape_progress["states_total"] = len(no_detail)
            _scrape_progress["states_done"] = 0
            logger.info(f"Detail scrape phase: {len(no_detail)} listings to process")

            async with httpx.AsyncClient(
                limits=httpx.Limits(max_connections=3, max_keepalive_connections=2),
            ) as detail_client:
                for i, stub in enumerate(no_detail):
                    if _scrape_stop_requested:
                        logger.info("Scrape stopped by user (detail phase)")
                        _scrape_progress["error_msg"] = "Stopped by user"
                        break
                    try:
                        doc = await col.find_one({"hash": stub["hash"]})
                        if not doc:
                            continue

                        source = doc.get("source", "")
                        if source == "landcentral":
                            doc = await _scrape_detail_landcentral(db, detail_client, doc)
                        elif source == "classiccountryland":
                            doc = await _scrape_detail_ccl(db, detail_client, doc)
                        elif source == "landmodo":
                            doc = await _scrape_detail_landmodo(db, detail_client, doc)
                        elif source == "discountlots":
                            doc = await _scrape_detail_discountlots(db, detail_client, doc)
                        elif source == "landcentury":
                            doc = await _scrape_detail_landcentury(db, detail_client, doc)
                        elif source == "ownerfinancedland":
                            doc = await _scrape_detail_ownerfinancedland(db, detail_client, doc)
                        elif source == "landzero":
                            doc = await _scrape_detail_landzero(db, detail_client, doc)
                        elif source == "billyland":
                            doc = await _scrape_detail_billyland(db, detail_client, doc)
                        elif source == "elegmentland":
                            doc = await _scrape_detail_elegmentland(db, detail_client, doc)
                        elif source == "landequities":
                            doc = await _scrape_detail_landequities(db, detail_client, doc)
                        elif source == "yourcheapland":
                            doc = await _scrape_detail_yourcheapland(db, detail_client, doc)
                        elif source == "terraprimelots":
                            doc = await _scrape_detail_terraprimelots(db, detail_client, doc)
                        elif source == "rawestate":
                            doc = await _scrape_detail_rawestate(db, detail_client, doc)
                        elif source == "landlimited":
                            doc = await _scrape_detail_landlimited(db, detail_client, doc)
                        elif source == "landandfarm":
                            doc = await _scrape_detail_landandfarm(db, detail_client, doc)
                        elif source == "landsearch":
                            doc = await _scrape_detail_landsearch(db, detail_client, doc)
                        elif source == "landwatch":
                            doc = await _scrape_detail_landwatch(db, detail_client, doc)
                        elif source == "horizonlandsales":
                            doc = await _scrape_detail_horizonlandsales(db, detail_client, doc)
                        elif source == "homescom":
                            doc = await _scrape_detail_homescom(db, detail_client, doc)
                        elif source == "landcom":
                            doc = await _scrape_detail_landcom(db, detail_client, doc)
                        else:
                            _scrape_progress["states_done"] = i + 1
                            continue

                        # Save detail data
                        update_data = {
                            k: v for k, v in doc.items() if k != "_id"
                        }
                        await col.update_one(
                            {"hash": stub["hash"]},
                            {"$set": update_data},
                        )
                    except Exception as e:
                        logger.warning(f"Detail scrape error for {stub.get('hash')}: {e}")
                        _scrape_progress["errors"] += 1

                    _scrape_progress["states_done"] = i + 1
                    # Throttle to avoid bans
                    await asyncio.sleep(0.5)
    except Exception as e:
        logger.error(f"Background scrape fatal: {e}\n{traceback.format_exc()}")
        _scrape_progress["error_msg"] = str(e)
    finally:
        _scrape_mode = "full"  # reset global mode
        _scrape_progress["running"] = False
        _scrape_progress["finished_at"] = datetime.now(timezone.utc).isoformat()
        _scrape_progress["source"] = None


@router.get("/scrape/progress")
async def scrape_progress_endpoint():
    """Get live scrape progress (poll from frontend)."""
    return dict(_scrape_progress)


@router.post("/scrape/stop")
async def scrape_stop():
    """Request the running scrape to stop gracefully."""
    global _scrape_stop_requested
    if not _scrape_progress["running"]:
        return {"ok": False, "message": "No scrape is running"}
    _scrape_stop_requested = True
    return {"ok": True, "message": "Stop requested — scrape will finish current item and stop"}


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
async def scrape_all(
    db=Depends(get_mongodb),
    mode: str = Query("full", regex="^(full|new_only|favorites)$"),
):
    """Start scraping all enabled sources in background.

    Modes:
      - full: update all listings + find new + detail-scrape (skip hidden)
      - new_only: only insert brand-new listings, skip existing
      - favorites: only re-scrape detail pages for favorited listings
    """
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

    mode_labels = {
        "full": "Update all & find new",
        "new_only": "Find new only",
        "favorites": "Update favorites",
    }
    label = mode_labels.get(mode, mode)

    asyncio.create_task(_run_scrape_background(source_ids, mode=mode))
    return {"ok": True, "message": f"{label}: {len(source_ids)} sources"}


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Stats & Utilities
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/stats")
async def get_stats(db=Depends(get_mongodb)):
    """Get overall statistics."""
    listings_total = await db[COL_LISTINGS].count_documents({})
    favorites_total = await db[COL_FAVORITES].count_documents({})
    watched_total = await db[COL_WATCHED].count_documents({})
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
        "watched": watched_total,
        "sources": sources_total,
        "by_source": source_counts,
        "by_state": state_counts,
        "last_scrape": last_scrape,
        **price_stats,
    }


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES — Filter Presets
# ═══════════════════════════════════════════════════════════════════════════


class FilterPresetInput(BaseModel):
    name: str
    filters: dict


@router.get("/filter-presets")
async def list_filter_presets(db=Depends(get_mongodb)):
    """List all saved filter presets."""
    items = []
    async for doc in db[COL_FILTER_PRESETS].find({}).sort("created_at", -1):
        doc["_id"] = str(doc["_id"])
        items.append(doc)
    return {"items": items}


@router.post("/filter-presets")
async def create_filter_preset(body: FilterPresetInput, db=Depends(get_mongodb)):
    """Save current filters as a named preset."""
    doc = {
        "name": body.name.strip(),
        "filters": body.filters,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db[COL_FILTER_PRESETS].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.patch("/filter-presets/{preset_id}")
async def update_filter_preset(preset_id: str, body: FilterPresetInput, db=Depends(get_mongodb)):
    """Update name or filters of a preset."""
    from bson import ObjectId
    update = {"name": body.name.strip(), "filters": body.filters}
    result = await db[COL_FILTER_PRESETS].update_one(
        {"_id": ObjectId(preset_id)}, {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Preset not found")
    return {"ok": True}


@router.delete("/filter-presets/{preset_id}")
async def delete_filter_preset(preset_id: str, db=Depends(get_mongodb)):
    """Delete a saved filter preset."""
    from bson import ObjectId
    result = await db[COL_FILTER_PRESETS].delete_one({"_id": ObjectId(preset_id)})
    if result.deleted_count == 0:
        raise HTTPException(404, "Preset not found")
    return {"ok": True}


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
