"""
Lead Generation addon — backend routes.

Manages clients, job opportunities, professional connections, and connections map.
Includes job sub-modules: CVs, job criterias, parsed jobs, and job sources (Craigslist parser).
Integrates with AKM-Advisor CRM to push leads and deals.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database import get_mongodb
from app.core.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/addons/lead-generation",
    tags=["addon-lead-generation"],
    dependencies=[Depends(get_current_user)],
)

# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

CLIENTS_COL = "leadgen_clients"
JOBS_COL = "leadgen_jobs"
CONNECTIONS_COL = "leadgen_connections"
CVS_COL = "leadgen_cvs"
JOB_CRITERIAS_COL = "leadgen_job_criterias"
PARSED_JOBS_COL = "leadgen_parsed_jobs"

# CV file storage
CV_UPLOAD_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))).resolve() / "data" / "leadgen_cvs"
CV_MAX_SIZE = 20 * 1024 * 1024  # 20 MB

# Job sources — stored as JSON files in addons/lead_generation/sources/ (git-tracked)
SOURCES_DIR = Path(os.path.dirname(os.path.dirname(__file__))).resolve() / "sources"
SOURCES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_id():
    return str(uuid4())


def _obj_id(doc):
    """Convert MongoDB _id to string and return doc."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ClientCreate(BaseModel):
    name: str
    company: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    website: str = ""
    industry: str = ""
    location: str = ""
    source: str = ""
    notes: str = ""
    tags: list[str] = []
    status: str = "new"  # new, contacted, qualified, converted, lost


