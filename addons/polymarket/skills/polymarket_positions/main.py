import httpx
import hmac
import hashlib
import base64
import time
import os

CLOB_API = "https://clob.polymarket.com"


def _build_hmac_signature(secret: str, timestamp: int, method: str, request_path: str, body: str = "") -> str:
    b64_secret = base64.urlsafe_b64decode(secret)
    message = f"{timestamp}{method}{request_path}"
    if body:
        message += body
    h = hmac.new(b64_secret, message.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).decode("utf-8")


async def execute():
    api_key = os.environ.get("POLYMARKET_API_KEY", "")
    api_secret = os.environ.get("POLYMARKET_API_SECRET", "")
    passphrase = os.environ.get("POLYMARKET_PASSPHRASE", "")
    address = os.environ.get("POLYMARKET_ADDRESS", "")
    if not api_key:
        return {"error": "Polymarket API key not configured. Go to Settings to add it."}

    timestamp = int(time.time()) - 5
    sig = _build_hmac_signature(api_secret, timestamp, "GET", "/positions")
    headers = {
        "Content-Type": "application/json",
        "POLY_API_KEY": api_key,
        "POLY_PASSPHRASE": passphrase,
        "POLY_TIMESTAMP": str(timestamp),
        "POLY_SIGNATURE": sig,
    }
    if address:
        headers["POLY_ADDRESS"] = address
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.get(f"{CLOB_API}/positions", headers=headers)
            if r.status_code != 200:
                return {"error": f"API error {r.status_code}: {r.text[:500]}"}
            data = r.json()
            positions = data if isinstance(data, list) else data.get("positions", [])
            return {"positions": positions, "count": len(positions)}
    except Exception as e:
        return {"error": f"Failed to fetch positions: {e}"}
