"""
Polymarket Addon — Backend routes.

Proxies calls to Polymarket CLOB API (https://clob.polymarket.com)
and Gamma API (https://gamma-api.polymarket.com) for event data.

All endpoints require authentication and polymarket_api_key setting.
"""
import logging
import uuid
import hmac
import hashlib
import base64
import time
from datetime import datetime, timezone
from typing import Optional, List

import httpx
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.api.settings import get_setting_value
from app.api.vpn import get_active_vpn as _system_get_active_vpn, make_httpx_client

logger = logging.getLogger("addon.polymarket")

router = APIRouter(
    prefix="/api/addons/polymarket",
    tags=["addon-polymarket"],
    dependencies=[Depends(get_current_user)],
)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


async def _get_polymarket_creds(db) -> dict:
    """Get Polymarket API credentials from system settings."""
    api_key = await get_setting_value(db, "polymarket_api_key")
    api_secret = await get_setting_value(db, "polymarket_api_secret")
    passphrase = await get_setting_value(db, "polymarket_passphrase")
    address = await get_setting_value(db, "polymarket_address")
    return {
        "api_key": api_key or "",
        "api_secret": api_secret or "",
        "passphrase": passphrase or "",
        "address": address or "",
    }


def _clob_headers(creds: dict) -> dict:
    """Build headers for CLOB API calls."""
    headers = {"Content-Type": "application/json"}
    if creds["api_key"]:
        headers["POLY_API_KEY"] = creds["api_key"]
        headers["POLY_API_SECRET"] = creds["api_secret"]
        headers["POLY_PASSPHRASE"] = creds["passphrase"]
    return headers


async def _get_active_vpn(db) -> dict | None:
    """Get the active system VPN if VPN is enabled in Polymarket settings."""
    vpn_enabled = await get_setting_value(db, "polymarket_vpn_enabled")
    if vpn_enabled != "true":
        return None
    return await _system_get_active_vpn(db)


def _make_httpx_client(vpn: dict | None = None, timeout: int = 15) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient, optionally with proxy from system VPN."""
    return make_httpx_client(vpn, timeout)


def _build_hmac_signature(secret: str, timestamp: int, method: str, request_path: str, body: str = "") -> str:
    """Build HMAC signature for Polymarket L2 auth."""
    b64_secret = base64.urlsafe_b64decode(secret)
    message = f"{timestamp}{method}{request_path}"
    if body:
        message += body
    h = hmac.new(b64_secret, message.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).decode("utf-8")


def _clob_l2_headers(creds: dict, method: str, request_path: str, body: str = "") -> dict:
    """Build L2 authenticated headers with HMAC signing for CLOB API."""
    # Subtract 5 seconds to avoid clock skew rejection by Polymarket servers
    timestamp = int(time.time()) - 5
    sig = _build_hmac_signature(creds["api_secret"], timestamp, method, request_path, body)
    headers = {
        "Content-Type": "application/json",
        "POLY_API_KEY": creds["api_key"],
        "POLY_PASSPHRASE": creds["passphrase"],
        "POLY_TIMESTAMP": str(timestamp),
        "POLY_SIGNATURE": sig,
    }
    if creds.get("address"):
        headers["POLY_ADDRESS"] = creds["address"]
    return headers


def _parse_outcome_prices(raw) -> dict:
    """Parse outcomePrices from Gamma API — can be a JSON string or list."""
    if not raw:
        return {"outcome_yes": None, "outcome_no": None}
    try:
        prices = json.loads(raw) if isinstance(raw, str) else raw
        yes = float(prices[0]) if len(prices) > 0 and prices[0] is not None else None
        no = float(prices[1]) if len(prices) > 1 and prices[1] is not None else None
        return {"outcome_yes": yes, "outcome_no": no}
    except (json.JSONDecodeError, TypeError, ValueError, IndexError):
        return {"outcome_yes": None, "outcome_no": None}


def _parse_token_ids(raw) -> dict:
    """Parse clobTokenIds — may be JSON string or list."""
    if not raw:
        return {"token_id_yes": None, "token_id_no": None}
    try:
        ids = json.loads(raw) if isinstance(raw, str) else raw
        return {
            "token_id_yes": ids[0] if len(ids) > 0 else None,
            "token_id_no": ids[1] if len(ids) > 1 else None,
        }
    except (json.JSONDecodeError, TypeError, ValueError, IndexError):
        return {"token_id_yes": None, "token_id_no": None}


# ─── Events (public, no auth needed) ───

@router.get("/events")
async def list_events(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    active: bool = Query(True),
    closed: bool = Query(False),
    search: Optional[str] = None,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List prediction market events from Gamma API."""
    params = {"limit": limit, "offset": offset, "active": str(active).lower(), "closed": str(closed).lower()}
    if search:
        params["tag"] = search
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.get(f"{GAMMA_API}/events", params=params)
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"Gamma API error: {r.text[:500]}")
            events = r.json()
            # Enrich with market data
            result = []
            for ev in events:
                markets = ev.get("markets", [])
                result.append({
                    "id": ev.get("id"),
                    "slug": ev.get("slug"),
                    "title": ev.get("title"),
                    "description": ev.get("description", "")[:300],
                    "start_date": ev.get("startDate"),
                    "end_date": ev.get("endDate"),
                    "active": ev.get("active"),
                    "closed": ev.get("closed"),
                    "liquidity": ev.get("liquidity"),
                    "volume": ev.get("volume"),
                    "markets_count": len(markets),
                    "markets": [
                        {
                            "id": m.get("id"),
                            "question": m.get("question"),
                            **_parse_outcome_prices(m.get("outcomePrices")),
                            "volume": m.get("volume"),
                            "liquidity": m.get("liquidity"),
                            "active": m.get("active"),
                        }
                        for m in markets[:10]
                    ],
                })
            return {"items": result, "total": len(result), "offset": offset, "limit": limit}
    except httpx.HTTPError as e:
        logger.error("Polymarket events fetch error: %s", e)
        raise HTTPException(status_code=502, detail=f"Error connecting to Polymarket: {e}")


