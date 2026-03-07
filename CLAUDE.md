# CLAUDE.md — Project Context for AI Agents Server

## Project Overview

AI Agents Server — full-stack platform for managing AI agents with LLM integration (Ollama, OpenAI-compatible). Python FastAPI backend + Vue 3 / Vuetify 3 frontend. All infrastructure runs in Docker, backend and frontend can run locally for dev.

## Quick Start

```bash
make install      # First run: copies .env.example → .env, starts Docker, pulls model
make run          # Production: docker compose up -d --build
make run-dev      # Dev mode: infra in Docker, backend+frontend local with hot reload
make stop-dev     # Kill local dev processes (ports 4700, 4200)
make stop         # docker compose down
make clean        # docker compose down -v (removes all data)
```

## Ports

| Service    | Port |
|------------|------|
| Frontend   | 4200 |
| Backend    | 4700 |
| PostgreSQL | 4532 |
| MongoDB    | 4717 |
| Redis      | 4379 |
| ChromaDB   | 4800 |
| Ollama     | 11434 (host, not Docker) |

## Dev Mode Manual Start

```bash
# Infrastructure
docker compose up -d postgres redis chromadb mongodb

# Backend (PYTHONPATH=. is required!)
cd backend && PYTHONPATH=. OLLAMA_BASE_URL=http://localhost:11434 CHROMADB_URL=http://localhost:4800 \
  .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4700 --reload

# Frontend
cd frontend && VITE_BACKEND_URL=http://localhost:4700 npm run dev -- --host 0.0.0.0 --port 4200
```

## Auth

- Default credentials: `admin` / `admin123`
- JWT: access token 15 min, refresh token 7 days
- All API endpoints require `Authorization: Bearer <token>` except `/api/auth/login` and `/api/auth/refresh`

## Tech Stack

### Backend (`backend/`)
- **Python 3.11** (venv at `backend/.venv`). **Python 3.14 NOT compatible** — pydantic-core build fails.
- FastAPI 0.115.6, SQLAlchemy 2.0.36 async, asyncpg, Pydantic 2.10, Motor 3.6.0 (MongoDB async driver)
- Alembic for migrations, Redis for caching, ChromaDB for vector memory
- `psutil` for system info, `httpx` for HTTP calls to Ollama/LLM

