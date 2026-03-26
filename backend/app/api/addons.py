"""
Addons API — returns addon manifests for the frontend, toggle enable/disable.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.dependencies import get_current_user
from app.database import get_mongodb
from app.services.addon_loader import get_addon_manifests

router = APIRouter(prefix="/api/addons", tags=["addons"], dependencies=[Depends(get_current_user)])


@router.get("")
async def list_addons():
    """Return list of all discovered addon manifests with enabled status."""
    from app.mongodb.services import SystemSettingService

    db = get_mongodb()
    setting_service = SystemSettingService(db)
    all_settings = await setting_service.get_all(skip=0, limit=5000)
    settings_map = {s.key: s.value for s in all_settings}

    manifests = get_addon_manifests()
    for m in manifests:
        addon_id = m.get("id", "unknown")
        enabled_key = f"addon_{addon_id}_enabled"
        m["enabled"] = settings_map.get(enabled_key, "true") == "true"
        menu_mode_key = f"addon_{addon_id}_menu_mode"
        if menu_mode_key in settings_map:
            m["menu_mode"] = settings_map[menu_mode_key]
    # Hidden addons are only visible when enabled (can only be enabled via API/DB)
    manifests = [m for m in manifests if not m.get("hidden", False) or m.get("enabled", False)]
    return manifests


class ToggleBody(BaseModel):
    enabled: bool


@router.post("/{addon_id}/toggle")
async def toggle_addon(addon_id: str, body: ToggleBody):
    """Enable or disable an addon."""
    from app.mongodb.services import SystemSettingService
    from app.mongodb.models import MongoSystemSetting

    db = get_mongodb()
    setting_service = SystemSettingService(db)
    key = f"addon_{addon_id}_enabled"

    existing = await setting_service.get_by_key(key)
    if existing:
        await setting_service.update(existing.id, {"value": str(body.enabled).lower()})
    else:
        new_setting = MongoSystemSetting(
            key=key,
            value=str(body.enabled).lower(),
            description=f"Enable/disable the {addon_id} addon",
        )
        await setting_service.create(new_setting)

    return {"addon_id": addon_id, "enabled": body.enabled}
