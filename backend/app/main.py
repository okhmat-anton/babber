import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.config import get_settings

# Configure app-level logging so watchdog and other services can log
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
from app.database import init_redis, init_mongodb, get_mongodb
from app.services.auth_service import create_default_admin
from app.services.skill_service import create_system_skills
from app.services.model_service import sync_ollama_models
from app.services.log_service import syslog_bg
from app.services.protocol_service import create_default_protocols, deduplicate_protocols

from app.api.auth import router as auth_router
from app.api.settings import router as settings_router
from app.api.agents import router as agents_router
from app.api.tasks_mongo import common_router as tasks_router, agent_task_router
from app.api.skills import router as skills_router, agent_skill_router
from app.api.logs import agent_log_router
from app.api.system import router as system_router
from app.api.memory import router as memory_router
from app.api.websocket import router as ws_router
from app.api.ollama import router as ollama_router
from app.api.filesystem import router as fs_router
from app.api.terminal import router as terminal_router
from app.api.processes import router as processes_router
from app.api.chat import router as chat_router
from app.api.skill_files import router as skill_files_router
from app.api.agent_files import router as agent_files_router
from app.api.agent_beliefs import router as agent_beliefs_router
from app.api.agent_aspirations import router as agent_aspirations_router
from app.api.protocols import router as protocols_router
from app.api.thinking_logs import agent_thinking_router, session_thinking_router, chat_thinking_router
from app.api.autonomous import router as autonomous_router
from app.api.projects import router as projects_router
from app.api.agent_errors import agent_error_router, all_errors_router
from app.api.messengers import router as messengers_router
from app.api.audio import router as audio_router
from app.api.creator import router as creator_router

from app.services.ollama_watchdog import start_watchdog, stop_watchdog

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_redis()
    await init_mongodb()

    # Create default admin & system skills
    mongodb = get_mongodb()
    await create_default_admin(mongodb)
    await create_system_skills(mongodb)
    await sync_ollama_models(mongodb)
    await create_default_protocols(mongodb)
    removed = await deduplicate_protocols(mongodb)
    if removed:
        await syslog_bg("info", f"Removed {removed} duplicate protocol(s)", source="system")

    # Settings migrated to MongoDB
    from app.api.settings import get_setting_value, _ensure_defaults
    await _ensure_defaults(mongodb)
    retention_str = await get_setting_value(mongodb, "log_retention_days")
    retention_days = int(retention_str) if retention_str and retention_str.isdigit() else 14

    # Note: File-based logs don't need automatic cleanup
    # TODO: Implement log rotation if needed

    # Clean up orphaned autonomous runs (e.g. from server restart during active run)
    from app.services.autonomous_runner import cleanup_orphaned_runs
    orphaned = await cleanup_orphaned_runs()
    if orphaned:
        await syslog_bg("warning", f"Cleaned up {orphaned} orphaned autonomous run(s)",
                        source="autonomous", metadata={"orphaned_count": orphaned})

    await syslog_bg("info", "Server started", source="system", metadata={"version": settings.APP_VERSION})

    # Start Ollama watchdog (auto-recovery, monitoring)
    await start_watchdog()

    yield

    # Shutdown
    await stop_watchdog()
    from app.services.telegram_service import stop_all_clients
    await stop_all_clients()
    await syslog_bg("info", "Server shutting down", source="system")


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/system/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Error-logging middleware ----------
@app.middleware("http")
async def log_errors_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            await syslog_bg(
                "error",
                f"{request.method} {request.url.path} -> {response.status_code}",
                source="api",
                metadata={"method": request.method, "path": request.url.path, "status": response.status_code},
            )
        return response
    except Exception as exc:
        await syslog_bg(
            "critical",
            f"Unhandled exception on {request.method} {request.url.path}: {exc}",
            source="api",
            metadata={"method": request.method, "path": request.url.path, "error": str(exc)},
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Include routers
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(agents_router)
app.include_router(agent_files_router)
app.include_router(agent_beliefs_router)
app.include_router(agent_aspirations_router)
app.include_router(tasks_router)
app.include_router(agent_task_router)
app.include_router(skills_router)
app.include_router(skill_files_router)
app.include_router(agent_skill_router)
app.include_router(agent_log_router)
app.include_router(system_router)
app.include_router(memory_router)
app.include_router(ws_router)
app.include_router(ollama_router)
app.include_router(fs_router)
app.include_router(terminal_router)
app.include_router(processes_router)
app.include_router(chat_router)
app.include_router(protocols_router)
app.include_router(agent_thinking_router)
app.include_router(session_thinking_router)
app.include_router(chat_thinking_router)
app.include_router(autonomous_router)
app.include_router(projects_router)
app.include_router(agent_error_router)
app.include_router(all_errors_router)
app.include_router(messengers_router)
app.include_router(audio_router)
app.include_router(creator_router)

# Serve uploaded files (avatars, etc.) from data/agents/ directory
_uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "agents")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/api/uploads/agents", StaticFiles(directory=_uploads_dir), name="uploads_agents")

# Serve audio files from data/audio/ directory
_audio_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "audio")
os.makedirs(_audio_dir, exist_ok=True)
app.mount("/api/uploads/audio", StaticFiles(directory=_audio_dir), name="uploads_audio")

# Serve chat media files (voice, photos, videos, documents from messengers)
_chat_media_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "chat_media")
os.makedirs(_chat_media_dir, exist_ok=True)
app.mount("/api/uploads/chat_media", StaticFiles(directory=_chat_media_dir), name="uploads_chat_media")


@app.get("/")
async def root():
    return {"message": settings.APP_TITLE, "version": settings.APP_VERSION, "docs": "/docs"}
