from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.core.security import hash_password, verify_password, generate_api_key, hash_api_key
from app.mongodb.models.user import MongoUser
from app.mongodb.models.model_config import MongoModelConfig, MongoModelRoleAssignment, MODEL_ROLES, MODEL_ROLE_LABELS
from app.mongodb.models.api_key import MongoApiKey
from app.mongodb.models.system_setting import MongoSystemSetting
from app.mongodb.services import (
    ModelConfigService, ApiKeyService, SystemSettingService, ModelRoleAssignmentService
)
from app.schemas.auth import ChangePasswordRequest
from app.schemas.settings import (
    ModelConfigCreate, ModelConfigUpdate, ModelConfigResponse,
    ApiKeyCreate, ApiKeyResponse, ApiKeyCreatedResponse,
    SystemSettingResponse, SystemSettingUpdate,
    RoleAssignmentResponse, RoleAssignmentUpdate, RolesListResponse,
)
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


# --- Password ---
@router.put("/password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid old password")
    
    from app.mongodb.services import UserService
    user_service = UserService(db)
    user.password_hash = hash_password(body.new_password)
    await user_service.update(user.id, {"password_hash": user.password_hash})
    return MessageResponse(message="Password changed")


# --- Models ---
@router.get("/models", response_model=list[ModelConfigResponse])
async def list_models(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    models = await model_service.get_all(skip=0, limit=1000)
    # Sort by created_at desc
    models.sort(key=lambda m: m.created_at, reverse=True)
    return models


@router.post("/models", response_model=ModelConfigResponse, status_code=201)
async def create_model(
    body: ModelConfigCreate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    model = MongoModelConfig(**body.model_dump())
    created = await model_service.create(model)
    return created


@router.get("/models/{model_id}", response_model=ModelConfigResponse)
async def get_model(
    model_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    model = await model_service.get_by_id(str(model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.put("/models/{model_id}", response_model=ModelConfigResponse)
async def update_model(
    model_id: UUID,
    body: ModelConfigUpdate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    model = await model_service.get_by_id(str(model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    update_data = body.model_dump(exclude_unset=True)
    updated = await model_service.update(str(model_id), update_data)
    return updated


@router.delete("/models/{model_id}", response_model=MessageResponse)
async def delete_model(
    model_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    model = await model_service.get_by_id(str(model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    await model_service.delete(str(model_id))
    return MessageResponse(message="Model deleted")


@router.post("/models/{model_id}/test", response_model=MessageResponse)
async def test_model(
    model_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    model = await model_service.get_by_id(str(model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    from app.llm.ollama import OllamaProvider
    from app.llm.openai_compatible import OpenAICompatibleProvider
    from app.llm.anthropic import AnthropicProvider
    from app.llm.kieai import KieAIProvider

    try:
        if model.provider == "ollama":
            provider = OllamaProvider(model.base_url)
        elif model.provider == "anthropic":
            api_key = model.api_key or await get_setting_value(db, "anthropic_api_key")
            provider = AnthropicProvider(api_key=api_key, base_url=model.base_url or "https://api.anthropic.com")
        elif model.provider == "kieai":
            api_key = model.api_key or await get_setting_value(db, "kieai_api_key")
            provider = KieAIProvider(api_key=api_key, base_url=model.base_url or "https://api.kie.ai", timeout=model.timeout if hasattr(model, 'timeout') else 180)
        else:
            provider = OpenAICompatibleProvider(model.base_url, model.api_key)
        connected = await provider.check_connection()
        if connected:
            return MessageResponse(message="Connection successful")
        raise HTTPException(status_code=400, detail="Connection failed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")


@router.get("/models/{model_id}/available")
async def list_available_models(
    model_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    model_service = ModelConfigService(db)
    model = await model_service.get_by_id(str(model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    from app.llm.ollama import OllamaProvider
    from app.llm.openai_compatible import OpenAICompatibleProvider
    from app.llm.anthropic import AnthropicProvider
    from app.llm.kieai import KieAIProvider

    try:
        if model.provider == "ollama":
            provider = OllamaProvider(model.base_url)
        elif model.provider == "anthropic":
            api_key = model.api_key or await get_setting_value(db, "anthropic_api_key")
            provider = AnthropicProvider(api_key=api_key, base_url=model.base_url or "https://api.anthropic.com")
        elif model.provider == "kieai":
            api_key = model.api_key or await get_setting_value(db, "kieai_api_key")
            provider = KieAIProvider(api_key=api_key, base_url=model.base_url or "https://api.kie.ai")
        else:
            provider = OpenAICompatibleProvider(model.base_url, model.api_key)
        models = await provider.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- Anthropic ---
@router.get("/anthropic/models")
async def get_anthropic_models(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Return available Anthropic models and whether the key is configured."""
    from app.llm.anthropic import ANTHROPIC_MODELS
    api_key = await get_setting_value(db, "anthropic_api_key")
    return {
        "configured": bool(api_key),
        "models": ANTHROPIC_MODELS,
    }


@router.post("/anthropic/test")
async def test_anthropic_connection(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Test Anthropic API connection using stored key."""
    api_key = await get_setting_value(db, "anthropic_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="Anthropic API key not configured")
    from app.llm.anthropic import AnthropicProvider
    provider = AnthropicProvider(api_key=api_key)
    connected = await provider.check_connection()
    if connected:
        return {"status": "ok", "message": "Anthropic API connection successful"}
    raise HTTPException(status_code=400, detail="Connection failed — check your API key")


@router.get("/anthropic/balance")
async def get_anthropic_balance(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Try to fetch Anthropic billing/balance info.

    Works with Admin API keys (sk-ant-admin...).  Regular API keys
    cannot access the billing API.
    """
    api_key = await get_setting_value(db, "anthropic_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="Anthropic API key not configured")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    base = "https://api.anthropic.com"

    async with httpx.AsyncClient(timeout=15) as client:
        # 1. Try Admin API — list organizations to get the org id
        try:
            r = await client.get(f"{base}/v1/organizations", headers=headers)
            if r.status_code == 200:
                data = r.json()
                orgs = data if isinstance(data, list) else data.get("data", [])
                if orgs:
                    org = orgs[0]
                    return {
                        "available": True,
                        "balance": org.get("balance") or org.get("credit_balance"),
                        "name": org.get("name", ""),
                        "raw": org,
                    }
        except Exception:
            pass

        # 2. Fallback: verify key works with count_tokens
        try:
            r = await client.post(
                f"{base}/v1/messages/count_tokens",
                json={"model": "claude-3-haiku-20240307", "messages": [{"role": "user", "content": "hi"}]},
                headers=headers,
            )
            key_valid = r.status_code == 200
        except Exception:
            key_valid = False

    # Admin API not accessible — key is regular, not admin
    return {
        "available": False,
        "key_valid": key_valid,
        "message": "Balance unavailable — use an Admin API key (sk-ant-admin…) or check console.anthropic.com/settings/billing",
        "url": "https://console.anthropic.com/settings/billing",
    }


# --- kie.ai ---
@router.get("/kieai/models")
async def get_kieai_models(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Return available kie.ai models and whether the key is configured."""
    from app.llm.kieai import KIEAI_MODELS
    api_key = await get_setting_value(db, "kieai_api_key")
    return {
        "configured": bool(api_key),
        "models": KIEAI_MODELS,
    }


@router.post("/kieai/test")
async def test_kieai_connection(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
    model: str | None = None,
):
    """Test kie.ai API connection using stored key. Optional model param to test a specific model."""
    api_key = await get_setting_value(db, "kieai_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="kie.ai API key not configured")
    from app.llm.kieai import KieAIProvider, KIEAI_MODELS
    valid_ids = {m["id"] for m in KIEAI_MODELS}
    test_model = model if model and model in valid_ids else "gemini-3-pro"
    provider = KieAIProvider(api_key=api_key)
    connected = await provider.check_connection(test_model)
    model_label = next((m["name"] for m in KIEAI_MODELS if m["id"] == test_model), test_model)
    if connected:
        return {"status": "ok", "message": f"{model_label} — connection successful"}
    raise HTTPException(status_code=400, detail=f"{model_label} — connection failed, check your API key")


@router.get("/kieai/balance")
async def get_kieai_balance(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Try to fetch kie.ai balance / credits info."""
    api_key = await get_setting_value(db, "kieai_api_key")
    if not api_key:
        raise HTTPException(status_code=400, detail="kie.ai API key not configured")

    headers = {"Authorization": f"Bearer {api_key}"}
    tried_urls = [
        "https://api.kie.ai/v1/balance",
        "https://api.kie.ai/v1/me",
        "https://api.kie.ai/v1/credits",
        "https://api.kie.ai/v1/dashboard/billing/credit_grants",
    ]

    async with httpx.AsyncClient(timeout=10) as client:
        for url in tried_urls:
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "available": True,
                        "balance": data.get("balance") or data.get("credits") or data.get("total_granted"),
                        "raw": data,
                    }
            except Exception:
                continue

        # Verify key works with a minimal request
        from app.llm.kieai import KieAIProvider
        provider = KieAIProvider(api_key=api_key)
        key_valid = await provider.check_connection("gemini-3-pro")

    return {
        "available": False,
        "key_valid": key_valid,
        "message": "Balance unavailable via API — check kie.ai/market",
        "url": "https://kie.ai/market",
    }


# --- Model Roles ---
@router.get("/model-roles/available")
async def get_available_roles(
    _user: MongoUser = Depends(get_current_user),
):
    """Return the list of all available roles with labels."""
    return [{"role": r, "label": MODEL_ROLE_LABELS.get(r, r)} for r in MODEL_ROLES]


@router.get("/model-roles", response_model=RolesListResponse)
async def get_model_roles(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Return all current role->model assignments."""
    role_service = ModelRoleAssignmentService(db)
    assignments = await role_service.get_all(skip=0, limit=1000)
    # Sort by role
    assignments.sort(key=lambda a: a.role)
    return RolesListResponse(
        assignments=[RoleAssignmentResponse(
            role=a.role,
            label=MODEL_ROLE_LABELS.get(a.role, a.role),
            model_config_id=a.model_config_id,
        ) for a in assignments],
        available_roles=[{"role": r, "label": MODEL_ROLE_LABELS.get(r, r)} for r in MODEL_ROLES],
    )


@router.put("/model-roles", response_model=RolesListResponse)
async def update_model_roles(
    body: RoleAssignmentUpdate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Bulk update role assignments. Expects {assignments: [{role, model_config_id}]}."""
    # Validate roles
    for a in body.assignments:
        if a.role not in MODEL_ROLES:
            raise HTTPException(status_code=400, detail=f"Unknown role: {a.role}")

    role_service = ModelRoleAssignmentService(db)
    
    # Delete all existing assignments
    existing = await role_service.get_all(skip=0, limit=1000)
    for assignment in existing:
        await role_service.delete(assignment.id)

    # Insert new
    for a in body.assignments:
        new_assignment = MongoModelRoleAssignment(role=a.role, model_config_id=a.model_config_id)
        await role_service.create(new_assignment)

    # Return updated list
    assignments = await role_service.get_all(skip=0, limit=1000)
    assignments.sort(key=lambda a: a.role)
    return RolesListResponse(
        assignments=[RoleAssignmentResponse(
            role=a.role,
            label=MODEL_ROLE_LABELS.get(a.role, a.role),
            model_config_id=a.model_config_id,
        ) for a in assignments],
        available_roles=[{"role": r, "label": MODEL_ROLE_LABELS.get(r, r)} for r in MODEL_ROLES],
    )


# --- API Keys ---
@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    apikey_service = ApiKeyService(db)
    all_keys = await apikey_service.get_all(skip=0, limit=1000)
    # Filter by user_id and sort by created_at desc
    user_keys = [k for k in all_keys if k.user_id == user.id]
    user_keys.sort(key=lambda k: k.created_at, reverse=True)
    return user_keys


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    raw_key = generate_api_key()
    apikey_service = ApiKeyService(db)
    api_key = MongoApiKey(
        user_id=user.id,
        name=body.name,
        description=body.description,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:8],
    )
    created = await apikey_service.create(api_key)
    return ApiKeyCreatedResponse(
        id=created.id,
        name=created.name,
        key_prefix=created.key_prefix,
        description=created.description,
        last_used_at=created.last_used_at,
        created_at=created.created_at,
        key=raw_key,
    )


@router.delete("/api-keys/{key_id}", response_model=MessageResponse)
async def delete_api_key(
    key_id: UUID,
    user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    apikey_service = ApiKeyService(db)
    api_key = await apikey_service.get_by_id(str(key_id))
    if not api_key or api_key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    await apikey_service.delete(str(key_id))
    return MessageResponse(message="API key deleted")


# --- System Settings ---

# Default settings seeded on first access
_DEFAULT_SETTINGS = {
    "filesystem_access_enabled": {"value": "false", "description": "Allow full filesystem access (read/write/delete files on host)"},
    "system_access_enabled": {"value": "false", "description": "Allow terminal commands, process management and full system control"},
    "log_retention_days": {"value": "14", "description": "Number of days to retain logs (system, agent, thinking). Older logs are automatically deleted."},
    # Audio / TTS / STT via kie.ai
    "kieai_api_key": {"value": "", "description": "kie.ai API key for TTS/STT and LLM models (GPT-5.2, Gemini 3.1 Pro, Gemini 3 Pro)"},
    "tts_timeout": {"value": "120", "description": "Maximum time (seconds) to wait for TTS audio generation. kie.ai processes async, so longer texts need more time."},
    # Anthropic
    "anthropic_api_key": {"value": "", "description": "Anthropic API key for Claude models (claude-sonnet-4, claude-opus-4, etc.)"},
    # ScrapeCreators — social media video transcripts
    "scrapecreators_api_key": {"value": "", "description": "ScrapeCreators API key for fetching video transcripts from YouTube, TikTok, Instagram, Facebook, Twitter"},
}


async def _ensure_defaults(db: AsyncIOMotorDatabase):
    """Seed default system settings if missing."""
    setting_service = SystemSettingService(db)
    existing_settings = await setting_service.get_all(skip=0, limit=1000)
    existing_keys = {s.key for s in existing_settings}
    for key, cfg in _DEFAULT_SETTINGS.items():
        if key not in existing_keys:
            new_setting = MongoSystemSetting(key=key, value=cfg["value"], description=cfg.get("description"))
            await setting_service.create(new_setting)


async def get_setting_value(db: AsyncIOMotorDatabase, key: str) -> str | None:
    """Helper to read a single setting value."""
    await _ensure_defaults(db)
    setting_service = SystemSettingService(db)
    setting = await setting_service.get_by_key(key)
    return setting.value if setting else None


@router.get("/system", response_model=list[SystemSettingResponse])
async def list_system_settings(
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    await _ensure_defaults(db)
    setting_service = SystemSettingService(db)
    settings = await setting_service.get_all(skip=0, limit=1000)
    settings.sort(key=lambda s: s.key)
    return settings


@router.put("/system/{key}", response_model=SystemSettingResponse)
async def update_system_setting(
    key: str,
    body: SystemSettingUpdate,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    await _ensure_defaults(db)
    setting_service = SystemSettingService(db)
    setting = await setting_service.get_by_key(key)
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    
    updated = await setting_service.update(setting.id, {"value": body.value})
    return updated
