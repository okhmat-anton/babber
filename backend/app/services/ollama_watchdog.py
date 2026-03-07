"""
Ollama Watchdog — background service for model health monitoring and auto-recovery.

Features:
1. Track manually stopped models vs crashes
2. Auto-restart Ollama if it crashes (not if manually stopped)
3. Auto-restart models that drop from memory (not if manually unloaded)
4. Auto-assign base role when a model starts and no base is assigned
"""
import asyncio
import json
import logging

import httpx

from app.config import get_settings
from app.database import redis_client, get_mongodb
from app.mongodb.models.model_config import MongoModelRoleAssignment
from app.mongodb.services import ModelConfigService, ModelRoleAssignmentService
from app.services.log_service import syslog, syslog_bg

logger = logging.getLogger("ollama_watchdog")

# Redis keys
REDIS_KEY_MANUALLY_STOPPED_MODELS = "ollama:manually_stopped_models"
REDIS_KEY_OLLAMA_MANUALLY_STOPPED = "ollama:manually_stopped"
REDIS_KEY_LAST_KNOWN_RUNNING = "ollama:last_known_running"

# In-memory fallback (used if Redis unavailable)
_manually_stopped_models: set[str] = set()
_ollama_manually_stopped: bool = False
_last_known_running: set[str] = set()

# Watchdog task reference
_watchdog_task: asyncio.Task | None = None

WATCHDOG_INTERVAL = 30  # seconds


# ── Public API for tracking manual actions ──────────────

async def mark_model_manually_stopped(model_name: str):
    """Record that a user manually unloaded this model."""
    _manually_stopped_models.add(model_name)
    try:
        if redis_client:
            await redis_client.sadd(REDIS_KEY_MANUALLY_STOPPED_MODELS, model_name)
    except Exception:
        pass
    logger.info(f"Model '{model_name}' marked as manually stopped")


async def mark_model_started(model_name: str):
    """Remove manual-stop flag when user explicitly loads a model."""
    _manually_stopped_models.discard(model_name)
    try:
        if redis_client:
            await redis_client.srem(REDIS_KEY_MANUALLY_STOPPED_MODELS, model_name)
    except Exception:
        pass


async def mark_ollama_manually_stopped():
    """Record that user manually stopped Ollama."""
    global _ollama_manually_stopped
    _ollama_manually_stopped = True
    try:
        if redis_client:
            await redis_client.set(REDIS_KEY_OLLAMA_MANUALLY_STOPPED, "1")
    except Exception:
        pass
    logger.info("Ollama marked as manually stopped")


async def mark_ollama_manually_started():
    """Clear the manual-stop flag when user starts Ollama."""
    global _ollama_manually_stopped
    _ollama_manually_stopped = False
    try:
        if redis_client:
            await redis_client.delete(REDIS_KEY_OLLAMA_MANUALLY_STOPPED)
    except Exception:
        pass


async def is_model_manually_stopped(model_name: str) -> bool:
    """Check if a model was manually stopped by user."""
    if model_name in _manually_stopped_models:
        return True
    try:
        if redis_client:
            return await redis_client.sismember(REDIS_KEY_MANUALLY_STOPPED_MODELS, model_name)
    except Exception:
        pass
    return False


async def is_ollama_manually_stopped() -> bool:
    """Check if Ollama was manually stopped by user."""
    if _ollama_manually_stopped:
        return True
    try:
        if redis_client:
            val = await redis_client.get(REDIS_KEY_OLLAMA_MANUALLY_STOPPED)
            return val == "1"
    except Exception:
        pass
    return False


async def get_manually_stopped_models() -> set[str]:
    """Get all manually stopped model names."""
    result = set(_manually_stopped_models)
    try:
        if redis_client:
            redis_set = await redis_client.smembers(REDIS_KEY_MANUALLY_STOPPED_MODELS)
            result.update(redis_set)
    except Exception:
        pass
    return result


# ── Last known running models tracking ──────────────────

