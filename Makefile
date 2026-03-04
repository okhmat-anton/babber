.PHONY: install run run-dev stop stop-dev restart update test lint logs migrate clean

install:
	@echo "=== AI Agents Server — Installation ==="
	@echo ""
	@echo "1. Setting up .env..."
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "   Created .env from .env.example"; \
		echo "   Review .env and adjust values if needed"; \
	else \
		echo "   .env already exists, skipping"; \
	fi
	@echo ""
	@echo "2. Checking Docker..."
	@which docker > /dev/null 2>&1 || (echo "   Docker not found. Install: https://docs.docker.com/get-docker/" && exit 1)
	@docker info > /dev/null 2>&1 || (echo "   Docker daemon is not running. Please start Docker Desktop and try again." && exit 1)
	@echo "   Docker OK"
	@echo ""
	@echo "3. Checking Ollama..."
	@if which ollama > /dev/null 2>&1; then \
		echo "   Ollama OK"; \
	else \
		echo "   Ollama not found. Installing..."; \
		if [ "$$(uname)" = "Darwin" ]; then \
			echo "   Downloading Ollama for macOS..."; \
			curl -fsSL https://ollama.com/install.sh | sh; \
		elif [ "$$(uname)" = "Linux" ]; then \
			echo "   Downloading Ollama for Linux..."; \
			curl -fsSL https://ollama.com/install.sh | sh; \
		else \
			echo "   Auto-install not supported on this OS."; \
			echo "   Please install manually: https://ollama.com/download"; \
			exit 1; \
		fi; \
		if ! which ollama > /dev/null 2>&1; then \
			echo "   Ollama installation failed. Install manually: https://ollama.com/download"; \
			exit 1; \
		fi; \
		echo "   Ollama installed successfully"; \
	fi
	@echo ""
	@echo "4. Checking if Ollama is running..."
	@if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then \
		echo "   Ollama already running"; \
	else \
		echo "   Starting Ollama..."; \
		ollama serve > /dev/null 2>&1 & sleep 3 || true; \
	fi
	@echo ""
	@echo "5. Checking models..."
	@if ollama list 2>/dev/null | grep -q "qwen2.5-coder:14b"; then \
		echo "   qwen2.5-coder:14b already installed"; \
	else \
		read -p "   Download default model qwen2.5-coder:14b (~9GB RAM needed)? [Y/n] " ans; \
		if [ "$$ans" != "n" ] && [ "$$ans" != "N" ]; then \
			echo "   Downloading qwen2.5-coder:14b..."; \
			ollama pull qwen2.5-coder:14b; \
		else \
			read -p "   Enter model name to download (or 'skip'): " model; \
			if [ "$$model" != "skip" ]; then \
				ollama pull $$model; \
			fi; \
		fi; \
	fi
	@echo ""
	@echo "6. Building and starting services..."
	docker compose up -d --build
	@echo ""
	@echo "=== Installation Complete ==="
	@echo "Frontend: http://localhost:4200"
	@echo "Backend:  http://localhost:4700"
	@echo "API Docs: http://localhost:4700/docs"
	@echo "Login:    admin / admin123"

run:
	docker compose up -d --build

run-dev:
	@echo "=== Starting dev mode (infra in Docker, backend+frontend local) ==="
	@echo ""
	@echo "1. Starting infrastructure..."
	docker compose up -d postgres redis chromadb
	@echo "   Waiting for Postgres & Redis..."
	@sleep 3
	@echo ""
	@echo "2. Setting up backend Python environment..."
	@if [ ! -d "backend/.venv" ]; then \
		echo "   Creating virtual environment (Python 3.11)..."; \
		python3.11 -m venv backend/.venv || python3 -m venv backend/.venv; \
	fi
	@echo "   Installing dependencies..."
	@backend/.venv/bin/pip install -q -r backend/requirements.txt 2>/dev/null || backend/.venv/bin/pip install -r backend/requirements.txt
	@echo ""
	@echo "3. Setting up frontend..."
	@if [ ! -d "frontend/node_modules" ]; then \
		echo "   Installing npm packages..."; \
		cd frontend && npm install; \
	fi
	@echo ""
	@echo "4. Starting services..."
	@lsof -ti:4700 | xargs kill -9 2>/dev/null || true
	@lsof -ti:4200 | xargs kill -9 2>/dev/null || true
	@cd backend && PYTHONPATH=. OLLAMA_BASE_URL=http://localhost:11434 CHROMADB_URL=http://localhost:4800 .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 4700 --reload &
	@cd frontend && VITE_BACKEND_URL=http://localhost:4700 npm run dev -- --host 0.0.0.0 --port 4200 &
	@echo ""
	@echo "=== Dev mode running ==="
	@echo "Frontend: http://localhost:4200"
	@echo "Backend:  http://localhost:4700"
	@echo "API Docs: http://localhost:4700/docs"
	@echo ""
	@echo "Press Ctrl+C to stop"
	@wait

stop:
	docker compose down

stop-dev:
	@lsof -ti:4700 | xargs kill -9 2>/dev/null || true
	@lsof -ti:4200 | xargs kill -9 2>/dev/null || true
	@echo "Dev processes stopped"

restart:
	docker compose restart

update:
	git pull
	docker compose up -d --build
	@echo "Installing frontend dependencies..."
	docker compose exec frontend npm install
	@echo "Installing backend dependencies..."
	docker compose exec backend pip install -r requirements.txt
	@echo "Running migrations..."
	docker compose exec backend alembic upgrade head

test:
	docker compose exec backend pytest -v

lint:
	docker compose exec backend ruff check .

logs:
	docker compose logs -f backend

migrate:
	docker compose exec backend alembic upgrade head

clean:
	docker compose down -v
	@echo "All volumes removed"
