"""
Lead Generation addon — backend routes.

Manages clients, job opportunities, professional connections, and connections map.
Integrates with AKM-Advisor CRM to push leads and deals.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Depends
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


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats():
    db = get_mongodb()
    clients = await db[CLIENTS_COL].count_documents({})
    jobs = await db[JOBS_COL].count_documents({})
    connections = await db[CONNECTIONS_COL].count_documents({})

    # Status breakdowns
    client_new = await db[CLIENTS_COL].count_documents({"status": "new"})
    client_qualified = await db[CLIENTS_COL].count_documents({"status": "qualified"})
    client_converted = await db[CLIENTS_COL].count_documents({"status": "converted"})

    jobs_new = await db[JOBS_COL].count_documents({"status": "new"})
    jobs_applied = await db[JOBS_COL].count_documents({"status": "applied"})

    return {
        "clients": clients,
        "clients_new": client_new,
        "clients_qualified": client_qualified,
        "clients_converted": client_converted,
        "jobs": jobs,
        "jobs_new": jobs_new,
        "jobs_applied": jobs_applied,
        "connections": connections,
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
    return {
        "deleted_clients": r1.deleted_count,
        "deleted_jobs": r2.deleted_count,
        "deleted_connections": r3.deleted_count,
    }
