"""
Data Sync Service — synchronize data between local and remote MongoDB instances.

Supports:
  - Local → Cloud: copy missing documents from local MongoDB to remote
  - Cloud → Local: copy missing documents from remote MongoDB to local
  - Full backup to S3
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

logger = logging.getLogger(__name__)

# Collections to skip during sync
SKIP_COLLECTIONS = {"system.version", "system.sessions"}


async def get_remote_db(cloud_mongodb_url: str) -> Optional[AsyncIOMotorDatabase]:
    """Create a connection to remote MongoDB and return the database."""
    if not cloud_mongodb_url:
        return None
    try:
        client = AsyncIOMotorClient(cloud_mongodb_url, serverSelectionTimeoutMS=10000)
        # Test connection
        await client.admin.command("ping")
        db_name = cloud_mongodb_url.split("/")[-1].split("?")[0]
        return client[db_name]
    except Exception as e:
        logger.error("Failed to connect to remote MongoDB: %s", e)
        raise


async def test_remote_mongodb(url: str) -> dict:
    """Test connection to remote MongoDB. Returns status info."""
    try:
        client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=10000)
        await client.admin.command("ping")
        db_name = url.split("/")[-1].split("?")[0]
        db = client[db_name]
        collections = await db.list_collection_names()
        total_docs = 0
        for coll_name in collections:
            if coll_name.startswith("system."):
                continue
            total_docs += await db[coll_name].count_documents({})
        client.close()
        return {
            "status": "ok",
            "database": db_name,
            "collections": len([c for c in collections if not c.startswith("system.")]),
            "total_documents": total_docs,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def sync_local_to_cloud(
    local_db: AsyncIOMotorDatabase,
    cloud_url: str,
) -> dict:
    """
    Sync local MongoDB → cloud MongoDB.
    Appends only missing documents (by _id) to cloud.
    """
    remote_db = await get_remote_db(cloud_url)
    return await _sync_databases(local_db, remote_db, direction="local_to_cloud")


async def sync_cloud_to_local(
    local_db: AsyncIOMotorDatabase,
    cloud_url: str,
) -> dict:
    """
    Sync cloud MongoDB → local MongoDB.
    Appends only missing documents (by _id) to local.
    """
    remote_db = await get_remote_db(cloud_url)
    return await _sync_databases(remote_db, local_db, direction="cloud_to_local")


async def _sync_databases(
    source_db: AsyncIOMotorDatabase,
    target_db: AsyncIOMotorDatabase,
    direction: str,
) -> dict:
    """
    Copy documents from source to target that don't exist in target (by _id).
    Returns sync statistics.
    """
    stats = {
        "direction": direction,
        "collections_synced": 0,
        "documents_copied": 0,
        "documents_skipped": 0,
        "errors": [],
        "details": [],
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        source_collections = await source_db.list_collection_names()

        for coll_name in sorted(source_collections):
            if coll_name.startswith("system.") or coll_name in SKIP_COLLECTIONS:
                continue

            try:
                source_coll = source_db[coll_name]
                target_coll = target_db[coll_name]

                # Get all _ids from target
                target_ids = set()
                async for doc in target_coll.find({}, {"_id": 1}):
                    target_ids.add(doc["_id"])

                # Find missing docs in source
                missing_docs = []
                skipped = 0
                async for doc in source_coll.find({}):
                    if doc["_id"] in target_ids:
                        skipped += 1
                    else:
                        missing_docs.append(doc)

                # Insert missing docs
                if missing_docs:
                    await target_coll.insert_many(missing_docs, ordered=False)

                coll_stat = {
                    "collection": coll_name,
                    "copied": len(missing_docs),
                    "skipped": skipped,
                }
                stats["details"].append(coll_stat)
                stats["documents_copied"] += len(missing_docs)
                stats["documents_skipped"] += skipped
                stats["collections_synced"] += 1

            except Exception as e:
                err_msg = f"Error syncing collection {coll_name}: {e}"
                logger.error(err_msg)
                stats["errors"].append(err_msg)

    except Exception as e:
        stats["errors"].append(f"Sync failed: {e}")
        logger.exception("Database sync failed")

    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    return stats


async def get_sync_status(
    local_db: AsyncIOMotorDatabase,
    cloud_url: str,
) -> dict:
    """
    Compare local and cloud databases, return document counts per collection.
    """
    try:
        remote_db = await get_remote_db(cloud_url)
    except Exception as e:
        return {"status": "error", "detail": str(e)}

    local_collections = set(await local_db.list_collection_names())
    remote_collections = set(await remote_db.list_collection_names())

    all_collections = sorted(
        (local_collections | remote_collections)
        - {c for c in (local_collections | remote_collections) if c.startswith("system.")}
    )

    comparison = []
    total_local = 0
    total_cloud = 0

    for coll_name in all_collections:
        local_count = await local_db[coll_name].count_documents({}) if coll_name in local_collections else 0
        remote_count = await remote_db[coll_name].count_documents({}) if coll_name in remote_collections else 0
        total_local += local_count
        total_cloud += remote_count
        comparison.append({
            "collection": coll_name,
            "local_count": local_count,
            "cloud_count": remote_count,
            "diff": local_count - remote_count,
        })

    remote_db.client.close()

    return {
        "status": "ok",
        "collections": comparison,
        "total_local": total_local,
        "total_cloud": total_cloud,
    }