async def _update_last_known_running(models: set[str]):
    """Update the set of last known running models."""
    global _last_known_running
    _last_known_running = models
    try:
        if redis_client:
            if models:
                await redis_client.delete(REDIS_KEY_LAST_KNOWN_RUNNING)
                await redis_client.sadd(REDIS_KEY_LAST_KNOWN_RUNNING, *models)
            else:
                await redis_client.delete(REDIS_KEY_LAST_KNOWN_RUNNING)
    except Exception:
        pass


async def _get_last_known_running() -> set[str]:
    """Get the set of models that were running in the last check."""
    if _last_known_running:
        return set(_last_known_running)
    try:
        if redis_client:
            return await redis_client.smembers(REDIS_KEY_LAST_KNOWN_RUNNING)
    except Exception:
        pass
    return set()


# ── Ollama helpers ──────────────────────────────────────

async def _check_ollama_running() -> bool:
    """Check if Ollama process is responding."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def _get_running_models() -> set[str]:
    """Get set of model names currently loaded in Ollama."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/ps")
            if r.status_code == 200:
                return {m.get("name", "") for m in r.json().get("models", []) if m.get("name")}
    except Exception:
        pass
    return set()


async def _restart_ollama() -> bool:
    """Try to restart Ollama serve process."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ollama", "serve",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.sleep(3)

        if await _check_ollama_running():
            return True

        # Give more time
        await asyncio.sleep(3)
        return await _check_ollama_running()
    except Exception as e:
        logger.error(f"Failed to restart Ollama: {e}")
        return False


async def _load_model(model_name: str) -> bool:
    """Try to load a model into Ollama memory."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={"model": model_name, "prompt": "", "keep_alive": "10m"},
                timeout=120,
            )
            return r.status_code == 200
    except Exception as e:
        logger.error(f"Failed to load model '{model_name}': {e}")
        return False


# ── Auto-assign base role ──────────────────────────────

async def _auto_assign_base_if_needed(running_models: set[str]):
    """If no base role is assigned, auto-assign the first running ollama model.
    If base role is assigned to an Ollama model that is not running,
    attempt to load it (unless manually stopped)."""
    try:
        db = get_mongodb()
        role_svc = ModelRoleAssignmentService(db)
        mc_svc = ModelConfigService(db)

        # Check if base role is already assigned
        existing = await role_svc.find_one({"role": "base"})
        if existing:
            # Base role exists — check if the model is still valid
            model = await mc_svc.get_by_id(existing.model_config_id)
            if model and model.is_active:
                # If it's an ollama model, check if it's running
                if model.provider == "ollama" and model.model_id in running_models:
                    return  # Base model is fine
                elif model.provider != "ollama":
                    return  # API model, always available
                # Base model is Ollama but NOT running — try to load it
                if model.provider == "ollama" and model.model_id not in running_models:
                    manually_stopped = await is_model_manually_stopped(model.model_id)
                    if not manually_stopped:
                        logger.warning(
                            f"Base model '{model.model_id}' is not running — attempting auto-load"
                        )
                        await syslog(
                            "warning",
                            f"Base model '{model.name}' ({model.model_id}) not running — auto-loading",
                            source="ollama_watchdog",
                        )
                        success = await _load_model(model.model_id)
                        if success:
                            running_models.add(model.model_id)
                            logger.info(f"Base model '{model.model_id}' auto-loaded successfully")
                            await syslog(
                                "info",
                                f"Base model '{model.name}' auto-loaded successfully",
                                source="ollama_watchdog",
                            )
                        else:
                            logger.error(f"Failed to auto-load base model '{model.model_id}'")
                            await syslog(
                                "error",
                                f"Failed to auto-load base model '{model.name}'",
                                source="ollama_watchdog",
                            )
                    return
                return
            # Model deleted or inactive — fall through to reassign

        # Find first running ollama model in model_configs
        for model_name in sorted(running_models):
            mc = await mc_svc.find_one({
                "provider": "ollama",
                "model_id": model_name,
                "is_active": True,
            })
            if mc:
                if existing:
                    await role_svc.update(existing.id, {"model_config_id": mc.id})
                else:
                    new_assignment = MongoModelRoleAssignment(
                        role="base", model_config_id=mc.id
                    )
                    await role_svc.create(new_assignment)
                await syslog("info",
                             f"Auto-assigned base role to running model: {mc.name} ({mc.model_id})",
                             source="ollama_watchdog")
                logger.info(f"Auto-assigned base role to: {mc.name}")
                return

        # No running ollama model found — try first active API model
        if not existing:
            all_models = await mc_svc.get_all(filter={"provider": {"$ne": "ollama"}, "is_active": True}, limit=1)
            if all_models:
                api_model = all_models[0]
                new_assignment = MongoModelRoleAssignment(
                    role="base", model_config_id=api_model.id
                )
                await role_svc.create(new_assignment)
                await syslog("info",
                             f"Auto-assigned base role to API model: {api_model.name}",
                             source="ollama_watchdog")
                logger.info(f"Auto-assigned base role to API: {api_model.name}")
    except Exception as e:
        logger.error(f"Error in auto-assign base: {e}")


