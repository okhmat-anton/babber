"""
leadgen_search — search for potential clients, jobs, or connections.

Uses web_search skill internally or stores manually provided results.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)


async def execute(params: dict, context: dict = None) -> dict:
    """
    Search for potential clients, job opportunities, or connections.

    Params:
        search_type: "clients" | "jobs" | "connections"
        query: search query string
        industry: optional industry filter
        location: optional location filter
        job_type: optional job type filter (full-time, part-time, contract, freelance)
        remote: optional remote filter (any, remote, hybrid, onsite)
        save_results: whether to save results (default True)

    Returns:
        dict with search results summary
    """
    from app.database import get_mongodb

    search_type = params.get("search_type", "clients")
    query = params.get("query", "")
    save_results = params.get("save_results", True)

    if not query:
        return {"error": "Query is required", "success": False}

    db = get_mongodb()
    now = datetime.now(timezone.utc).isoformat()

    # Collection mapping
    col_map = {
        "clients": "leadgen_clients",
        "jobs": "leadgen_jobs",
        "connections": "leadgen_connections",
    }
    collection = col_map.get(search_type, "leadgen_clients")

    # Build a structured result from the query
    # The agent provides parsed data from its search; we store it
    results = []

    if search_type == "clients":
        # Agent is expected to provide structured client data
        items = params.get("results", [])
        if not items:
            # Return existing matches from DB
            regex = {"$regex": query, "$options": "i"}
            cursor = db[collection].find({
                "$or": [{"name": regex}, {"company": regex}, {"industry": regex}, {"notes": regex}]
            }).limit(50)
            existing = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                existing.append(doc)
            return {
                "success": True,
                "search_type": search_type,
                "query": query,
                "found_in_db": len(existing),
                "results": existing,
                "message": f"Found {len(existing)} existing clients matching '{query}'. To add new clients, provide structured data in the 'results' parameter.",
            }

        for item in items:
            doc = {
                "_id": str(uuid4()),
                "name": item.get("name", ""),
                "company": item.get("company", ""),
                "title": item.get("title", ""),
                "email": item.get("email", ""),
                "phone": item.get("phone", ""),
                "linkedin": item.get("linkedin", ""),
                "website": item.get("website", ""),
                "industry": item.get("industry", params.get("industry", "")),
                "location": item.get("location", params.get("location", "")),
                "source": item.get("source", "agent_search"),
                "notes": item.get("notes", f"Found via search: {query}"),
                "tags": item.get("tags", []),
                "status": "new",
                "created_at": now,
                "updated_at": now,
            }
            if save_results:
                await db[collection].insert_one(doc)
            results.append(doc)

    elif search_type == "jobs":
        items = params.get("results", [])
        if not items:
            regex = {"$regex": query, "$options": "i"}
            cursor = db[collection].find({
                "$or": [{"title": regex}, {"company": regex}, {"description": regex}]
            }).limit(50)
            existing = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                existing.append(doc)
            return {
                "success": True,
                "search_type": search_type,
                "query": query,
                "found_in_db": len(existing),
                "results": existing,
                "message": f"Found {len(existing)} existing jobs matching '{query}'.",
            }

        for item in items:
            doc = {
                "_id": str(uuid4()),
                "title": item.get("title", ""),
                "company": item.get("company", ""),
                "location": item.get("location", params.get("location", "")),
                "url": item.get("url", ""),
                "salary_range": item.get("salary_range", ""),
                "job_type": item.get("job_type", params.get("job_type", "")),
                "remote": item.get("remote", params.get("remote", "any")),
                "description": item.get("description", ""),
                "requirements": item.get("requirements", ""),
                "source": item.get("source", "agent_search"),
                "status": "new",
                "tags": item.get("tags", []),
                "created_at": now,
                "updated_at": now,
            }
            if save_results:
                await db[collection].insert_one(doc)
            results.append(doc)

    elif search_type == "connections":
        items = params.get("results", [])
        if not items:
            regex = {"$regex": query, "$options": "i"}
            cursor = db[collection].find({
                "$or": [{"name": regex}, {"company": regex}, {"title": regex}]
            }).limit(50)
            existing = []
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                existing.append(doc)
            return {
                "success": True,
                "search_type": search_type,
                "query": query,
                "found_in_db": len(existing),
                "results": existing,
                "message": f"Found {len(existing)} existing connections matching '{query}'.",
            }

        for item in items:
            doc = {
                "_id": str(uuid4()),
                "name": item.get("name", ""),
                "company": item.get("company", ""),
                "title": item.get("title", ""),
                "email": item.get("email", ""),
                "phone": item.get("phone", ""),
                "linkedin": item.get("linkedin", ""),
                "relationship": item.get("relationship", ""),
                "met_through": item.get("met_through", "agent_search"),
                "notes": item.get("notes", f"Found via search: {query}"),
                "tags": item.get("tags", []),
                "strength": item.get("strength", 3),
                "created_at": now,
                "updated_at": now,
            }
            if save_results:
                await db[collection].insert_one(doc)
            results.append(doc)

    return {
        "success": True,
        "search_type": search_type,
        "query": query,
        "saved": save_results,
        "count": len(results),
        "results": results,
        "message": f"{'Saved' if save_results else 'Found'} {len(results)} {search_type} for query '{query}'",
    }
