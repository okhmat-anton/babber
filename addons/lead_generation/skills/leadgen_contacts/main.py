"""
leadgen_contacts — retrieve existing contacts from the lead generation database.
"""

import logging

logger = logging.getLogger(__name__)


async def execute(params: dict, context: dict = None) -> dict:
    """
    Retrieve contacts from the lead generation database.

    Params:
        contact_type: "clients" | "jobs" | "connections" | "all"
        search: optional search query
        status: optional status filter
        industry: optional industry filter
        relationship: optional relationship filter
        limit: max results (default 50)

    Returns:
        dict with contacts list and summary
    """
    from app.database import get_mongodb

    contact_type = params.get("contact_type", "all")
    search = params.get("search", "")
    status = params.get("status", "")
    industry = params.get("industry", "")
    relationship = params.get("relationship", "")
    limit = params.get("limit", 50)

    db = get_mongodb()
    result = {}

    async def query_collection(col_name, extra_filter=None):
        q = {}
        if search:
            regex = {"$regex": search, "$options": "i"}
            q["$or"] = [
                {"name": regex},
                {"company": regex},
                {"title": regex},
                {"notes": regex},
            ]
        if extra_filter:
            q.update(extra_filter)

        cursor = db[col_name].find(q).sort("created_at", -1).limit(limit)
        items = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(doc)
        return items

    if contact_type in ("clients", "all"):
        extra = {}
        if status:
            extra["status"] = status
        if industry:
            extra["industry"] = {"$regex": industry, "$options": "i"}
        clients = await query_collection("leadgen_clients", extra)
        result["clients"] = clients
        result["clients_count"] = len(clients)

    if contact_type in ("jobs", "all"):
        extra = {}
        if status:
            extra["status"] = status
        jobs = await query_collection("leadgen_jobs", extra)
        result["jobs"] = jobs
        result["jobs_count"] = len(jobs)

    if contact_type in ("connections", "all"):
        extra = {}
        if relationship:
            extra["relationship"] = relationship
        connections = await query_collection("leadgen_connections", extra)
        result["connections"] = connections
        result["connections_count"] = len(connections)

    # Summary
    total = sum(v for k, v in result.items() if k.endswith("_count"))
    result["success"] = True
    result["total"] = total
    result["message"] = f"Retrieved {total} contacts"

    if contact_type == "all":
        result["message"] = (
            f"Retrieved {result.get('clients_count', 0)} clients, "
            f"{result.get('jobs_count', 0)} jobs, "
            f"{result.get('connections_count', 0)} connections"
        )

    return result
