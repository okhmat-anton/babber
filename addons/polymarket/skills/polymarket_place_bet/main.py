import httpx
import hmac
import hashlib
import base64
import json
import time
import os

CLOB_API = "https://clob.polymarket.com"


def _build_hmac_signature(secret: str, timestamp: int, method: str, request_path: str, body: str = "") -> str:
    """Build HMAC signature for Polymarket L2 auth."""
    b64_secret = base64.urlsafe_b64decode(secret)
    message = f"{timestamp}{method}{request_path}"
    if body:
        message += body
    h = hmac.new(b64_secret, message.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).decode("utf-8")


def _clob_l2_headers(api_key: str, api_secret: str, passphrase: str, address: str, method: str, request_path: str, body: str = "") -> dict:
    """Build L2 authenticated headers with HMAC signing for CLOB API."""
    # Subtract 5 seconds to avoid clock skew rejection by Polymarket servers
    timestamp = int(time.time()) - 5
    sig = _build_hmac_signature(api_secret, timestamp, method, request_path, body)
    headers = {
        "Content-Type": "application/json",
        "POLY_API_KEY": api_key,
        "POLY_PASSPHRASE": passphrase,
        "POLY_TIMESTAMP": str(timestamp),
        "POLY_SIGNATURE": sig,
    }
    if address:
        headers["POLY_ADDRESS"] = address
    return headers


async def execute(token_id, price, size, side="BUY"):
    api_key = os.environ.get("POLYMARKET_API_KEY", "")
    api_secret = os.environ.get("POLYMARKET_API_SECRET", "")
    passphrase = os.environ.get("POLYMARKET_PASSPHRASE", "")
    address = os.environ.get("POLYMARKET_ADDRESS", "")
    if not api_key:
        return {"error": "Polymarket API key not configured. Go to Settings to add it."}
    if not token_id:
        return {"error": "token_id is required"}
    price = float(price)
    size = float(size)
    if price < 0.01 or price > 0.99:
        return {"error": "Price must be between 0.01 and 0.99"}
    if size <= 0:
        return {"error": "Size must be positive"}

    order = {
        "tokenID": token_id,
        "side": side.upper(),
        "price": str(price),
        "size": str(size),
        "type": "GTC",
    }
    body_str = json.dumps(order)
    headers = _clob_l2_headers(api_key, api_secret, passphrase, address, "POST", "/order", body_str)
    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            r = await client.post(f"{CLOB_API}/order", content=body_str, headers=headers)
            if r.status_code not in (200, 201):
                return {"error": f"Order failed ({r.status_code}): {r.text[:500]}"}
            result = r.json()
            return {
                "success": True,
                "order_id": result.get("orderID") or result.get("id"),
                "token_id": token_id,
                "side": side,
                "price": price,
                "size": size,
                "status": result.get("status", "submitted"),
                "raw": result,
            }
    except Exception as e:
        return {"error": f"Failed to place bet: {e}"}