class JobCreate(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    url: str = ""
    salary_range: str = ""
    job_type: str = ""  # full-time, part-time, contract, freelance
    remote: str = "any"  # any, remote, hybrid, onsite
    description: str = ""
    requirements: str = ""
    source: str = ""
    status: str = "new"  # new, applied, interview, offer, rejected, saved
    tags: list[str] = []


class ConnectionCreate(BaseModel):
    name: str
    company: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    relationship: str = ""  # colleague, friend, mentor, client, vendor, other
    met_through: str = ""
    notes: str = ""
    tags: list[str] = []
    strength: int = 3  # 1-5 connection strength


class AkmPushBody(BaseModel):
    item_ids: list[str]
    target: str = "leads"  # "leads" or "deals"
    board_id: str = ""


class JobCriteriaCreate(BaseModel):
    industries: list[str] = []           # priority industries
    companies_dream: str = ""            # dream companies (one per line)
    companies_good: str = ""             # good fit companies (one per line)
    companies_backup: str = ""           # backup companies (one per line)
    salary_annual_min: str = ""          # min annual salary e.g. "80000"
    salary_monthly_min: str = ""         # min monthly salary
    tax_state: str = ""                  # US state for tax estimation
    keywords: list[str] = []             # keywords for job title & description (tags)
    states: list[str] = []               # US states or regions
    notes: str = ""


class JobSourceCreate(BaseModel):
    name: str                        # e.g. "Craigslist SF"
    source_type: str = "craigslist"  # craigslist, indeed, linkedin, etc.
    enabled: bool = True
    url: str = ""                    # base URL or region for source
    keywords: list[str] = []         # keywords to search for
    exclude_keywords: list[str] = [] # keywords to exclude
    min_keyword_matches: int = 1     # minimum keyword matches to keep a listing
    max_results: int = 50
    scrape_interval_hours: int = 24
    last_scraped: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats():
    db = get_mongodb()
    clients = await db[CLIENTS_COL].count_documents({})
    jobs = await db[JOBS_COL].count_documents({})
    connections = await db[CONNECTIONS_COL].count_documents({})
    parsed_jobs = await db[PARSED_JOBS_COL].count_documents({})
    cvs = await db[CVS_COL].count_documents({})

    # Status breakdowns
    client_new = await db[CLIENTS_COL].count_documents({"status": "new"})
    client_qualified = await db[CLIENTS_COL].count_documents({"status": "qualified"})
    client_converted = await db[CLIENTS_COL].count_documents({"status": "converted"})

    jobs_new = await db[JOBS_COL].count_documents({"status": "new"})
    jobs_applied = await db[JOBS_COL].count_documents({"status": "applied"})

    parsed_new = await db[PARSED_JOBS_COL].count_documents({"status": "new"})

    return {
        "clients": clients,
        "clients_new": client_new,
        "clients_qualified": client_qualified,
        "clients_converted": client_converted,
        "jobs": jobs,
        "jobs_new": jobs_new,
        "jobs_applied": jobs_applied,
        "connections": connections,
        "parsed_jobs": parsed_jobs,
        "parsed_new": parsed_new,
        "cvs": cvs,
    }


# ---------------------------------------------------------------------------
# Clients CRUD
# ---------------------------------------------------------------------------

@router.get("/clients")
async def list_clients(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    db = get_mongodb()
    q = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": regex}, {"company": regex}, {"email": regex}, {"notes": regex}]
    if status:
        q["status"] = status
    if industry:
        q["industry"] = {"$regex": industry, "$options": "i"}
    if tag:
        q["tags"] = tag

    total = await db[CLIENTS_COL].count_documents(q)
    cursor = db[CLIENTS_COL].find(q).sort("created_at", -1).skip(offset).limit(limit)
    items = [_obj_id(doc) async for doc in cursor]
    return {"items": items, "total": total}


@router.post("/clients")
async def create_client(body: ClientCreate):
    db = get_mongodb()
    doc = body.model_dump()
    doc["_id"] = _make_id()
    doc["created_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    await db[CLIENTS_COL].insert_one(doc)
    return _obj_id(doc)


@router.patch("/clients/{client_id}")
async def update_client(client_id: str, body: dict):
    db = get_mongodb()
    body["updated_at"] = _now_iso()
    result = await db[CLIENTS_COL].update_one({"_id": client_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(404, "Client not found")
    return {"ok": True}


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    db = get_mongodb()
    result = await db[CLIENTS_COL].delete_one({"_id": client_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Client not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Jobs CRUD
# ---------------------------------------------------------------------------

@router.get("/jobs")
async def list_jobs(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    remote: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    db = get_mongodb()
    q = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        q["$or"] = [{"title": regex}, {"company": regex}, {"description": regex}]
    if status:
        q["status"] = status
    if job_type:
        q["job_type"] = job_type
    if remote and remote != "any":
        q["remote"] = remote
    if tag:
        q["tags"] = tag

    total = await db[JOBS_COL].count_documents(q)
    cursor = db[JOBS_COL].find(q).sort("created_at", -1).skip(offset).limit(limit)
    items = [_obj_id(doc) async for doc in cursor]
    return {"items": items, "total": total}


@router.post("/jobs")
async def create_job(body: JobCreate):
    db = get_mongodb()
    doc = body.model_dump()
    doc["_id"] = _make_id()
    doc["created_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    await db[JOBS_COL].insert_one(doc)
    return _obj_id(doc)


@router.patch("/jobs/{job_id}")
async def update_job(job_id: str, body: dict):
    db = get_mongodb()
    body["updated_at"] = _now_iso()
    result = await db[JOBS_COL].update_one({"_id": job_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(404, "Job not found")
    return {"ok": True}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    db = get_mongodb()
    result = await db[JOBS_COL].delete_one({"_id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Job not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Connections CRUD
# ---------------------------------------------------------------------------

@router.get("/connections")
async def list_connections(
    search: Optional[str] = Query(None),
    relationship: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    db = get_mongodb()
    q = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        q["$or"] = [{"name": regex}, {"company": regex}, {"title": regex}, {"notes": regex}]
    if relationship:
        q["relationship"] = relationship
    if tag:
        q["tags"] = tag

    total = await db[CONNECTIONS_COL].count_documents(q)
    cursor = db[CONNECTIONS_COL].find(q).sort("created_at", -1).skip(offset).limit(limit)
    items = [_obj_id(doc) async for doc in cursor]
    return {"items": items, "total": total}


@router.post("/connections")
async def create_connection(body: ConnectionCreate):
    db = get_mongodb()
    doc = body.model_dump()
    doc["_id"] = _make_id()
    doc["created_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    await db[CONNECTIONS_COL].insert_one(doc)
    return _obj_id(doc)


@router.patch("/connections/{conn_id}")
async def update_connection(conn_id: str, body: dict):
    db = get_mongodb()
    body["updated_at"] = _now_iso()
    result = await db[CONNECTIONS_COL].update_one({"_id": conn_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(404, "Connection not found")
    return {"ok": True}


@router.delete("/connections/{conn_id}")
async def delete_connection(conn_id: str):
    db = get_mongodb()
    result = await db[CONNECTIONS_COL].delete_one({"_id": conn_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Connection not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# CVs — Upload / download / CRUD
# ---------------------------------------------------------------------------

@router.get("/cvs")
async def list_cvs():
    db = get_mongodb()
    cursor = db[CVS_COL].find().sort("created_at", -1)
    items = [_obj_id(doc) async for doc in cursor]
    return {"items": items}


@router.post("/cvs/upload")
async def upload_cv(
    file: UploadFile = File(...),
    title: str = Form(""),
    description: str = Form(""),
):
    """Upload a CV/resume file (PDF, DOC, DOCX, TXT)."""
    if not file.filename:
        raise HTTPException(400, "No file provided")

    data = await file.read()
    if len(data) > CV_MAX_SIZE:
        raise HTTPException(400, f"File too large. Max {CV_MAX_SIZE // (1024 * 1024)} MB")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    allowed = {"pdf", "doc", "docx", "txt", "rtf", "odt", "md"}
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported format .{ext}. Allowed: {', '.join(allowed)}")

    cv_id = _make_id()
    CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{cv_id}.{ext}"
    (CV_UPLOAD_DIR / stored_name).write_bytes(data)

    doc = {
        "_id": cv_id,
        "title": title or file.filename,
        "original_name": file.filename,
        "stored_name": stored_name,
        "ext": ext,
        "size": len(data),
        "description": description,
        "created_at": _now_iso(),
    }
    db = get_mongodb()
    await db[CVS_COL].insert_one(doc)
    return _obj_id(doc)


@router.get("/cvs/{cv_id}/download")
async def download_cv(cv_id: str):
    db = get_mongodb()
    doc = await db[CVS_COL].find_one({"_id": cv_id})
    if not doc:
        raise HTTPException(404, "CV not found")
    file_path = CV_UPLOAD_DIR / doc["stored_name"]
    if not file_path.exists():
        raise HTTPException(404, "CV file missing from storage")
    return FileResponse(
        str(file_path),
        filename=doc.get("original_name", doc["stored_name"]),
        media_type="application/octet-stream",
    )


@router.patch("/cvs/{cv_id}")
async def update_cv(cv_id: str, body: dict):
    db = get_mongodb()
    allowed = {"title", "description"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    result = await db[CVS_COL].update_one({"_id": cv_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "CV not found")
    return {"ok": True}


@router.delete("/cvs/{cv_id}")
async def delete_cv(cv_id: str):
    db = get_mongodb()
    doc = await db[CVS_COL].find_one({"_id": cv_id})
    if not doc:
        raise HTTPException(404, "CV not found")
    # Remove file
    file_path = CV_UPLOAD_DIR / doc.get("stored_name", "")
    if file_path.exists():
        file_path.unlink()
    await db[CVS_COL].delete_one({"_id": cv_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Job Criterias — single document (upsert)
# ---------------------------------------------------------------------------

@router.get("/job-criterias")
async def get_job_criterias():
    db = get_mongodb()
    doc = await db[JOB_CRITERIAS_COL].find_one({"_id": "default"})
    if not doc:
        return {
            "industries": [], "companies_dream": "", "companies_good": "", "companies_backup": "",
            "salary_annual_min": "", "salary_monthly_min": "", "tax_state": "",
            "keywords": [], "states": [], "notes": "",
        }
    return _obj_id(doc)


@router.put("/job-criterias")
async def save_job_criterias(body: JobCriteriaCreate):
    db = get_mongodb()
    doc = body.model_dump()
    doc["updated_at"] = _now_iso()
    await db[JOB_CRITERIAS_COL].update_one(
        {"_id": "default"},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# Parsed Jobs
# ---------------------------------------------------------------------------

@router.get("/parsed-jobs")
async def list_parsed_jobs(
    search: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    exclude_source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    db = get_mongodb()
    q = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        q["$or"] = [{"title": regex}, {"company": regex}, {"description": regex}]
    if source:
        q["source"] = source
    if exclude_source:
        excluded = [s.strip() for s in exclude_source.split(",") if s.strip()]
        if excluded:
            q["source"] = {"$nin": excluded}
    if status:
        q["status"] = status

    total = await db[PARSED_JOBS_COL].count_documents(q)
    cursor = db[PARSED_JOBS_COL].find(q).sort("parsed_at", -1).skip(offset).limit(limit)
    items = [_obj_id(doc) async for doc in cursor]
    return {"items": items, "total": total}


@router.patch("/parsed-jobs/{job_id}")
async def update_parsed_job(job_id: str, body: dict):
    db = get_mongodb()
    body["updated_at"] = _now_iso()
    result = await db[PARSED_JOBS_COL].update_one({"_id": job_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(404, "Parsed job not found")
    return {"ok": True}


@router.delete("/parsed-jobs/{job_id}")
async def delete_parsed_job(job_id: str):
    db = get_mongodb()
    result = await db[PARSED_JOBS_COL].delete_one({"_id": job_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Parsed job not found")
    return {"ok": True}


@router.post("/parsed-jobs/bulk-delete")
async def bulk_delete_parsed_jobs(body: dict):
    db = get_mongodb()
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "No IDs provided")
    result = await db[PARSED_JOBS_COL].delete_many({"_id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.post("/parsed-jobs/{job_id}/save-as-job")
async def save_parsed_as_job(job_id: str):
    """Copy a parsed job into the main jobs collection."""
    db = get_mongodb()
    parsed = await db[PARSED_JOBS_COL].find_one({"_id": job_id})
    if not parsed:
        raise HTTPException(404, "Parsed job not found")

    job_doc = {
        "_id": _make_id(),
        "title": parsed.get("title", ""),
        "company": parsed.get("company", ""),
        "location": parsed.get("location", ""),
        "url": parsed.get("url", ""),
        "salary_range": parsed.get("salary_range", ""),
        "job_type": parsed.get("job_type", ""),
        "remote": parsed.get("remote", "any"),
        "description": parsed.get("description", ""),
        "requirements": "",
        "source": parsed.get("source", ""),
        "status": "saved",
        "tags": parsed.get("tags", []),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db[JOBS_COL].insert_one(job_doc)
    await db[PARSED_JOBS_COL].update_one({"_id": job_id}, {"$set": {"status": "saved"}})
    return _obj_id(job_doc)


# ---------------------------------------------------------------------------
# Job Sources — file-based CRUD (git-tracked JSON in sources/ directory)
# ---------------------------------------------------------------------------

def _source_id_from_path(p: Path) -> str:
    """Derive source ID from filename (stem without .json)."""
    return p.stem


def _read_source_file(p: Path) -> dict:
    """Read a single source JSON file and attach _id from filename."""
    data = json.loads(p.read_text(encoding="utf-8"))
    data["_id"] = _source_id_from_path(p)
    return data


def _write_source_file(source_id: str, data: dict):
    """Write source dict to JSON file. Removes _id before writing."""
    out = {k: v for k, v in data.items() if k != "_id"}
    fp = SOURCES_DIR / f"{source_id}.json"
    fp.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slugify(name: str) -> str:
    """Convert a source name to a filesystem-safe slug."""
    import re as _re
    slug = _re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or _make_id()[:8]


@router.get("/job-sources")
async def list_job_sources():
    items = []
    for fp in sorted(SOURCES_DIR.glob("*.json")):
        try:
            items.append(_read_source_file(fp))
        except Exception as e:
            logger.warning(f"Failed to read source file {fp.name}: {e}")
    return {"items": items}


@router.post("/job-sources")
async def create_job_source(body: JobSourceCreate):
    doc = body.model_dump()
    source_id = _slugify(body.name)
    # Ensure unique filename
    fp = SOURCES_DIR / f"{source_id}.json"
    if fp.exists():
        source_id = f"{source_id}_{_make_id()[:6]}"
    doc["created_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    _write_source_file(source_id, doc)
    doc["_id"] = source_id
    return doc


@router.patch("/job-sources/{source_id}")
async def update_job_source(source_id: str, body: dict):
    fp = SOURCES_DIR / f"{source_id}.json"
    if not fp.exists():
        raise HTTPException(404, "Source not found")
    current = _read_source_file(fp)
    current.update(body)
    current["updated_at"] = _now_iso()
    _write_source_file(source_id, current)
    return {"ok": True}


@router.delete("/job-sources/{source_id}")
async def delete_job_source(source_id: str):
    fp = SOURCES_DIR / f"{source_id}.json"
    if not fp.exists():
        raise HTTPException(404, "Source not found")
    fp.unlink()
    return {"ok": True}


@router.post("/job-sources/{source_id}/scrape")
async def trigger_scrape(source_id: str):
    """Manually trigger a scrape for a specific job source.
    Currently supports: craigslist.
    """
    db = get_mongodb()
    fp = SOURCES_DIR / f"{source_id}.json"
    if not fp.exists():
        raise HTTPException(404, "Source not found")
    src = _read_source_file(fp)

    if src.get("source_type") == "craigslist":
        result = await _scrape_craigslist(db, src)
        # Update last_scraped in the file
        src["last_scraped"] = _now_iso()
        src["updated_at"] = _now_iso()
        _write_source_file(source_id, src)
        return result
    else:
        raise HTTPException(400, f"Scraping not yet implemented for source type: {src.get('source_type')}")


async def _scrape_craigslist(db, src: dict) -> dict:
    """Scrape Craigslist job listings based on source keywords.

    Uses Craigslist search HTML (no API key needed).
    Filters results by keyword match count >= min_keyword_matches.
    """
    base_url = src.get("url", "").rstrip("/")
    if not base_url:
        base_url = "https://sfbay.craigslist.org"

    keywords = [k.strip().lower() for k in src.get("keywords", []) if k.strip()]
    exclude = [k.strip().lower() for k in src.get("exclude_keywords", []) if k.strip()]
    min_matches = src.get("min_keyword_matches", 1)
    max_results = src.get("max_results", 50)

    if not keywords:
        return {"parsed": 0, "saved": 0, "message": "No keywords configured for this source"}

    # Build search queries — one per keyword group
    search_query = "|".join(keywords)
    search_url = f"{base_url}/search/jjj?query={search_query}&sort=date"

    parsed_count = 0
    saved_count = 0

    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
            resp = await http.get(search_url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text

            # Simple HTML parsing — extract listing items
            # Craigslist uses <li class="cl-static-search-result"> or <li class="result-row">
            import re

            # Pattern for newer Craigslist format
            pattern = re.compile(
                r'<li[^>]*class="[^"]*cl-static-search-result[^"]*"[^>]*>.*?'
                r'<a[^>]*href="([^"]*)"[^>]*>.*?'
                r'<div class="title"[^>]*>([^<]*)</div>',
                re.DOTALL | re.IGNORECASE,
            )
            # Fallback: older format
            pattern2 = re.compile(
                r'<a[^>]*href="(https?://[^"]*\.craigslist[^"]*\.html[^"]*)"[^>]*class="[^"]*result-title[^"]*"[^>]*>([^<]*)</a>',
                re.DOTALL | re.IGNORECASE,
            )

            matches = pattern.findall(html)
            if not matches:
                matches = pattern2.findall(html)

            for url, title in matches[:max_results]:
                title = title.strip()
                parsed_count += 1
                title_lower = title.lower()

                # Check keyword matches
                match_count = sum(1 for kw in keywords if kw in title_lower)

                # Check exclusions
                excluded = any(ex in title_lower for ex in exclude)
                if excluded:
                    continue

                if match_count < min_matches:
                    continue

                # Check if already exists
                existing = await db[PARSED_JOBS_COL].find_one({"url": url})
                if existing:
                    continue

                doc = {
                    "_id": _make_id(),
                    "title": title,
                    "company": "",
                    "location": base_url.split("//")[-1].split(".")[0] if "//" in base_url else "",
                    "url": url if url.startswith("http") else base_url + url,
                    "salary_range": "",
                    "job_type": "",
                    "remote": "any",
                    "description": "",
                    "source": src.get("name", "craigslist"),
                    "source_id": src.get("_id", ""),
                    "status": "new",
                    "keyword_matches": match_count,
                    "tags": [kw for kw in keywords if kw in title_lower],
                    "parsed_at": _now_iso(),
                }
                await db[PARSED_JOBS_COL].insert_one(doc)
                saved_count += 1

    except httpx.HTTPError as e:
        logger.error(f"Craigslist scrape failed: {e}")
        raise HTTPException(502, f"Scrape failed: {str(e)[:200]}")

    return {"parsed": parsed_count, "saved": saved_count, "source": src.get("name", "")}


# ---------------------------------------------------------------------------
# Connections Map — aggregated data for visualization
# ---------------------------------------------------------------------------

@router.get("/connections-map")
async def get_connections_map():
    """Return all connections grouped by company for graph visualization."""
    db = get_mongodb()
    cursor = db[CONNECTIONS_COL].find({}).sort("company", 1)
    items = [_obj_id(doc) async for doc in cursor]

    # Build nodes and links
    nodes = []
    links = []
    company_map = {}
    node_id = 0

    # Add "You" center node
    nodes.append({"id": "center", "name": "You", "type": "center", "size": 30})

    for c in items:
        cid = c["_id"]
        company = c.get("company", "Unknown")

        # Person node
        nodes.append({
            "id": cid,
            "name": c.get("name", ""),
            "type": "person",
            "company": company,
            "title": c.get("title", ""),
            "relationship": c.get("relationship", ""),
            "strength": c.get("strength", 3),
            "size": 10 + c.get("strength", 3) * 2,
        })

        # Company node (deduplicated)
        if company and company != "Unknown":
            if company not in company_map:
                company_id = f"company_{node_id}"
                node_id += 1
                company_map[company] = company_id
                nodes.append({"id": company_id, "name": company, "type": "company", "size": 18})
                links.append({"source": "center", "target": company_id, "type": "knows"})

            links.append({"source": company_map[company], "target": cid, "type": "works_at"})
        else:
            links.append({"source": "center", "target": cid, "type": "knows"})

    return {"nodes": nodes, "links": links, "total_connections": len(items)}


# ---------------------------------------------------------------------------
# AKM-Advisor Integration — Push leads/deals
# ---------------------------------------------------------------------------

@router.post("/push-to-akm")
async def push_to_akm(body: AkmPushBody):
    """Push selected clients to AKM-Advisor as leads or deals."""
    from app.mongodb.services import SystemSettingService

    db = get_mongodb()
    setting_service = SystemSettingService(db)
    all_settings = await setting_service.get_all(skip=0, limit=5000)
    s = {st.key: st.value for st in all_settings}

    api_key = s.get("leadgen_akm_api_key", "")
    base_url = s.get("leadgen_akm_base_url", "https://app.akm-advisor.com/api/v1")
    board_id = body.board_id or (
        s.get("leadgen_akm_deal_board_id", "") if body.target == "deals"
        else s.get("leadgen_akm_lead_board_id", "")
    )

    if not api_key:
        raise HTTPException(400, "AKM-Advisor API key not configured. Set it in Settings tab.")

    # Fetch selected clients
    clients = []
    for cid in body.item_ids:
        doc = await db[CLIENTS_COL].find_one({"_id": cid})
        if doc:
            clients.append(_obj_id(doc))

    if not clients:
        raise HTTPException(404, "No clients found for provided IDs")

    pushed = []
    errors = []

    async with httpx.AsyncClient(timeout=30) as http:
        for client in clients:
            try:
                if body.target == "deals":
                    payload = {
                        "title": f"{client.get('name', '')} — {client.get('company', '')}".strip(" —"),
                        "board_id": board_id,
                        "contact_name": client.get("name", ""),
                        "contact_email": client.get("email", ""),
                        "contact_phone": client.get("phone", ""),
                        "company": client.get("company", ""),
                        "source": "leadgen_addon",
                        "notes": client.get("notes", ""),
                    }
                    resp = await http.post(
                        f"{base_url}/deals",
                        json=payload,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                else:
                    payload = {
                        "name": client.get("name", ""),
                        "board_id": board_id,
                        "email": client.get("email", ""),
                        "phone": client.get("phone", ""),
                        "company": client.get("company", ""),
                        "source": "leadgen_addon",
                        "notes": client.get("notes", ""),
                    }
                    resp = await http.post(
                        f"{base_url}/leads",
                        json=payload,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )

                if resp.status_code in (200, 201):
                    pushed.append(client["_id"])
                    # Mark as converted
                    await db[CLIENTS_COL].update_one(
                        {"_id": client["_id"]},
                        {"$set": {"status": "converted", "updated_at": _now_iso()}},
                    )
                else:
                    errors.append({"id": client["_id"], "error": resp.text[:200]})
            except Exception as e:
                errors.append({"id": client["_id"], "error": str(e)[:200]})

    return {"pushed": len(pushed), "errors": errors}


# ---------------------------------------------------------------------------
# AKM-Advisor — Fetch available boards/pipelines
# ---------------------------------------------------------------------------

@router.get("/akm-boards")
async def get_akm_boards(target: str = Query("leads")):
    """Fetch available boards from AKM-Advisor to configure pipeline."""
    from app.mongodb.services import SystemSettingService

    db = get_mongodb()
    setting_service = SystemSettingService(db)
    all_settings = await setting_service.get_all(skip=0, limit=5000)
    s = {st.key: st.value for st in all_settings}

    api_key = s.get("leadgen_akm_api_key", "")
    base_url = s.get("leadgen_akm_base_url", "https://app.akm-advisor.com/api/v1")

    if not api_key:
        raise HTTPException(400, "AKM-Advisor API key not configured")

    endpoint = f"{base_url}/lead-boards" if target == "leads" else f"{base_url}/deal-boards"

    async with httpx.AsyncClient(timeout=15) as http:
        try:
            resp = await http.get(endpoint, headers={"Authorization": f"Bearer {api_key}"})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, f"AKM API error: {e.response.text[:200]}")
        except Exception as e:
            raise HTTPException(502, f"Failed to reach AKM-Advisor: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------

@router.post("/clients/bulk-delete")
async def bulk_delete_clients(body: dict):
    db = get_mongodb()
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "No IDs provided")
    result = await db[CLIENTS_COL].delete_many({"_id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.post("/jobs/bulk-delete")
async def bulk_delete_jobs(body: dict):
    db = get_mongodb()
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "No IDs provided")
    result = await db[JOBS_COL].delete_many({"_id": {"$in": ids}})
    return {"deleted": result.deleted_count}


@router.post("/connections/bulk-delete")
async def bulk_delete_connections(body: dict):
    db = get_mongodb()
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(400, "No IDs provided")
    result = await db[CONNECTIONS_COL].delete_many({"_id": {"$in": ids}})
    return {"deleted": result.deleted_count}


# ---------------------------------------------------------------------------
# Clear all data
# ---------------------------------------------------------------------------

@router.post("/clear-all")
async def clear_all():
    db = get_mongodb()
    r1 = await db[CLIENTS_COL].delete_many({})
    r2 = await db[JOBS_COL].delete_many({})
    r3 = await db[CONNECTIONS_COL].delete_many({})
    r4 = await db[PARSED_JOBS_COL].delete_many({})
    r6 = await db[CVS_COL].delete_many({})
    await db[JOB_CRITERIAS_COL].delete_many({})
    # Clean CV files
    if CV_UPLOAD_DIR.exists():
        for f in CV_UPLOAD_DIR.iterdir():
            if f.is_file():
                f.unlink()
    # Note: job source JSON files are NOT deleted by clear-all (they are git-tracked config)
    return {
        "deleted_clients": r1.deleted_count,
        "deleted_jobs": r2.deleted_count,
        "deleted_connections": r3.deleted_count,
        "deleted_parsed_jobs": r4.deleted_count,
        "deleted_cvs": r6.deleted_count,
    }
