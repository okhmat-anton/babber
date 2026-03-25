"""
Cloud & Sync API — endpoints for remote MongoDB, S3 storage, and data synchronization.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models.user import MongoUser
from app.services.log_service import syslog_bg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud", tags=["cloud"])


# --- Schemas ---

class TestMongoDBRequest(BaseModel):
    url: str


class TestS3Request(BaseModel):
    endpoint_url: str = ""
    access_key: str
    secret_key: str
    bucket_name: str
    region: str = "us-east-1"


class SyncRequest(BaseModel):
    direction: str  # "local_to_cloud" or "cloud_to_local"


class S3BackupRequest(BaseModel):
    note: str = ""


# --- Helpers ---

async def _get_cloud_settings(db: AsyncIOMotorDatabase) -> dict:
    """Read all cloud-related settings from system_settings."""
    from app.mongodb.services import SystemSettingService
    svc = SystemSettingService(db)
    keys = [
        "cloud_mongodb_url", "cloud_mongodb_enabled",
        "s3_endpoint_url", "s3_access_key", "s3_secret_key",
        "s3_bucket_name", "s3_region", "s3_storage_enabled",
    ]
    result = {}
    for key in keys:
        setting = await svc.find_one({"key": key})
        result[key] = setting.value if setting else ""
    return result


# --- Remote MongoDB ---

@router.post("/test-mongodb")
async def test_mongodb_connection(
    body: TestMongoDBRequest,
    _user: MongoUser = Depends(get_current_user),
):
    """Test connection to a remote MongoDB instance."""
    from app.services.data_sync import test_remote_mongodb
    result = await test_remote_mongodb(body.url)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["detail"])
    return result


@router.post("/test-s3")
async def test_s3_connection(
    body: TestS3Request,
    _user: MongoUser = Depends(get_current_user),
):
    """Test connection to S3-compatible storage."""
    from app.services.cloud_storage import S3Storage
    s3 = S3Storage(
        endpoint_url=body.endpoint_url,
        access_key=body.access_key,
        secret_key=body.secret_key,
        bucket=body.bucket_name,
        region=body.region,
    )
    ok = await s3.check_connection()
    if not ok:
        raise HTTPException(status_code=400, detail="S3 connection failed — check credentials and bucket name")
    # Get bucket info
    objects = await s3.list_objects()
    total_size = sum(o["size"] for o in objects)
    return {
        "status": "ok",
        "message": "S3 connection successful",
        "objects_count": len(objects),
        "total_size_bytes": total_size,
    }


# --- Sync Status ---

@router.get("/sync-status")
async def get_sync_status(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Compare local and cloud MongoDB databases."""
    settings = await _get_cloud_settings(db)
    cloud_url = settings.get("cloud_mongodb_url", "")
    if not cloud_url:
        raise HTTPException(status_code=400, detail="Cloud MongoDB URL is not configured")

    from app.services.data_sync import get_sync_status as _get_status
    result = await _get_status(db, cloud_url)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("detail", "Sync status check failed"))
    return result


# --- Data Sync ---

