import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import get_settings

# Configure app-level logging so watchdog and other services can log
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
from app.database import init_db, init_redis, async_session
from app.services.auth_service import create_default_admin
from app.services.skill_service import create_system_skills
from app.services.model_service import sync_ollama_models
from app.services.log_service import syslog_bg
from app.services.protocol_service import create_default_protocols

from app.api.auth import router as auth_router
from app.api.settings import router as settings_router
from app.api.agents import router as agents_router
from app.api.tasks import common_router as tasks_router, agent_task_router
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
from app.api.thinking_logs import agent_thinking_router, session_thinking_router
from app.api.autonomous import router as autonomous_router

from app.services.ollama_watchdog import start_watchdog, stop_watchdog

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_redis()
    await init_db()

    # Create default admin & system skills
    async with async_session() as db:
        await create_default_admin(db)
        await create_system_skills(db)
        await sync_ollama_models(db)
        await create_default_protocols(db)

    await syslog_bg("info", "Server started", source="system", metadata={"version": settings.APP_VERSION})

    # Start Ollama watchdog (auto-recovery, monitoring)
    await start_watchdog()

    yield

    # Shutdown
    await stop_watchdog()
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
app.include_router(autonomous_router)


@app.get("/")
async def root():
    return {"message": settings.APP_TITLE, "version": settings.APP_VERSION, "docs": "/docs"}
