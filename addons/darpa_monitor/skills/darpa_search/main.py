"""DARPA Monitor: search skill for agent use."""


async def execute(query: str = "", category: str = "", limit: int = 20):
    """Search DARPA items stored from darpa.mil monitoring."""
    from app.database import get_mongodb

    db = get_mongodb()
    col = db["darpa_items"]

    # Build query
    mongo_query = {}
    if category:
        mongo_query["category"] = category
    if query:
        mongo_query["$text"] = {"$search": query}

    try:
        items = await col.find(mongo_query).sort("last_seen_at", -1).limit(limit).to_list(length=limit)
    except Exception:
        # Fall back to regex search if text index not available
        if query:
            regex = {"$regex": query, "$options": "i"}
            mongo_query.pop("$text", None)
            mongo_query["$or"] = [
                {"title": regex},
                {"body": regex},
                {"summary": regex},
            ]
        items = await col.find(mongo_query).sort("last_seen_at", -1).limit(limit).to_list(length=limit)

    if not items:
        # Check if we have any data at all
        total = await col.count_documents({})
        if total == 0:
            return "No DARPA data available. The DARPA Monitor addon needs to scrape data first. Ask the user to click 'Scrape Now' in the DARPA Monitor page."
        return f"No DARPA items found matching query='{query}', category='{category}'. There are {total} total items in the database."

    lines = [f"Found {len(items)} DARPA items:"]

    for item in items:
        cat = item.get("category", "")
        title = item.get("title", "").strip()
        office = item.get("office", "")
        topics = ", ".join(item.get("topics", []))
        is_new = " [NEW]" if item.get("is_new") else ""
        url = item.get("darpa_url") or item.get("external_url", "")

        line = f"\n- [{cat.upper()}]{is_new} {title}"
        if office:
            line += f"\n  Office: {office}"
        if topics:
            line += f"\n  Topics: {topics}"

        # Category-specific info
        if cat == "opportunities":
            opp_num = item.get("opportunity_number", "")
            close = item.get("close_date", "")
            open_d = item.get("open_date", "")
            if opp_num:
                line += f"\n  Number: {opp_num}"
            if open_d:
                line += f" | Opens: {open_d}"
            if close:
                line += f" | Closes: {close}"
            ext = item.get("external_url", "")
            if ext:
                line += f"\n  Apply: {ext}"

        elif cat == "programs":
            status = item.get("status", "")
            pm = item.get("program_manager", "")
            start = item.get("start_date", "")
            if status:
                line += f"\n  Status: {status}"
            if pm:
                line += f" | PM: {pm}"
            if start:
                line += f" | Started: {start}"

        elif cat == "news":
            pub = item.get("publish_date", "")
            if pub:
                line += f"\n  Published: {pub}"

        elif cat == "events":
            edate = item.get("event_date", "")
            loc = item.get("location", "")
            addr = item.get("address", "")
            if edate:
                line += f"\n  Date: {edate}"
            if loc:
                line += f" | Location: {loc}"
            if addr:
                line += f" | {addr}"

        if url:
            line += f"\n  URL: {url}"

        # Body snippet
        summary = item.get("summary") or item.get("body", "")
        if summary:
            snippet = summary[:300].strip()
            if len(summary) > 300:
                snippet += "..."
            line += f"\n  {snippet}"

        lines.append(line)

    return "\n".join(lines)