@router.post("/sync")
async def sync_data(
    body: SyncRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Sync data between local and cloud MongoDB (append missing documents)."""
    settings = await _get_cloud_settings(db)
    cloud_url = settings.get("cloud_mongodb_url", "")
    if not cloud_url:
        raise HTTPException(status_code=400, detail="Cloud MongoDB URL is not configured")

    from app.services.data_sync import sync_local_to_cloud, sync_cloud_to_local

    if body.direction == "local_to_cloud":
        result = await sync_local_to_cloud(db, cloud_url)
        await syslog_bg("info", f"Data synced local → cloud: {result['documents_copied']} docs copied",
                        source="cloud", metadata=result)
    elif body.direction == "cloud_to_local":
        result = await sync_cloud_to_local(db, cloud_url)
        await syslog_bg("info", f"Data synced cloud → local: {result['documents_copied']} docs copied",
                        source="cloud", metadata=result)
    else:
        raise HTTPException(status_code=400, detail="Invalid direction. Use 'local_to_cloud' or 'cloud_to_local'")

    return result


# --- S3 File Sync ---

@router.post("/s3-sync-files")
async def sync_files_to_s3(
    body: SyncRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Sync data files between local filesystem and S3."""
    settings = await _get_cloud_settings(db)
    from app.services.cloud_storage import create_s3_client
    s3 = create_s3_client(settings)
    if not s3:
        raise HTTPException(status_code=400, detail="S3 is not configured")

    from app.config import get_settings
    app_settings = get_settings()

    dirs_to_sync = [
        (app_settings.AGENTS_DIR, "data/agents"),
        ("../data/audio", "data/audio"),
        ("../data/chat_media", "data/chat_media"),
    ]

    total_files = 0
    details = []

    if body.direction == "local_to_cloud":
        for local_dir, s3_prefix in dirs_to_sync:
            count = await s3.upload_directory(local_dir, s3_prefix)
            total_files += count
            details.append({"directory": s3_prefix, "files_uploaded": count})
        await syslog_bg("info", f"Files synced local → S3: {total_files} files",
                        source="cloud", metadata={"details": details})
    elif body.direction == "cloud_to_local":
        for local_dir, s3_prefix in dirs_to_sync:
            count = await s3.download_directory(s3_prefix, local_dir)
            total_files += count
            details.append({"directory": s3_prefix, "files_downloaded": count})
        await syslog_bg("info", f"Files synced S3 → local: {total_files} files",
                        source="cloud", metadata={"details": details})
    else:
        raise HTTPException(status_code=400, detail="Invalid direction")

    return {
        "total_files": total_files,
        "details": details,
        "direction": body.direction,
    }


# --- S3 Backup ---

@router.post("/s3-backup")
async def backup_to_s3(
    body: S3BackupRequest,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a full backup and upload it to S3."""
    settings = await _get_cloud_settings(db)
    from app.services.cloud_storage import create_s3_client
    s3 = create_s3_client(settings)
    if not s3:
        raise HTTPException(status_code=400, detail="S3 is not configured")

    # Create local backup first
    from app.services.backup_service import create_backup, BACKUP_DIR
    result = await create_backup(db, note=body.note or "S3 cloud backup")

    # Upload to S3
    backup_path = str(BACKUP_DIR / result["filename"])
    s3_key = f"backups/{result['filename']}"
    success = await s3.upload_file(backup_path, s3_key)

    if not success:
        raise HTTPException(status_code=500, detail="Backup created locally but S3 upload failed")

    await syslog_bg("info", f"Backup uploaded to S3: {result['filename']}",
                    source="cloud", metadata={"s3_key": s3_key, "size_bytes": result["size_bytes"]})

    return {
        **result,
        "s3_key": s3_key,
        "uploaded_to_s3": True,
    }


@router.get("/s3-backups")
async def list_s3_backups(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List backups stored in S3."""
    settings = await _get_cloud_settings(db)
    from app.services.cloud_storage import create_s3_client
    s3 = create_s3_client(settings)
    if not s3:
        raise HTTPException(status_code=400, detail="S3 is not configured")

    objects = await s3.list_objects("backups/")
    return {
        "backups": [
            {
                "filename": obj["key"].split("/")[-1],
                "s3_key": obj["key"],
                "size_bytes": obj["size"],
                "last_modified": obj["last_modified"],
            }
            for obj in objects
            if obj["key"].endswith(".tar.gz")
        ]
    }


@router.post("/s3-restore/{filename}")
async def restore_from_s3(
    filename: str,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Download a backup from S3 and restore it."""
    settings = await _get_cloud_settings(db)
    from app.services.cloud_storage import create_s3_client
    s3 = create_s3_client(settings)
    if not s3:
        raise HTTPException(status_code=400, detail="S3 is not configured")

    from app.services.backup_service import BACKUP_DIR, restore_backup
    import os

    # Download from S3
    s3_key = f"backups/{filename}"
    local_path = str(BACKUP_DIR / filename)
    os.makedirs(str(BACKUP_DIR), exist_ok=True)

    success = await s3.download_file(s3_key, local_path)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found in S3")

    # Restore
    result = await restore_backup(db, filename)
    await syslog_bg("info", f"Restored backup from S3: {filename}",
                    source="cloud", metadata=result)
    return result


# --- Cloud Settings Info ---

@router.get("/settings")
async def get_cloud_settings_info(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get current cloud settings (without secrets)."""
    settings = await _get_cloud_settings(db)
    # Mask sensitive values
    masked = dict(settings)
    for key in ("cloud_mongodb_url", "s3_secret_key", "s3_access_key"):
        val = masked.get(key, "")
        if val and len(val) > 8:
            masked[key] = val[:4] + "***" + val[-4:]
    return masked
