"""
VPN API — system-wide VPN/proxy management.
Supports CRUD, bulk import (paste a list), auto-testing, and activation.
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models.user import MongoUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vpn", tags=["vpn"])

COLLECTION = "system_vpns"


# ─── Models ───

class VpnConfig(BaseModel):
    name: str
    protocol: str = "socks5"  # socks5, socks5h, http, https
    host: str
    port: int = 1080
    username: str = ""
    password: str = ""
    is_active: bool = False


class VpnBulkImport(BaseModel):
    text: str  # Raw text with one proxy per line
    default_protocol: str = "socks5"


# ─── Helpers ───

def build_proxy_url(vpn: dict) -> str:
    """Build proxy URL from VPN config."""
    protocol = vpn.get("protocol", "socks5")
    host = vpn.get("host", "")
    port = vpn.get("port", 1080)
    username = vpn.get("username", "")
    password = vpn.get("password", "")
    if username and password:
        return f"{protocol}://{username}:{password}@{host}:{port}"
    return f"{protocol}://{host}:{port}"


def make_httpx_client(vpn: dict | None = None, timeout: int = 15) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient, optionally with proxy."""
    kwargs = {"timeout": timeout, "verify": False}
    if vpn and vpn.get("host"):
        proxy_url = build_proxy_url(vpn)
        kwargs["proxy"] = proxy_url
    return httpx.AsyncClient(**kwargs)


async def get_active_vpn(db) -> dict | None:
    """Get the currently active VPN proxy config, or None."""
    return await db[COLLECTION].find_one({"is_active": True})