### Frontend (`frontend/`)
- Vue 3.5.13, Vuetify 3.7.6, Pinia 2.3, Vue Router 4.5, Vite 6.0
- `marked` + `dompurify` for markdown rendering in chat
- Axios for API calls, `@mdi/font` for icons
- Vite proxy: `/api` → `VITE_BACKEND_URL` (http://localhost:4700)

### Database
- **PostgreSQL 16**: user `agents`, password `agents_secret_2026`, db `ai_agents`
  - Used for relational data: users, agents, models, skills, chat sessions (foreign keys, joins)
  - All models use UUID primary keys, auto timestamps (`created_at`, `updated_at`)
- **MongoDB 7**: user `agents`, password `mongo_secret_2026`, db `ai_agents`
  - Used for JSON documents: tasks (dynamic result/error fields), autonomous runs, thinking logs
  - Models defined as Pydantic with `to_mongo()` / `from_mongo()` methods for UUID/datetime conversion

## Project Structure

```
backend/
  app/
    main.py              # FastAPI app, lifespan, router registration
    config.py            # Settings (pydantic-settings, reads .env)
    database.py          # async engine, session, init_db, init_redis
    api/                 # Route handlers (one file per domain)
      auth.py            # Login, refresh, change password
      settings.py        # ModelConfig CRUD, ApiKey CRUD, SystemSettings CRUD
      agents.py          # Agent CRUD + execution
      tasks.py           # Task CRUD + scheduling (cron)
      skills.py          # Skill CRUD (Python/JS code)
      chat.py            # Chat sessions, messages, multi-model, auto-title
      ollama.py          # Ollama management (status, models, load/unload, chat)
      filesystem.py      # File browser API (guarded by setting)
      terminal.py        # Terminal exec API (guarded by setting)
      processes.py       # Process list + system info (guarded by setting)
      system.py          # System info endpoint
      memory.py          # ChromaDB vector memory
      logs.py            # Agent log queries
      websocket.py       # WebSocket for real-time updates
    models/              # SQLAlchemy ORM models
      user.py, agent.py, task.py, skill.py, chat.py,
      model_config.py, api_key.py, system_setting.py, log.py, memory.py
    mongodb/             # MongoDB Pydantic models and services
      models.py          # MongoTask with to_mongo()/from_mongo() UUID conversion
      task_service.py    # CRUD operations for tasks using Motor async driver
    llm/                 # LLM provider abstraction
      base.py            # Message, GenerationParams, LLMResponse, LLMProvider protocol
      ollama.py          # OllamaProvider (chat timeout=300s)
      openai_compatible.py  # OpenAICompatibleProvider
    services/            # Business logic
      auth_service.py, model_service.py, skill_service.py, log_service.py
    core/
      dependencies.py    # get_current_user dependency

frontend/
  src/
    main.js              # App entry, Vuetify + Pinia + Router setup
    App.vue              # Root component
    api/                 # Axios instance with auth interceptors
    layouts/
      MainLayout.vue     # Left nav + main content + right chat panel (resizable)
    components/
      ChatPanel.vue      # VS Code-style chat panel (sessions, messages, input)
    views/               # Page components (one per route)
      DashboardView, AgentsView, TasksView, SkillsView, SettingsView,
      ModelsView, ApiKeysView, OllamaView, FileBrowserView, TerminalView,
      SystemView, SystemLogsView, LoginView
    stores/              # Pinia stores
      auth.js, agents.js, tasks.js, skills.js, settings.js, chat.js
    router/index.js      # Route definitions
    plugins/vuetify.js   # Vuetify config (dark theme)
```

## Key Patterns

### Backend
- All API routes prefixed with `/api/`
- Database sessions via `Depends(get_db)` — async SQLAlchemy
- Auth via `Depends(get_current_user)` — JWT from Authorization header
- Feature flags: `filesystem_access_enabled`, `system_access_enabled` in SystemSetting table
- Ollama models auto-synced to `model_configs` table on startup
- For Ollama models: always use `settings.OLLAMA_BASE_URL` at runtime (not stored DB `base_url`) — Docker vs local URLs differ

**Database Strategy:**
- **PostgreSQL** for relational data requiring foreign keys, joins, and referential integrity (users, agents, models, skills, chat sessions)
- **MongoDB** for JSON-heavy documents with dynamic/flexible schemas (tasks with result/error fields, autonomous runs, thinking logs)
- MongoDB access via `from app.database import get_mongodb` — returns Motor AsyncIOMotorDatabase
- MongoDB models use Pydantic with `to_mongo()` / `from_mongo()` for UUID string conversion and datetime ISO formatting

### Frontend
- Vuetify dark theme by default
- Delete confirmations require typing "DELETE"
- Chat panel: fixed right side panel with mouse-drag resize (320–900px), state persisted in localStorage
- Task schedule: human-friendly dropdowns that generate cron expressions
- API calls via Axios instance at `frontend/src/api/index.js` with auto token refresh

## Environment

- `.env.example` is the template (committed to git)
- `.env` is the actual config (gitignored)
- `make install` auto-copies `.env.example` → `.env` if missing
- In dev mode, `OLLAMA_BASE_URL` is overridden to `http://localhost:11434` (instead of Docker's `host.docker.internal`)

## Common Issues

- **PYTHONPATH=.** is required when running backend outside Docker (imports use `app.` prefix)
- **Python 3.14** breaks pydantic-core — use python3.11
- **Ollama model errors** (nodename not known): usually means stored `base_url` = Docker URL used in dev mode. Fixed: `_resolve_model()` now uses runtime `OLLAMA_BASE_URL` for ollama provider
- **Backend pip install fails**: ensure using `backend/.venv/bin/pip`, not system pip
- **Redis import**: use `from app.database import redis_client` (module-level, not function)
- **MongoDB import**: use `from app.database import get_mongodb` — returns AsyncIOMotorDatabase instance
