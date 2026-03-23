"""Real Estate: land search skill for agent use."""


async def execute(
    query: str = "",
    state: str = "",
    max_price: float = 0,
    min_acreage: float = 0,
    source: str = "",
    limit: int = 20,
):
    """Search affordable land listings from scraped real estate sources."""
    from app.database import get_mongodb

    db = get_mongodb()
    col = db["re_listings"]

    mongo_query = {}

    if source:
        mongo_query["source"] = source

    if state:
        mongo_query["state"] = {"$regex": state, "$options": "i"}

    if max_price and max_price > 0:
        mongo_query["price"] = {"$lte": max_price}

    if min_acreage and min_acreage > 0:
        mongo_query.setdefault("acreage", {})["$gte"] = min_acreage

    # If query provided, search in name/county/description/state
    if query:
        mongo_query["$or"] = [
            {"name": {"$regex": query, "$options": "i"}},
            {"county": {"$regex": query, "$options": "i"}},
            {"description": {"$regex": query, "$options": "i"}},
            {"state": {"$regex": query, "$options": "i"}},
        ]

    results = []
    cursor = col.find(mongo_query).sort("price", 1).limit(limit)

    async for item in cursor:
        price_str = f"${item['price']:,.0f}" if item.get("price") else "N/A"
        acreage_str = f"{item['acreage']} acres" if item.get("acreage") else "N/A"
        location = ""
        if item.get("county"):
            location = f"{item['county']} County, {item.get('state', '')}"
        elif item.get("state"):
            location = item["state"]

        financing = ""
        if item.get("down_payment") or item.get("monthly_payment"):
            parts = []
            if item.get("down_payment"):
                parts.append(f"${item['down_payment']:,.0f} down")
            if item.get("monthly_payment"):
                parts.append(f"${item['monthly_payment']:,.0f}/mo")
            financing = f" | Financing: {', '.join(parts)}"

        extras = []
        if item.get("is_foreclosure"):
            extras.append("FORECLOSURE")
        if item.get("building_permitted"):
            extras.append("building OK")
        if item.get("camping_allowed"):
            extras.append("camping OK")
        if item.get("septic_allowed"):
            extras.append("septic")
        if item.get("tracts_available"):
            extras.append(f"{item['tracts_available']} tracts")
        extras_str = f" [{', '.join(extras)}]" if extras else ""

        results.append(
            f"[{item.get('source_name', 'Unknown')}] {item.get('name', 'Unnamed')} — "
            f"{price_str}, {acreage_str}, {location}{financing}{extras_str}\n"
            f"  URL: {item.get('url', '')}"
        )

    if not results:
        total = await col.count_documents({})
        if total == 0:
            return (
                "No land listings found. The database is empty — "
                "the user needs to run a scrape first from the Real Estate addon page."
            )
        return f"No listings match your criteria. Total listings in database: {total}. Try broadening your search."

    header = f"Found {len(results)} affordable land listing(s):\n\n"
    return header + "\n\n".join(results)