@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    """Get detailed event info with all markets."""
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.get(f"{GAMMA_API}/events/{event_id}")
            if r.status_code == 404:
                raise HTTPException(status_code=404, detail="Event not found")
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"Gamma API error: {r.text[:500]}")
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/markets/{token_id}/orderbook")
async def get_orderbook(token_id: str, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    """Get orderbook for a specific market outcome token."""
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.get(f"{CLOB_API}/book", params={"token_id": token_id})
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"CLOB API error: {r.text[:500]}")
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))



# ─── Authenticated endpoints (need API key) ───

async def _require_creds(db) -> dict:
    """Get creds or raise 400."""
    creds = await _get_polymarket_creds(db)
    if not creds["api_key"]:
        raise HTTPException(status_code=400, detail="Polymarket API key not configured. Go to Settings to add it.")
    return creds


class PlaceBetRequest(BaseModel):
    token_id: str
    side: str = "BUY"  # BUY or SELL
    price: float  # 0.01 - 0.99
    size: float  # Amount in USDC


@router.post("/bet")
async def place_bet(body: PlaceBetRequest, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    """Place a bet (limit order) on Polymarket."""
    creds = await _require_creds(db)
    if body.price < 0.01 or body.price > 0.99:
        raise HTTPException(status_code=400, detail="Price must be between 0.01 and 0.99")
    if body.size <= 0:
        raise HTTPException(status_code=400, detail="Size must be positive")

    order = {
        "tokenID": body.token_id,
        "side": body.side.upper(),
        "price": str(body.price),
        "size": str(body.size),
        "type": "GTC",  # Good Till Cancel
    }
    body_str = json.dumps(order)
    headers = _clob_l2_headers(creds, "POST", "/order", body_str)
    vpn = await _get_active_vpn(db)
    try:
        async with _make_httpx_client(vpn, timeout=30) as client:
            r = await client.post(
                f"{CLOB_API}/order",
                content=body_str,
                headers=headers,
            )
            if r.status_code not in (200, 201):
                raise HTTPException(status_code=r.status_code, detail=f"Order failed: {r.text[:500]}")
            result = r.json()

            # Save to local history
            await _save_bet_record(db, body, result)
            return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/positions")
async def get_positions(db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    """Get current open positions / balances."""
    creds = await _require_creds(db)
    headers = _clob_l2_headers(creds, "GET", "/positions")
    vpn = await _get_active_vpn(db)
    try:
        async with _make_httpx_client(vpn) as client:
            r = await client.get(
                f"{CLOB_API}/positions",
                headers=headers,
            )
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"API error: {r.text[:500]}")
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/orders")
async def get_orders(
    status: Optional[str] = Query(None, description="all, live, matched"),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get order history from CLOB API."""
    creds = await _require_creds(db)
    params = {}
    if status:
        params["status"] = status
    headers = _clob_l2_headers(creds, "GET", "/orders")
    vpn = await _get_active_vpn(db)
    try:
        async with _make_httpx_client(vpn) as client:
            r = await client.get(
                f"{CLOB_API}/orders",
                headers=headers,
                params=params,
            )
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"API error: {r.text[:500]}")
            return r.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/balance")
async def get_balance(db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    """Get USDC balance via /balance-allowance with L2 HMAC auth."""
    creds = await _require_creds(db)
    request_path = "/balance-allowance"
    params = "?asset_type=COLLATERAL&signature_type=0"
    headers = _clob_l2_headers(creds, "GET", request_path)
    vpn = await _get_active_vpn(db)
    try:
        async with _make_httpx_client(vpn) as client:
            r = await client.get(
                f"{CLOB_API}{request_path}{params}",
                headers=headers,
            )
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail=f"API error: {r.text[:500]}")
            data = r.json()
            # Return in a consistent format: {balance: "123.45"}
            balance_val = data.get("balance") or data.get("available") or data.get("allowance") or "0"
            return {"balance": balance_val}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ─── Local bet history (MongoDB) ───

@router.get("/history")
async def bet_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get local bet history stored in MongoDB."""
    col = db["addon_polymarket_bets"]
    total = await col.count_documents({})
    cursor = col.find({}).sort("created_at", -1).skip(offset).limit(limit)
    items = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        items.append(doc)
    return {"items": items, "total": total}


@router.get("/history/stats")
async def bet_stats(db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    """Get betting stats — total bets, wins, losses, profit."""
    col = db["addon_polymarket_bets"]
    total = await col.count_documents({})
    won = await col.count_documents({"result": "won"})
    lost = await col.count_documents({"result": "lost"})
    pending = await col.count_documents({"result": {"$in": [None, "pending"]}})

    pipeline = [
        {"$match": {"result": {"$in": ["won", "lost"]}}},
        {"$group": {"_id": None, "total_profit": {"$sum": "$profit"}, "total_invested": {"$sum": "$size"}}},
    ]
    agg = await col.aggregate(pipeline).to_list(1)
    profit = agg[0]["total_profit"] if agg else 0
    invested = agg[0]["total_invested"] if agg else 0

    return {
        "total_bets": total,
        "won": won,
        "lost": lost,
        "pending": pending,
        "total_profit": round(profit, 2),
        "total_invested": round(invested, 2),
        "win_rate": round(won / (won + lost) * 100, 1) if (won + lost) > 0 else 0,
    }


async def _save_bet_record(db, body: PlaceBetRequest, api_result: dict):
    """Save bet to local MongoDB for tracking."""
    col = db["addon_polymarket_bets"]
    await col.insert_one({
        "token_id": body.token_id,
        "side": body.side,
        "price": body.price,
        "size": body.size,
        "order_id": api_result.get("orderID") or api_result.get("id"),
        "result": "pending",
        "profit": 0,
        "api_response": api_result,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


# ─── Manual result recording ───

class RecordResultRequest(BaseModel):
    result: str  # "won" or "lost"
    profit: float = 0


@router.patch("/history/{bet_id}")
async def record_bet_result(
    bet_id: str,
    body: RecordResultRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Record whether a bet was won or lost."""
    from bson import ObjectId
    col = db["addon_polymarket_bets"]
    r = await col.update_one(
        {"_id": ObjectId(bet_id)},
        {"$set": {"result": body.result, "profit": body.profit}},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Bet not found")
    return {"message": "Result recorded"}


# ─── AI Betting ─────────────────────────────────────────────

RARE_EVENTS_KEYWORDS = [
    "election", "president", "presidential", "vote", "governor", "senate",
    "congress", "prime minister", "parliament", "referendum", "nominee",
    "bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "defi",
    "crash", "correction", "bear market", "bull market",
    "war", "invasion", "nuclear", "sanctions", "coup", "crisis", "conflict",
    "military", "nato", "missile", "ceasefire", "peace",
    "impeach", "resign", "assassination", "indictment", "arrest", "conviction",
    "earthquake", "hurricane", "tsunami", "pandemic", "outbreak", "wildfire",
    "recession", "default", "collapse", "bankruptcy",
    "tariff", "ban", "embargo", "trade war",
    "fed ", "interest rate", "inflation", "gdp", "unemployment",
    "spacex", "mars", "ai regulation", "tiktok",
]

STRATEGY_KEYWORDS = {
    "rare_events_micro": RARE_EVENTS_KEYWORDS,
}


class AiBettingAnalyzeRequest(BaseModel):
    strategy: str = "rare_events_micro"
    agent_id: Optional[str] = None
    default_amount: float = 1.0
    max_odds: float = 0.35
    min_multiplier: float = 2.5


class SessionBetsUpdateRequest(BaseModel):
    bets: List[dict]
    default_amount: Optional[float] = None
    min_multiplier: Optional[float] = None


@router.post("/ai-betting/analyze")
async def ai_betting_analyze(
    body: AiBettingAnalyzeRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Fetch active events, filter by strategy keywords, build betting session."""
    keywords = STRATEGY_KEYWORDS.get(body.strategy, RARE_EVENTS_KEYWORDS)

    # 1. Fetch events from Gamma API (multiple pages)
    all_events = []
    for offset in range(0, 500, 100):
        try:
            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                r = await client.get(f"{GAMMA_API}/events", params={
                    "limit": 100, "offset": offset,
                    "active": "true", "closed": "false",
                })
                if r.status_code == 200:
                    batch = r.json()
                    if not batch:
                        break
                    all_events.extend(batch)
                else:
                    break
        except Exception as exc:
            logger.warning("Gamma fetch page offset=%s failed: %s", offset, exc)
            break

    logger.info("AI Betting: fetched %d events from Gamma", len(all_events))

    # 2. Filter by strategy keywords
    filtered_events = []
    for ev in all_events:
        text = f"{ev.get('title', '')} {ev.get('description', '')}".lower()
        for m in ev.get("markets", []):
            text += f" {m.get('question', '')}".lower()
        if any(kw in text for kw in keywords):
            filtered_events.append(ev)

    logger.info("AI Betting: %d events match strategy '%s'", len(filtered_events), body.strategy)

    # 2.5. Global exclusion — get all token_ids that were already bet on
    placed_token_ids = set()
    cursor = db["addon_polymarket_bets"].find({}, {"token_id": 1})
    async for rec in cursor:
        if rec.get("token_id"):
            placed_token_ids.add(rec["token_id"])
    # Also check bets marked as placed in other sessions
    session_cursor = db["polymarket_sessions"].find(
        {"bets.placed": True},
        {"bets.token_id": 1, "bets.placed": 1},
    )
    async for sess in session_cursor:
        for b in sess.get("bets", []):
            if b.get("placed") and b.get("token_id"):
                placed_token_ids.add(b["token_id"])
    # Also exclude rejected token_ids (agent decided not to play)
    rejected_cursor = db["polymarket_rejected_bets"].find({}, {"token_id": 1})
    async for rec in rejected_cursor:
        if rec.get("token_id"):
            placed_token_ids.add(rec["token_id"])

    if placed_token_ids:
        logger.info("AI Betting: excluding %d globally placed/rejected token_ids", len(placed_token_ids))

    # 3. Build bet options — pick the rare (low-probability) side of each market
    bets = []
    bet_num = 0
    for ev in filtered_events:
        for m in ev.get("markets", []):
            if not m.get("active", True):
                continue
            prices = _parse_outcome_prices(m.get("outcomePrices"))
            tokens = _parse_token_ids(m.get("clobTokenIds"))
            yes_p = prices.get("outcome_yes")
            no_p = prices.get("outcome_no")
            if yes_p is None or no_p is None:
                continue

            sides = []
            if 0.005 < yes_p <= body.max_odds:
                mult = round(1 / yes_p, 2)
                if mult >= body.min_multiplier:
                    sides.append({
                        "side": "YES", "odds": yes_p,
                        "token_id": tokens.get("token_id_yes"),
                        "payout_multiplier": mult,
                    })
            if 0.005 < no_p <= body.max_odds:
                mult = round(1 / no_p, 2)
                if mult >= body.min_multiplier:
                    sides.append({
                        "side": "NO", "odds": no_p,
                        "token_id": tokens.get("token_id_no"),
                        "payout_multiplier": mult,
                    })

            for s in sides:
                # Skip if already placed globally
                if s["token_id"] and s["token_id"] in placed_token_ids:
                    continue
                bet_num += 1
                bets.append({
                    "number": bet_num,
                    "event_title": ev.get("title", ""),
                    "market_id": m.get("id"),
                    "market_question": m.get("question", ""),
                    "side": s["side"],
                    "odds": s["odds"],
                    "token_id": s["token_id"],
                    "payout_multiplier": s["payout_multiplier"],
                    "amount": body.default_amount,
                    "expected_payout": round(body.default_amount * s["payout_multiplier"], 2),
                    "end_date": ev.get("endDate") or ev.get("end_date"),
                    "selected": True,
                })

    # 4. Create session document
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "strategy": body.strategy,
        "agent_id": body.agent_id,
        "default_amount": body.default_amount,
        "max_odds": body.max_odds,
        "min_multiplier": body.min_multiplier,
        "bets": bets,
        "total_events": len(filtered_events),
        "total_bets": len(bets),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "draft",
    }
    await db["polymarket_sessions"].insert_one({**session, "_id": session_id})

    logger.info("AI Betting: session %s created with %d bets", session_id, len(bets))
    return session


@router.get("/ai-betting/sessions")
async def list_ai_betting_sessions(
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List past AI betting sessions (newest first)."""
    cursor = db["polymarket_sessions"].find().sort("created_at", -1).limit(50)
    sessions = []
    async for doc in cursor:
        doc.pop("_id", None)
        # Return summary without full bets array
        doc["bets_count"] = len(doc.get("bets", []))
        doc.pop("bets", None)
        sessions.append(doc)
    return sessions


@router.get("/ai-betting/sessions/{session_id}")
async def get_ai_betting_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single AI betting session with all bets."""
    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    doc.pop("_id", None)
    return doc


@router.patch("/ai-betting/sessions/{session_id}")
async def update_session_bets(
    session_id: str,
    body: SessionBetsUpdateRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update bets selection/amounts in a session."""
    update_fields = {"bets": body.bets}
    if body.default_amount is not None:
        update_fields["default_amount"] = body.default_amount
    if body.min_multiplier is not None:
        update_fields["min_multiplier"] = body.min_multiplier
    r = await db["polymarket_sessions"].update_one(
        {"id": session_id},
        {"$set": update_fields},
    )
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session updated"}


@router.delete("/ai-betting/sessions/{session_id}")
async def delete_ai_betting_session(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete an AI betting session."""
    r = await db["polymarket_sessions"].delete_one({"id": session_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


@router.post("/ai-betting/sessions/{session_id}/place")
async def place_session_bets(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Place all selected bets in a session via CLOB API."""
    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    creds = await _get_polymarket_creds(db)
    if not creds["api_key"]:
        raise HTTPException(status_code=400, detail="Polymarket API credentials not configured")

    vpn = await _get_active_vpn(db)
    results = []

    for bet in doc.get("bets", []):
        if not bet.get("selected") or not bet.get("token_id"):
            continue
        try:
            order_body = {
                "tokenID": bet["token_id"],
                "side": "BUY",
                "price": str(bet["odds"]),
                "size": str(bet["amount"]),
            }
            body_str = json.dumps(order_body)
            headers = _clob_l2_headers(creds, "POST", "/order", body_str)
            async with _make_httpx_client(vpn, timeout=30) as client:
                r = await client.post(f"{CLOB_API}/order", headers=headers, content=body_str)
                success = r.status_code in (200, 201)
                detail = r.json() if success else r.text[:300]
                results.append({
                    "bet_number": bet["number"],
                    "success": success,
                    "detail": detail,
                })
                # Also save to bet history
                if success:
                    await db["addon_polymarket_bets"].insert_one({
                        "token_id": bet["token_id"],
                        "side": bet["side"],
                        "price": bet["odds"],
                        "size": bet["amount"],
                        "order_id": detail.get("orderID") or detail.get("id"),
                        "result": "pending",
                        "profit": 0,
                        "session_id": session_id,
                        "api_response": detail,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
        except Exception as exc:
            results.append({
                "bet_number": bet["number"],
                "success": False,
                "detail": str(exc),
            })

    placed = len([r for r in results if r["success"]])
    failed = len([r for r in results if not r["success"]])

    # Update session status
    new_status = "placed" if failed == 0 else ("partial" if placed > 0 else "failed")

    # Mark successfully placed bets in the session document
    placed_numbers = {r["bet_number"] for r in results if r["success"]}
    if placed_numbers:
        bets = doc.get("bets", [])
        for bet in bets:
            if bet.get("number") in placed_numbers:
                bet["placed"] = True
                bet["selected"] = False
        update_fields = {"status": new_status, "place_results": results, "bets": bets}
    else:
        update_fields = {"status": new_status, "place_results": results}

    await db["polymarket_sessions"].update_one(
        {"id": session_id},
        {"$set": update_fields},
    )

    return {"placed": placed, "failed": failed, "results": results}


@router.post("/ai-betting/sessions/{session_id}/place-single/{bet_number}")
async def place_single_bet(
    session_id: str,
    bet_number: int,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Place a single bet from a session."""
    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    creds = await _get_polymarket_creds(db)
    if not creds["api_key"]:
        raise HTTPException(status_code=400, detail="Polymarket API credentials not configured")

    # Find the bet
    bet = None
    bet_idx = None
    for i, b in enumerate(doc.get("bets", [])):
        if b.get("number") == bet_number:
            bet = b
            bet_idx = i
            break
    if not bet:
        raise HTTPException(status_code=404, detail=f"Bet #{bet_number} not found in session")
    if bet.get("placed"):
        raise HTTPException(status_code=400, detail=f"Bet #{bet_number} already placed")
    if not bet.get("token_id"):
        raise HTTPException(status_code=400, detail=f"Bet #{bet_number} has no token_id")

    order_body = {
        "tokenID": bet["token_id"],
        "side": "BUY",
        "price": str(bet["odds"]),
        "size": str(bet["amount"]),
    }
    body_str = json.dumps(order_body)
    headers = _clob_l2_headers(creds, "POST", "/order", body_str)
    vpn = await _get_active_vpn(db)
    try:
        async with _make_httpx_client(vpn, timeout=30) as client:
            r = await client.post(f"{CLOB_API}/order", headers=headers, content=body_str)
            success = r.status_code in (200, 201)
            detail = r.json() if success else r.text[:300]
    except Exception as exc:
        return {"success": False, "bet_number": bet_number, "detail": str(exc)}

    if success:
        # Save to bet history
        await db["addon_polymarket_bets"].insert_one({
            "token_id": bet["token_id"],
            "side": bet["side"],
            "price": bet["odds"],
            "size": bet["amount"],
            "order_id": detail.get("orderID") or detail.get("id"),
            "result": "pending",
            "profit": 0,
            "session_id": session_id,
            "api_response": detail,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Mark bet as placed in session
        await db["polymarket_sessions"].update_one(
            {"id": session_id},
            {"$set": {
                f"bets.{bet_idx}.placed": True,
                f"bets.{bet_idx}.selected": False,
            }},
        )

    return {"success": success, "bet_number": bet_number, "detail": detail}


# ─── Agent Analysis ──────────────────────────────────────────

class AgentAnalyzeRequest(BaseModel):
    agent_id: str
    bet_numbers: List[int] = []  # which bets to analyze; empty = all selected
    total_budget: float = 100.0
    bet_amount: float = 1.0
    min_multiplier: float = 2.5


def _parse_csv_verdicts(raw: str) -> dict[int, dict]:
    """Parse CSV verdicts from agent response. Returns {number: {verdict, rating}}."""
    import re as _re
    verdict_map = {}
    # Find CSV lines: number,verdict,rating
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("number"):
            continue
        # Match: number, verdict, rating (with optional spaces)
        m = _re.match(r'^(\d+)\s*[,;|\t]\s*(green|yellow|red)\s*[,;|\t]\s*(\d+)', line, _re.IGNORECASE)
        if m:
            num = int(m.group(1))
            verdict = m.group(2).lower()
            rating = int(m.group(3))
            verdict_map[num] = {"verdict": verdict, "rating": rating, "reasoning": ""}
    return verdict_map


def _parse_reasoning_response(raw: str) -> dict[int, str]:
    """Parse reasoning from stage-2 response. Supports JSON array or numbered lines."""
    import re as _re
    reasoning_map = {}

    # Try JSON first
    m = _re.search(r'\[.*\]', raw, _re.DOTALL)
    if m:
        try:
            items = json.loads(m.group(0))
            for item in items:
                if isinstance(item, dict) and "number" in item:
                    reasoning_map[item["number"]] = item.get("reasoning", "")
            if reasoning_map:
                return reasoning_map
        except json.JSONDecodeError:
            pass

    # Fallback: parse numbered lines like "#1: reasoning text" or "1. reasoning text"
    for line in raw.splitlines():
        line = line.strip()
        m2 = _re.match(r'^#?(\d+)[.):]\s*(.+)', line)
        if m2:
            num = int(m2.group(1))
            reasoning_map[num] = m2.group(2).strip()

    return reasoning_map


@router.post("/ai-betting/sessions/{session_id}/agent-analyze")
async def agent_analyze_bets(
    session_id: str,
    body: AgentAnalyzeRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Two-stage agent analysis: 1) CSV verdicts+ratings, 2) reasoning for top/bottom bets."""
    from app.services.agent_chat_engine import AgentChatEngine

    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    bets = doc.get("bets", [])
    if body.bet_numbers:
        to_analyze = [b for b in bets if b["number"] in body.bet_numbers and not b.get("placed")]
    else:
        to_analyze = [b for b in bets if b.get("selected") and not b.get("placed")]

    if not to_analyze:
        raise HTTPException(status_code=400, detail="No bets selected for analysis")

    max_picks = int(body.total_budget / body.bet_amount) if body.bet_amount > 0 else len(to_analyze)
    max_picks = min(max_picks, len(to_analyze))

    # Build compact bets list
    bets_text = ""
    for b in to_analyze:
        bets_text += (
            f"#{b['number']}. \"{b['event_title']}\" — {b['market_question']}\n"
            f"   Side: {b['side']}, Odds: {b['odds']*100:.1f}% (x{b['payout_multiplier']})\n\n"
        )

    # ── STAGE 1: CSV verdicts + ratings ──
    prompt_stage1 = f"""You are a professional prediction-market analyst. Evaluate ALL bets below.

CONTEXT:
- Total budget: ${body.total_budget:.2f}, Bet: ${body.bet_amount:.2f}/position, Max picks: {max_picks}
- Min payout multiplier: x{body.min_multiplier}
- Candidates: {len(to_analyze)}

TASK: Rate each bet. Pick TOP {max_picks} as "green", borderline as "yellow", rest as "red".
Prioritize: value bets (market underestimates probability), high multipliers, news/context awareness, avoid correlated bets.

RESPOND IN CSV FORMAT ONLY — one line per bet, no headers, no explanation:
number,verdict,rating

Where rating is 1-100 (100=best opportunity). Example:
1,green,85
2,red,15
3,yellow,45

BETS:

{bets_text}

CSV:"""

    engine = AgentChatEngine(db)
    thinking_log_id = None

    # Helper to save analysis log reference
    async def _save_analysis_log(*, verdicts_summary=None, status="error", error_msg=None, log_id=None):
        lid = log_id or thinking_log_id
        if not lid:
            return
        log_entry = {
            "thinking_log_id": lid,
            "agent_id": body.agent_id,
            "bets_analyzed": len(to_analyze),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }
        if verdicts_summary:
            log_entry["verdicts_summary"] = verdicts_summary
        if error_msg:
            log_entry["error"] = error_msg[:500]
        await db["polymarket_sessions"].update_one(
            {"id": session_id},
            {"$push": {"analysis_logs": log_entry}},
        )

    # Stage 1 call
    try:
        result1 = await engine.generate_full(
            agent_id=body.agent_id,
            user_input=prompt_stage1,
            history=[],
            session_id=session_id,
            load_skills=False,
            load_protocols=False,
            enable_thinking_log=True,
            max_skill_iterations=0,
        )
    except Exception as exc:
        logger.error("Agent analysis stage 1 failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent call failed: {exc}")

    thinking_log_id = getattr(result1, 'thinking_log_id', None)
    raw1 = result1.content.strip()

    # Parse CSV
    verdict_map = _parse_csv_verdicts(raw1)
    if not verdict_map:
        logger.warning("Stage 1: no CSV verdicts parsed from: %s", raw1[:500])
        await _save_analysis_log(error_msg="Failed to parse CSV verdicts from agent response")
        raise HTTPException(status_code=422, detail="Agent did not return valid CSV. Raw: " + raw1[:500])

    logger.info("Stage 1 parsed %d verdicts (CSV)", len(verdict_map))

    # Apply verdicts to session bets
    for b in bets:
        v = verdict_map.get(b["number"])
        if v:
            b["agent_verdict"] = v["verdict"]
            b["agent_rating"] = v.get("rating", 50)
            b["agent_reasoning"] = v.get("reasoning", "")
            if v["verdict"] == "red":
                b["selected"] = False
                b["rejected"] = True  # mark as rejected

    # Save
    verdicts_summary = {
        "green": len([v for v in verdict_map.values() if v["verdict"] == "green"]),
        "yellow": len([v for v in verdict_map.values() if v["verdict"] == "yellow"]),
        "red": len([v for v in verdict_map.values() if v["verdict"] == "red"]),
    }
    await _save_analysis_log(verdicts_summary=verdicts_summary, status="completed")
    await db["polymarket_sessions"].update_one(
        {"id": session_id},
        {"$set": {"bets": bets, "agent_analyzed": True}},
    )

    # Save rejected token_ids globally so future sessions skip them
    red_token_ids = []
    for b in bets:
        if b.get("rejected") and b.get("token_id"):
            red_token_ids.append({
                "token_id": b["token_id"],
                "session_id": session_id,
                "event_title": b.get("event_title", ""),
                "market_question": b.get("market_question", ""),
                "side": b.get("side", ""),
                "odds": b.get("odds", 0),
                "payout_multiplier": b.get("payout_multiplier", 0),
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            })
    if red_token_ids:
        # Upsert to avoid duplicates
        for entry in red_token_ids:
            await db["polymarket_rejected_bets"].update_one(
                {"token_id": entry["token_id"]},
                {"$set": entry, "$setOnInsert": {"_id": entry["token_id"]}},
                upsert=True,
            )
        logger.info("Saved %d rejected token_ids globally", len(red_token_ids))

    return {
        "analyzed": len(verdict_map),
        **verdicts_summary,
        "verdicts": {k: {"verdict": v["verdict"], "rating": v.get("rating", 50), "reasoning": v.get("reasoning", "")} for k, v in verdict_map.items()},
        "thinking_log_id": thinking_log_id,
    }


# ─── Agent Reasoning (Stage 2 — separate call) ──────────────────────

class AgentReasoningRequest(BaseModel):
    agent_id: str
    bet_numbers: List[int] = []  # empty = auto-select top greens + bottom reds


@router.post("/ai-betting/sessions/{session_id}/agent-reasoning")
async def agent_get_reasoning(
    session_id: str,
    body: AgentReasoningRequest,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Stage 2: Get reasoning for selected bets (top green + worst red)."""
    from app.services.agent_chat_engine import AgentChatEngine

    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    bets = doc.get("bets", [])
    if not doc.get("agent_analyzed"):
        raise HTTPException(status_code=400, detail="Run analysis first before requesting reasoning")

    # Pick which bets to get reasoning for
    if body.bet_numbers:
        need_reasoning = body.bet_numbers
    else:
        # Auto: top 10 greens by rating + bottom 10 reds by rating
        analyzed = [(b["number"], b) for b in bets if b.get("agent_verdict")]
        analyzed.sort(key=lambda x: x[1].get("agent_rating", 50), reverse=True)
        top_greens = [num for num, b in analyzed if b["agent_verdict"] == "green"][:10]
        bottom_reds = [num for num, b in analyzed if b["agent_verdict"] == "red"][-10:]
        need_reasoning = list(set(top_greens + bottom_reds))

    if not need_reasoning:
        raise HTTPException(status_code=400, detail="No bets to get reasoning for")

    # Build prompt
    reasoning_bets = []
    for b in bets:
        if b["number"] in need_reasoning:
            reasoning_bets.append(
                f"#{b['number']} [{b.get('agent_verdict','?')}, rating:{b.get('agent_rating','?')}] "
                f"\"{b.get('event_title','')}\" — {b.get('market_question','')} "
                f"(Side: {b.get('side','')}, x{b.get('payout_multiplier',0)})"
            )

    prompt = f"""You previously rated these bets. Now provide 1-2 sentence reasoning for each.

Respond ONLY with a JSON array. Each object: {{"number": N, "reasoning": "..."}}

Bets:
{chr(10).join(reasoning_bets)}

JSON:"""

    engine = AgentChatEngine(db)
    try:
        result = await engine.generate_full(
            agent_id=body.agent_id,
            user_input=prompt,
            history=[],
            session_id=session_id,
            load_skills=False,
            load_protocols=False,
            enable_thinking_log=True,
            max_skill_iterations=0,
        )
    except Exception as exc:
        logger.error("Agent reasoning failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Agent reasoning call failed: {exc}")

    raw = result.content.strip()
    reasoning_map = _parse_reasoning_response(raw)

    # Apply reasoning to session bets
    updated_count = 0
    for b in bets:
        reason = reasoning_map.get(b["number"])
        if reason:
            b["agent_reasoning"] = reason
            updated_count += 1

    await db["polymarket_sessions"].update_one(
        {"id": session_id},
        {"$set": {"bets": bets}},
    )

    thinking_log_id = getattr(result, 'thinking_log_id', None)
    # Save to analysis logs
    if thinking_log_id:
        await db["polymarket_sessions"].update_one(
            {"id": session_id},
            {"$push": {"analysis_logs": {
                "thinking_log_id": thinking_log_id,
                "agent_id": body.agent_id,
                "bets_analyzed": len(need_reasoning),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "completed",
                "type": "reasoning",
            }}},
        )

    return {
        "reasoning_added": updated_count,
        "requested": len(need_reasoning),
        "thinking_log_id": thinking_log_id,
    }


# ─── Rejected Bets Management ──────────────────────

@router.get("/ai-betting/rejected-bets")
async def list_rejected_bets(
    limit: int = 200,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List globally rejected bets (token_ids excluded from future sessions)."""
    cursor = db["polymarket_rejected_bets"].find().sort("rejected_at", -1).limit(limit)
    items = []
    async for doc in cursor:
        doc.pop("_id", None)
        items.append(doc)
    return {"items": items, "total": len(items)}


@router.delete("/ai-betting/rejected-bets/{token_id}")
async def unblock_rejected_bet(
    token_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unblock a rejected bet — remove from global exclusion."""
    result = await db["polymarket_rejected_bets"].delete_one({"token_id": token_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rejected bet not found")
    return {"success": True, "token_id": token_id}


@router.post("/ai-betting/sessions/{session_id}/unblock-bet/{bet_number}")
async def unblock_session_bet(
    session_id: str,
    bet_number: int,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Unblock a rejected bet in a session — remove rejected flag, re-select it."""
    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")

    bets = doc.get("bets", [])
    found = False
    token_id = None
    for b in bets:
        if b["number"] == bet_number:
            b["rejected"] = False
            b["selected"] = True
            b["agent_verdict"] = "yellow"  # downgrade from red to yellow
            token_id = b.get("token_id")
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Bet not found")

    await db["polymarket_sessions"].update_one(
        {"id": session_id},
        {"$set": {"bets": bets}},
    )

    # Also remove from global rejection
    if token_id:
        await db["polymarket_rejected_bets"].delete_one({"token_id": token_id})

    return {"success": True}


@router.get("/ai-betting/sessions/{session_id}/thinking-logs")
async def get_session_thinking_logs(
    session_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get analysis thinking logs for a session."""
    doc = await db["polymarket_sessions"].find_one({"id": session_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Session not found")
    return doc.get("analysis_logs", [])


@router.get("/ai-betting/thinking-logs/{log_id}")
async def get_thinking_log_detail(
    log_id: str,
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get thinking log detail with all steps."""
    log_doc = await db["thinking_logs"].find_one({"_id": log_id})
    if not log_doc:
        raise HTTPException(status_code=404, detail="Thinking log not found")
    log_doc["id"] = log_doc.pop("_id")

    # Get steps
    steps_cursor = db["thinking_steps"].find({"thinking_log_id": log_id}).sort("step_order", 1)
    steps = []
    async for s in steps_cursor:
        s["id"] = s.pop("_id")
        steps.append(s)

    log_doc["steps"] = steps
    return log_doc