# ── Watchdog loop ──────────────────────────────────────

async def _watchdog_loop():
    """Main watchdog loop — runs every WATCHDOG_INTERVAL seconds."""

    # Wait for startup to complete
    await asyncio.sleep(10)

    while True:
        try:
            await _watchdog_tick()
        except asyncio.CancelledError:
            logger.info("Watchdog cancelled")
            return
        except Exception as e:
            logger.error(f"Watchdog tick error: {e}")

        await asyncio.sleep(WATCHDOG_INTERVAL)


async def _watchdog_tick():
    """Single watchdog check cycle."""

    ollama_running = await _check_ollama_running()
    manually_stopped = await is_ollama_manually_stopped()

    # ── 1. Auto-restart Ollama if crashed ──
    if not ollama_running and not manually_stopped:
        logger.warning("Ollama is not running and was not manually stopped — attempting restart")
        await syslog("warning", "Ollama crashed — attempting auto-restart", source="ollama_watchdog")

        success = await _restart_ollama()
        if success:
            logger.info("Ollama auto-restarted successfully")
            await syslog("info", "Ollama auto-restarted successfully", source="ollama_watchdog")
            ollama_running = True
        else:
            logger.error("Failed to auto-restart Ollama")
            await syslog("error", "Failed to auto-restart Ollama", source="ollama_watchdog")
            return

    if not ollama_running:
        # Ollama is down and manually stopped — don't do anything
        return

    # ── 2. Get current running models ──
    current_running = await _get_running_models()
    previous_running = await _get_last_known_running()
    stopped_models = await get_manually_stopped_models()

    # ── 3. Detect dropped models and auto-restart ──
    if previous_running:
        dropped = previous_running - current_running
        for model_name in dropped:
            if model_name in stopped_models:
                logger.debug(f"Model '{model_name}' was manually stopped, skipping auto-restart")
                continue

            logger.warning(f"Model '{model_name}' dropped from memory — attempting auto-restart")
            await syslog("warning",
                         f"Model '{model_name}' dropped from memory — attempting auto-restart",
                         source="ollama_watchdog")

            success = await _load_model(model_name)
            if success:
                current_running.add(model_name)
                logger.info(f"Model '{model_name}' auto-restarted successfully")
                await syslog("info",
                             f"Model '{model_name}' auto-restarted successfully",
                             source="ollama_watchdog")
            else:
                logger.error(f"Failed to auto-restart model '{model_name}'")
                await syslog("error",
                             f"Failed to auto-restart model '{model_name}'",
                             source="ollama_watchdog")

    # ── 4. Auto-assign base role / auto-load base model if needed ──
    await _auto_assign_base_if_needed(current_running)

    # ── 5. Update last known running models ──
    await _update_last_known_running(current_running)

# ── Lifecycle ──────────────────────────────────────────

async def start_watchdog():
    """Start the watchdog background task."""
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        return
    _watchdog_task = asyncio.create_task(_watchdog_loop())
    logger.info("Ollama watchdog started (interval=%ds)", WATCHDOG_INTERVAL)


async def stop_watchdog():
    """Stop the watchdog background task."""
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass
    _watchdog_task = None
    logger.info("Ollama watchdog stopped")
