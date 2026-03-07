<p align="center">
  <h1 align="center">🤖 AI Agents Server</h1>
  <p align="center">
    <strong>Self-hosted platform for creating, managing, and running autonomous AI agents</strong>
  </p>
  <p align="center">
    <a href="#features">Features</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#installation">Installation</a> •
    <a href="#development">Development</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#api">API</a> •
    <a href="#license">License</a>
  </p>
</p>

---

## What is AI Agents Server?

AI Agents Server is a **fully self-hosted, open-source platform** for building and running AI agents powered by local LLMs (via [Ollama](https://ollama.com)) or any OpenAI-compatible API. No cloud dependencies, no API costs — your data stays on your machine.

Think of it as your personal AI workforce: create agents with unique personalities, give them skills (tools), assign tasks, and let them work autonomously — complete with long-term memory, thinking protocols, and project management.

### Who is this for?

- **Developers** who want to experiment with AI agents locally
- **Researchers** exploring autonomous AI behavior, beliefs, and reasoning
- **Teams** that need a private, self-hosted AI agent management system
- **Hobbyists** who want to run powerful AI agents without cloud subscriptions

---

## Features

### 🧠 Intelligent Agents
- Create agents with custom personalities, system prompts, and generation parameters
- **Belief System** — define core (immutable) and additional (mutable) beliefs for each agent
- **Aspirations** — set dreams, desires, and goals that guide agent behavior
- **Multi-Model Support** — assign different LLM models for different roles (primary, analytical, creative)
- Per-agent access controls (filesystem, system)

### 🔧 Skills System
- Extensible tool/skill framework — agents can use skills to interact with the world
- Built-in skills: web fetch, file read/write, shell execution, code execution, memory store/search, project file management, text summarization
- Create custom skills with Python code and JSON schemas
- Agents select and invoke skills autonomously during conversations

### 🧪 Thinking Protocols
- Define step-by-step reasoning workflows for agents
- **Standard** protocols — structured analysis and research flows
- **Orchestrator** protocols — meta-protocols that delegate to child protocols
- **Loop** protocols — autonomous work cycles where agents self-direct
- Full thinking log visibility for debugging and research

### 💬 Chat Interface
- VS Code-style resizable chat panel
- Persistent chat sessions with full history
- Multi-model chat — compare responses from different models side by side
- Multi-agent chat — have several agents collaborate in one session
- Automatic session titles via LLM
- Markdown rendering with syntax highlighting

### 🚀 Autonomous Execution
- Agents can run autonomously — processing tasks, making decisions, writing code
- Built-in project system — agents write code to isolated project directories
- Task management with scheduling (cron expressions)
- Real-time progress via WebSocket

### 🧬 Long-Term Memory
- **Vector Memory** (ChromaDB) — semantic search across agent memories
- **Knowledge Graph** — typed links between memory records
- Memory categories, tags, importance scoring
- Deep memory processing — agents analyze and connect their own memories

### 🏗️ Infrastructure
- Full **Docker Compose** setup — one command to run everything
- **PostgreSQL** for relational data, **MongoDB** for JSON documents (tasks, logs)
- **Redis** for caching, **ChromaDB** for vector embeddings
- Ollama integration with auto-model sync, health monitoring, and watchdog
- Alembic database migrations
- Swagger/ReDoc API documentation

### 🖥️ Admin Dashboard
- Modern dark-themed UI (Vue 3 + Vuetify 3)
- Dashboard with system overview
- Agent management with avatar support
- Skill editor with CodeMirror
- Model management (Ollama + external APIs)
- System logs, file browser, terminal, process monitor
- Project browser for agent-generated code

---

## Quick Start

The fastest way to get running (requires Docker and Ollama):

```bash
git clone https://github.com/okhmat-anton/ai-agents-server.git
cd ai-agents-server
make install
```

This will:
1. Create `.env` from template
2. Check/install Ollama
3. Offer to download a default model (`qwen2.5-coder:14b`)
4. Build and start all services

Then open: **http://localhost:4200**  
Login: `admin` / `admin123`

---

## Installation

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Docker** | 20.10+ | [Install Docker](https://docs.docker.com/get-docker/) |
| **Docker Compose** | v2+ | Included with Docker Desktop |
| **Ollama** | Latest | [Install Ollama](https://ollama.com/download) |
| **RAM** | 8 GB+ | 16 GB+ recommended for 14B models |
| **Disk** | 10 GB+ | Models take 4–9 GB each |

> 💡 Ollama is required for local LLM inference. You can also use any OpenAI-compatible API (GPT-4, Claude, Mistral, etc.) by configuring external model providers in the UI.

---

### macOS

#### 1. Install Docker Desktop

```bash
# Download and install from:
# https://www.docker.com/products/docker-desktop/
# Or with Homebrew:
brew install --cask docker
```

Launch Docker Desktop and wait for it to start.

#### 2. Install Ollama

```bash
# Download from https://ollama.com/download/mac
# Or with Homebrew:
brew install ollama
```

Start Ollama:
```bash
ollama serve
```

Pull a model (in another terminal):
```bash
# Recommended for coding tasks (requires ~9 GB RAM):
ollama pull qwen2.5-coder:14b

# Lighter alternative (~4 GB RAM):
ollama pull qwen2.5-coder:7b

# Or any model you prefer:
ollama pull llama3.1:8b
```

#### 3. Clone and Run

```bash
git clone https://github.com/okhmat-anton/ai-agents-server.git
cd ai-agents-server
make install
```

#### 4. Open the App

- **Frontend:** http://localhost:4200
- **Backend API:** http://localhost:4700
- **API Docs:** http://localhost:4700/docs
- **Login:** `admin` / `admin123`

---

### Linux (Ubuntu / Debian)

#### 1. Install Docker

```bash
# Install Docker Engine
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Verify
docker --version
docker compose version
```

#### 2. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Start Ollama:
```bash
ollama serve &
```

Pull a model:
```bash
ollama pull qwen2.5-coder:14b
# Or a lighter model:
ollama pull qwen2.5-coder:7b
```

#### 3. Clone and Run

```bash
git clone https://github.com/okhmat-anton/ai-agents-server.git
cd ai-agents-server
make install
```

#### 4. Open the App

- **Frontend:** http://localhost:4200
- **Backend API:** http://localhost:4700
- **API Docs:** http://localhost:4700/docs
- **Login:** `admin` / `admin123`

> **Note for Linux:** If Ollama is running on the same host, the default `OLLAMA_BASE_URL=http://host.docker.internal:11434` in `.env` should work with Docker Desktop. On plain Docker Engine, you may need to change it to `http://172.17.0.1:11434` or your host IP.

---

### Windows

#### 1. Install Docker Desktop

Download and install **Docker Desktop for Windows** from:  
https://www.docker.com/products/docker-desktop/

- Enable **WSL 2 backend** during installation (recommended)
- Launch Docker Desktop and wait for it to start

#### 2. Install Ollama

Download and install from: https://ollama.com/download/windows

After installation, Ollama runs as a system service. Open PowerShell:

```powershell
# Verify Ollama is running
ollama list

# Pull a model
ollama pull qwen2.5-coder:14b
# Or lighter:
ollama pull qwen2.5-coder:7b
```

#### 3. Install Git (if not already installed)

```powershell
# Download from https://git-scm.com/download/win
# Or with winget:
winget install Git.Git
```

#### 4. Install Make (optional but recommended)

```powershell
# Option A: Install via Chocolatey
choco install make

# Option B: Install via winget
winget install GnuWin32.Make
```

If you don't have `make`, see the [Manual Setup](#manual-setup-without-make) section below.

#### 5. Clone and Run

Open **Git Bash** or **WSL** terminal:

```bash
git clone https://github.com/okhmat-anton/ai-agents-server.git
cd ai-agents-server
make install
```

#### 6. Open the App

- **Frontend:** http://localhost:4200
- **Backend API:** http://localhost:4700
- **API Docs:** http://localhost:4700/docs
- **Login:** `admin` / `admin123`

---

### Manual Setup (without Make)

If you can't use `make`, run these commands manually:

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Review and edit .env if needed
#    (default values work for local development)

# 3. Make sure Ollama is running
ollama serve

# 4. Pull a model
ollama pull qwen2.5-coder:14b

# 5. Start all services with Docker Compose
docker compose up -d --build

# 6. Open http://localhost:4200
```

---

## Configuration

All configuration is managed via the `.env` file in the project root.

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_PORT` | `4700` | Backend API port |
| `FRONTEND_PORT` | `4200` | Frontend UI port |
| `POSTGRES_PORT` | `4532` | PostgreSQL port |
| `REDIS_PORT` | `4379` | Redis port |
| `CHROMADB_PORT` | `4800` | ChromaDB vector database port |
| `MONGO_PORT` | `4717` | MongoDB port |
| `POSTGRES_USER` | `agents` | Database username |
| `POSTGRES_PASSWORD` | `agents_secret_2026` | Database password |
| `POSTGRES_DB` | `ai_agents` | Database name |
| `REDIS_PASSWORD` | `redis_secret_2026` | Redis password |
| `MONGO_USER` | `agents` | MongoDB username |
| `MONGO_PASSWORD` | `mongo_secret_2026` | MongoDB password |
| `MONGO_DB` | `ai_agents` | MongoDB database name |
| `JWT_SECRET_KEY` | `super-secret-jwt-key-...` | **Change in production!** |
| `DEFAULT_ADMIN_USERNAME` | `admin` | Default admin login |
| `DEFAULT_ADMIN_PASSWORD` | `admin123` | **Change in production!** |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama API URL |

> ⚠️ **Production:** Always change `JWT_SECRET_KEY`, `DEFAULT_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, and `MONGO_PASSWORD` before deploying.

---

## Development

### Dev Mode (Hot Reload)

For active development, run infrastructure in Docker and backend/frontend locally with hot reload:

```bash
make run-dev
```

This starts:
- **PostgreSQL, Redis, ChromaDB** — in Docker containers
- **Backend** — locally with `uvicorn --reload` (Python 3.11)
- **Frontend** — locally with `vite` hot module replacement

### Manual Dev Setup

```bash
# Start infrastructure
docker compose up -d postgres redis chromadb

# Backend (requires Python 3.11)
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
PYTHONPATH=. OLLAMA_BASE_URL=http://localhost:11434 CHROMADB_URL=http://localhost:4800 \
  uvicorn app.main:app --host 0.0.0.0 --port 4700 --reload

# Frontend (in another terminal)
cd frontend
npm install
VITE_BACKEND_URL=http://localhost:4700 npm run dev -- --host 0.0.0.0 --port 4200
```

### Common Commands

| Command | Description |
|---------|-------------|
| `make install` | First-time setup (env, Docker, Ollama, models) |
| `make run` | Production: start all services via Docker |
| `make run-dev` | Dev mode: infra in Docker, backend+frontend local |
| `make stop` | Stop Docker services |
| `make stop-dev` | Kill local dev processes (ports 4700, 4200) |
| `make restart` | Restart Docker services |
| `make update` | Pull latest code, install deps, rebuild |
| `make migrate` | Run database migrations |
| `make logs` | Follow backend logs |
| `make test` | Run backend tests |
| `make lint` | Run linter (ruff) |
| `make clean` | Stop and remove all volumes (⚠️ deletes data) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│                  Vue 3 + Vuetify 3 + Pinia                  │
│                   http://localhost:4200                      │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API + WebSocket
┌────────────────────────▼────────────────────────────────────┐
│                        Backend                              │
│                  FastAPI + SQLAlchemy                        │
│                   http://localhost:4700                      │
│                                                             │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  Auth   │  │  Agents  │  │  Skills  │  │    Chat     │  │
│  │ Service │  │  Engine  │  │  Runner  │  │   Engine    │  │
│  └─────────┘  └──────────┘  └──────────┘  └─────────────┘  │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │  Tasks  │  │  Memory  │  │ Thinking │  │ Autonomous  │  │
│  │ Scheduler│ │  Service │  │ Protocols│  │   Runner    │  │
│  └─────────┘  └──────────┘  └──────────┘  └─────────────┘  │
└───┬──────────────┬──────────────┬───────────────┬───────────┘
    │              │              │               │
┌───▼───┐   ┌─────▼─────┐  ┌────▼────┐  ┌───▼────┐  ┌──────▼──────┐
│Postgres│  │  MongoDB  │  │  Redis  │  │ChromaDB│  │   Ollama    │
│ :4532  │  │   :4717   │  │  :4379  │  │ :4800  │  │  :11434     │
│Relational│ │ Documents │  │  Cache  │  │Vectors │  │  Local LLM  │
└────────┘  └───────────┘  └─────────┘  └────────┘  └─────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Vue 3.5, Vuetify 3.7, Pinia 2.3, Vue Router 4, Vite 6, CodeMirror 6 |
| **Backend** | Python 3.11, FastAPI 0.115, SQLAlchemy 2.0 (async), Pydantic 2.10, Motor 3.6 |
| **Database** | PostgreSQL 16 (relational), MongoDB 7 (documents) |
| **Cache** | Redis 7 |
| **Vector DB** | ChromaDB |
| **LLM** | Ollama (local) + any OpenAI-compatible API |
| **Migrations** | Alembic |
| **Container** | Docker Compose |

---

## API

Full interactive API documentation is available at:

- **Swagger UI:** http://localhost:4700/docs
- **ReDoc:** http://localhost:4700/redoc

### Key API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/login` | Authenticate and get JWT tokens |
| `GET /api/agents` | List all agents |
| `POST /api/agents` | Create a new agent |
| `POST /api/agents/{id}/execute` | Execute agent |
| `GET /api/agents/{id}/memory` | Agent memory records |
| `GET /api/chat/sessions` | Chat sessions |
| `POST /api/chat/sessions/{id}/messages` | Send a message |
| `GET /api/skills` | List available skills |
| `GET /api/tasks` | List tasks |
| `GET /api/ollama/status` | Ollama health status |
| `GET /api/ollama/models` | Available models |
| `GET /api/system/info` | System information |

All endpoints (except auth) require `Authorization: Bearer <token>` header.

---

## Troubleshooting

### Ollama connection issues

If agents can't connect to Ollama, check the `OLLAMA_BASE_URL` in `.env`:

```bash
# macOS / Windows (Docker Desktop):
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Linux (Docker Engine without Docker Desktop):
OLLAMA_BASE_URL=http://172.17.0.1:11434
# Or use your host machine's IP address
```

### Python version

The backend requires **Python 3.11**. Python 3.14 is not supported (pydantic-core build fails).

### Backend can't find modules

When running the backend locally (outside Docker), `PYTHONPATH=.` is required:

```bash
cd backend
PYTHONPATH=. .venv/bin/uvicorn app.main:app --port 4700
```

### Database reset

To completely reset all data:

```bash
make clean    # Removes all Docker volumes
make run      # Recreate fresh
```

### Port conflicts

If default ports are in use, change them in `.env`:

```env
BACKEND_PORT=4701
FRONTEND_PORT=4201
POSTGRES_PORT=4533
```

---

## Project Structure

```
ai-agents-server/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── api/               # Route handlers (one file per domain)
│   │   ├── core/              # Auth dependencies, security
│   │   ├── llm/               # LLM provider abstraction (Ollama, OpenAI)
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── services/          # Business logic layer
│   │   ├── migrations/        # Alembic database migrations
│   │   ├── config.py          # Settings (reads .env)
│   │   ├── database.py        # DB engine, sessions, Redis
│   │   └── main.py            # FastAPI app & lifespan
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                   # Vue 3 SPA
│   ├── src/
│   │   ├── api/               # Axios instance + interceptors
│   │   ├── components/        # Reusable components (ChatPanel, etc.)
│   │   ├── layouts/           # App layout (sidebar + chat panel)
│   │   ├── views/             # Page components
│   │   ├── stores/            # Pinia state management
│   │   ├── router/            # Vue Router config
│   │   └── plugins/           # Vuetify setup
│   ├── package.json
│   └── Dockerfile
├── data/                       # Runtime data (agents, skills, projects)
│   ├── agents/                # Agent configs, beliefs, aspirations
│   ├── skills/                # Custom skill code
│   └── projects/              # Agent-generated project code
├── docker-compose.yml
├── Makefile
├── .env.example               # Environment template
└── README.md
```

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <sub>Built with ❤️ using FastAPI, Vue 3, Ollama, and PostgreSQL</sub>
</p>