def _parse_proxy_line(line: str, default_protocol: str = "socks5") -> dict | None:
    """
    Parse a single proxy line. Auto-detects format.
    Supported formats:
      - protocol://user:pass@host:port
      - protocol://host:port
      - host:port:user:pass
      - host:port
      - user:pass@host:port
      - IP  PORT  (space/tab separated, e.g. from free-proxy-list.net tables)
      - IP\tPORT\tCODE\tCOUNTRY\tANON\tGOOGLE\tHTTPS\tLAST  (full table row)
    Returns dict with {protocol, host, port, username, password} or None.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Skip header-like lines
    lower = line.lower()
    if any(kw in lower for kw in ["ip address", "port", "country", "anonymity", "last checked"]):
        if sum(1 for kw in ["ip address", "port", "country"] if kw in lower) >= 2:
            return None

    # Format: protocol://...
    url_match = re.match(
        r'^(socks5h?|https?|socks4)://(?:([^:@]+):([^@]+)@)?([^:]+):(\d+)$',
        line, re.IGNORECASE,
    )
    if url_match:
        return {
            "protocol": url_match.group(1).lower(),
            "username": url_match.group(2) or "",
            "password": url_match.group(3) or "",
            "host": url_match.group(4),
            "port": int(url_match.group(5)),
        }

    # Format: user:pass@host:port
    at_match = re.match(r'^([^:@]+):([^@]+)@([^:]+):(\d+)$', line)
    if at_match:
        return {
            "protocol": default_protocol,
            "username": at_match.group(1),
            "password": at_match.group(2),
            "host": at_match.group(3),
            "port": int(at_match.group(4)),
        }

    # Format: host:port:user:pass
    parts = line.split(":")
    if len(parts) == 4:
        try:
            return {
                "protocol": default_protocol,
                "host": parts[0],
                "port": int(parts[1]),
                "username": parts[2],
                "password": parts[3],
            }
        except ValueError:
            pass

    # Format: host:port
    if len(parts) == 2:
        try:
            return {
                "protocol": default_protocol,
                "host": parts[0].strip(),
                "port": int(parts[1].strip()),
                "username": "",
                "password": "",
            }
        except ValueError:
            pass

    # Format: space/tab separated — IP PORT ... (e.g. free-proxy-list.net table rows)
    # May have extra columns: IP PORT CODE COUNTRY ANONYMITY GOOGLE HTTPS LAST_CHECKED
    tokens = re.split(r'[\t\s]+', line)
    if len(tokens) >= 2:
        ip_candidate = tokens[0]
        port_candidate = tokens[1]
        # Validate IP-like host (IPv4 or hostname)
        ip_ok = re.match(r'^(\d{1,3}\.){3}\d{1,3}$', ip_candidate) or re.match(r'^[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$', ip_candidate)
        if ip_ok:
            try:
                port = int(port_candidate)
                if 1 <= port <= 65535:
                    # Auto-detect protocol from row if HTTPS column present
                    proto = default_protocol
                    if len(tokens) >= 7:
                        https_val = tokens[6].strip().lower()
                        if https_val in ("yes", "true", "1"):
                            proto = "https"
                        elif https_val in ("no", "false", "0"):
                            proto = "http"
                    return {
                        "protocol": proto,
                        "host": ip_candidate,
                        "port": port,
                        "username": "",
                        "password": "",
                    }
            except ValueError:
                pass

    return None


async def _test_single_proxy(vpn_dict: dict, timeout: int = 8) -> dict:
    """Test a single proxy and return result with IP or error."""
    try:
        async with make_httpx_client(vpn_dict, timeout=timeout) as client:
            r = await client.get("http://httpbin.org/ip")
            if r.status_code == 200:
                data = r.json()
                return {"success": True, "ip": data.get("origin", "unknown")}
            return {"success": False, "error": f"HTTP {r.status_code}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:200]}


# ─── Endpoints ───

@router.get("")
async def list_vpns(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """List all VPN configurations."""
    cursor = db[COLLECTION].find().sort("created_at", -1)
    items = []
    async for doc in cursor:
        doc.pop("_id", None)
        if doc.get("password"):
            doc["password_set"] = True
            doc["password"] = "***"
        else:
            doc["password_set"] = False
        items.append(doc)
    return {"items": items}


@router.post("")
async def create_vpn(
    body: VpnConfig,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Create a new VPN configuration."""
    vpn_id = str(uuid.uuid4())
    doc = {
        "id": vpn_id,
        **body.dict(),
        "status": "unknown",
        "last_tested": None,
        "last_ip": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if body.is_active:
        await db[COLLECTION].update_many({}, {"$set": {"is_active": False}})
    await db[COLLECTION].insert_one(doc)
    return {"id": vpn_id, "success": True}


@router.patch("/{vpn_id}")
async def update_vpn(
    vpn_id: str,
    body: VpnConfig,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Update a VPN configuration."""
    existing = await db[COLLECTION].find_one({"id": vpn_id})
    if not existing:
        raise HTTPException(status_code=404, detail="VPN not found")

    update = body.dict()
    if update.get("password") == "***":
        update["password"] = existing.get("password", "")

    if update.get("is_active"):
        await db[COLLECTION].update_many({"id": {"$ne": vpn_id}}, {"$set": {"is_active": False}})

    await db[COLLECTION].update_one({"id": vpn_id}, {"$set": update})
    return {"success": True}


@router.delete("/{vpn_id}")
async def delete_vpn(
    vpn_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Delete a VPN configuration."""
    result = await db[COLLECTION].delete_one({"id": vpn_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="VPN not found")
    return {"success": True}


@router.post("/{vpn_id}/activate")
async def activate_vpn(
    vpn_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Set a VPN as the active proxy. Use vpn_id='none' to disable all."""
    await db[COLLECTION].update_many({}, {"$set": {"is_active": False}})
    if vpn_id != "none":
        result = await db[COLLECTION].update_one({"id": vpn_id}, {"$set": {"is_active": True}})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="VPN not found")
    return {"success": True}


@router.post("/{vpn_id}/test")
async def test_vpn(
    vpn_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Test a VPN connection."""
    vpn = await db[COLLECTION].find_one({"id": vpn_id})
    if not vpn:
        raise HTTPException(status_code=404, detail="VPN not found")

    result = await _test_single_proxy(vpn)
    now = datetime.now(timezone.utc).isoformat()

    await db[COLLECTION].update_one(
        {"id": vpn_id},
        {"$set": {
            "status": "working" if result["success"] else "failed",
            "last_tested": now,
            "last_ip": result.get("ip") if result["success"] else None,
        }},
    )

    return {
        "success": result["success"],
        "ip": result.get("ip"),
        "error": result.get("error"),
    }


@router.post("/bulk-import")
async def bulk_import_vpns(
    body: VpnBulkImport,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """
    Parse a list of proxies (one per line), auto-test each,
    and add working ones to the database.
    """
    lines = body.text.strip().split("\n")
    parsed = []
    for line in lines:
        p = _parse_proxy_line(line, body.default_protocol)
        if p:
            parsed.append(p)

    if not parsed:
        raise HTTPException(status_code=400, detail="No valid proxy lines found")

    # Test all in parallel (max 20 concurrent)
    sem = asyncio.Semaphore(20)

    async def test_with_sem(proxy_dict):
        async with sem:
            result = await _test_single_proxy(proxy_dict, timeout=10)
            return {**proxy_dict, **result}

    results = await asyncio.gather(*[test_with_sem(p) for p in parsed])

    added = 0
    failed = 0
    details = []
    now = datetime.now(timezone.utc).isoformat()

    for r in results:
        label = f"{r['host']}:{r['port']}"
        if r.get("success"):
            vpn_id = str(uuid.uuid4())
            await db[COLLECTION].insert_one({
                "id": vpn_id,
                "name": label,
                "protocol": r["protocol"],
                "host": r["host"],
                "port": r["port"],
                "username": r.get("username", ""),
                "password": r.get("password", ""),
                "is_active": False,
                "status": "working",
                "last_tested": now,
                "last_ip": r.get("ip"),
                "created_at": now,
            })
            added += 1
            details.append({"proxy": label, "success": True, "ip": r.get("ip")})
        else:
            failed += 1
            details.append({"proxy": label, "success": False, "error": r.get("error", "")[:200]})

    return {
        "total_parsed": len(parsed),
        "added": added,
        "failed": failed,
        "details": details,
    }


@router.post("/test-all")
async def test_all_vpns(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Test all VPNs and update their status."""
    cursor = db[COLLECTION].find()
    vpns = []
    async for doc in cursor:
        vpns.append(doc)

    if not vpns:
        return {"total": 0, "working": 0, "failed": 0}

    sem = asyncio.Semaphore(20)
    now = datetime.now(timezone.utc).isoformat()

    async def test_one(vpn_doc):
        async with sem:
            result = await _test_single_proxy(vpn_doc, timeout=10)
            status = "working" if result["success"] else "failed"
            await db[COLLECTION].update_one(
                {"id": vpn_doc["id"]},
                {"$set": {
                    "status": status,
                    "last_tested": now,
                    "last_ip": result.get("ip") if result["success"] else None,
                }},
            )
            return result["success"]

    results = await asyncio.gather(*[test_one(v) for v in vpns])
    working = sum(1 for r in results if r)

    return {"total": len(vpns), "working": working, "failed": len(vpns) - working}


@router.delete("/dead")
async def delete_dead_vpns(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    _user: MongoUser = Depends(get_current_user),
):
    """Delete all VPNs with status 'failed'."""
    result = await db[COLLECTION].delete_many({"status": "failed"})
    return {"deleted": result.deleted_count}
