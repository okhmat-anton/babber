"""
Projects API — filesystem-based project management for agent code development.

Storage layout:
  data/projects/<slug>/
    project.json    — project config (name, description, goals, criteria, settings)
    tasks.json      — backlog tasks with statuses
    logs.json       — project activity logs
    code/           — all source code files
"""
import asyncio
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])
settings = get_settings()

LANGUAGE_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".jsx": "javascript",
    ".tsx": "typescript", ".vue": "vue", ".svelte": "svelte",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".md": "markdown", ".txt": "text", ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".sql": "sql", ".xml": "xml", ".csv": "text",
    ".env": "shell", ".cfg": "ini", ".ini": "ini",
    ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".dockerfile": "dockerfile", ".log": "text",
    ".r": "r", ".R": "r", ".m": "matlab",
}

TASK_STATUSES = ["backlog", "todo", "in_progress", "review", "done", "cancelled"]
TASK_PRIORITIES = ["lowest", "low", "medium", "high", "highest"]
PROJECT_STATUSES = ["active", "paused", "completed", "archived"]
ACCESS_LEVELS = ["full", "restricted"]  # full = all agents, restricted = listed agents only


# ── Helpers ─────────────────────────────────────────────

def _get_language(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return LANGUAGE_MAP.get(ext, "text")


def _ensure_projects_dir():
    Path(settings.PROJECTS_DIR).mkdir(parents=True, exist_ok=True)


def _get_project_dir(slug: str) -> Path:
    base = Path(settings.PROJECTS_DIR).resolve()
    project_dir = (base / slug).resolve()
    if not str(project_dir).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid project slug")
    return project_dir


def _resolve_code_path(project_dir: Path, rel_path: str) -> Path:
    code_dir = (project_dir / "code").resolve()
    resolved = (code_dir / rel_path).resolve()
    if not str(resolved).startswith(str(code_dir)):
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    return resolved


def _slug_from_name(name: str) -> str:
    """Generate a filesystem-safe slug from project name."""
    import re
    slug = name.strip().lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = slug.strip('-')
    return slug or f"project-{uuid.uuid4().hex[:8]}"


def _read_project_json(project_dir: Path) -> dict:
    path = project_dir / "project.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_project_json(project_dir: Path, data: dict):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    (project_dir / "project.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_tasks_json(project_dir: Path) -> list[dict]:
    path = project_dir / "tasks.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_tasks_json(project_dir: Path, tasks: list[dict]):
    (project_dir / "tasks.json").write_text(
        json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _read_logs_json(project_dir: Path) -> list[dict]:
    path = project_dir / "logs.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _write_logs_json(project_dir: Path, logs: list[dict]):
    (project_dir / "logs.json").write_text(
        json.dumps(logs, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _add_log(project_dir: Path, level: str, message: str, source: str = "system"):
    logs = _read_logs_json(project_dir)
    logs.append({
        "id": uuid.uuid4().hex[:12],
        "level": level,
        "message": message,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    # Keep last 500 log entries
    if len(logs) > 500:
        logs = logs[-500:]
    _write_logs_json(project_dir, logs)


def _scan_code_dir(base_dir: Path, current_dir: Path) -> list[dict]:
    """Recursively scan code directory and return file tree."""
    items = []
    try:
        entries = sorted(current_dir.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return items
    for entry in entries:
        rel_path = str(entry.relative_to(base_dir))
        if entry.is_dir():
            children = _scan_code_dir(base_dir, entry)
            items.append({
                "name": entry.name, "path": rel_path, "is_dir": True,
                "size": 0, "language": "", "children": children,
            })
        else:
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            items.append({
                "name": entry.name, "path": rel_path, "is_dir": False,
                "size": size, "language": _get_language(entry.name),
            })
    return items


def _get_project_or_404(slug: str) -> tuple[Path, dict]:
    """Get project directory and config, or raise 404."""
    _ensure_projects_dir()
    project_dir = _get_project_dir(slug)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    config = _read_project_json(project_dir)
    if not config:
        raise HTTPException(status_code=404, detail="Project config not found")
    return project_dir, config


def _enrich_project(config: dict, project_dir: Path) -> dict:
    """Add computed fields to project config for API response."""
    tasks = _read_tasks_json(project_dir)
    code_dir = project_dir / "code"

    # Count files in code dir
    file_count = 0
    if code_dir.exists():
        for _, _, files in os.walk(code_dir):
            file_count += len(files)

    config["task_stats"] = {
        "total": len(tasks),
        "backlog": sum(1 for t in tasks if t.get("status") == "backlog"),
        "todo": sum(1 for t in tasks if t.get("status") == "todo"),
        "in_progress": sum(1 for t in tasks if t.get("status") == "in_progress"),
        "review": sum(1 for t in tasks if t.get("status") == "review"),
        "done": sum(1 for t in tasks if t.get("status") == "done"),
        "cancelled": sum(1 for t in tasks if t.get("status") == "cancelled"),
    }
    config["file_count"] = file_count
    # Migrate legacy string tech_stack to list
    ts = config.get("tech_stack", [])
    if isinstance(ts, str):
        config["tech_stack"] = [t.strip() for t in ts.split(",") if t.strip()] if ts else []
    return config


# ── Schemas ─────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    goals: str = ""
    success_criteria: str = ""
    tech_stack: list[str] = []
    status: str = "active"
    access_level: str = "full"  # full = all agents, restricted = listed agents
    allowed_agent_ids: list[str] = []
    lead_agent_id: Optional[str] = None  # agent designated as lead for this project
    execution_access: str = "restricted"  # restricted or full access to system
    tags: list[str] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    goals: Optional[str] = None
    success_criteria: Optional[str] = None
    tech_stack: Optional[list[str]] = None
    status: Optional[str] = None
    access_level: Optional[str] = None
    allowed_agent_ids: Optional[list[str]] = None
    lead_agent_id: Optional[str] = None
    execution_access: Optional[str] = None
    tags: Optional[list[str]] = None


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    status: str = "backlog"
    priority: str = "medium"
    assignee: str = ""  # agent name or "human"
    labels: list[str] = []
    story_points: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    labels: Optional[list[str]] = None
    story_points: Optional[int] = None


class FileCreate(BaseModel):
    path: str
    is_dir: bool = False
    content: str = ""


class FileWrite(BaseModel):
    path: str
    content: str


class ExecuteRequest(BaseModel):
    command: str
    timeout: int = 30
    env: Optional[dict[str, str]] = None


# ══════════════════════════════════════════════════════════
# ── PROJECT CRUD ─────────────────────────────────────────
# ══════════════════════════════════════════════════════════

@router.get("")
async def list_projects(
    status: Optional[str] = None,
    _user: User = Depends(get_current_user),
):
    """List all projects."""
    _ensure_projects_dir()
    base = Path(settings.PROJECTS_DIR)
    projects = []
    if not base.exists():
        return {"items": [], "total": 0}
    for entry in sorted(base.iterdir(), key=lambda e: e.name.lower()):
        if entry.is_dir() and (entry / "project.json").exists():
            config = _read_project_json(entry)
            if config:
                if status and config.get("status") != status:
                    continue
                projects.append(_enrich_project(config, entry))
    return {"items": projects, "total": len(projects)}


@router.get("/by-agent/{agent_id}")
async def list_projects_for_agent(
    agent_id: str,
    _user: User = Depends(get_current_user),
):
    """List projects accessible by a given agent (allowed or access_level=full, or lead)."""
    _ensure_projects_dir()
    base = Path(settings.PROJECTS_DIR)
    projects = []
    if not base.exists():
        return {"items": [], "total": 0}
    for entry in sorted(base.iterdir(), key=lambda e: e.name.lower()):
        if entry.is_dir() and (entry / "project.json").exists():
            config = _read_project_json(entry)
            if not config:
                continue
            if config.get("status") in ("archived",):
                continue
            access = config.get("access_level", "full")
            allowed = config.get("allowed_agent_ids", [])
            lead = config.get("lead_agent_id")
            # Agent has access if: access_level is full, or agent is in allowed list, or agent is lead
            if access == "full" or agent_id in allowed or lead == agent_id:
                enriched = _enrich_project(config, entry)
                enriched["is_lead"] = (lead == agent_id)
                projects.append(enriched)
    return {"items": projects, "total": len(projects)}


@router.post("", status_code=201)
async def create_project(
    body: ProjectCreate,
    _user: User = Depends(get_current_user),
):
    """Create a new project."""
    _ensure_projects_dir()
    slug = _slug_from_name(body.name)
    project_dir = _get_project_dir(slug)

    # Ensure unique slug
    counter = 1
    original_slug = slug
    while project_dir.exists():
        slug = f"{original_slug}-{counter}"
        project_dir = _get_project_dir(slug)
        counter += 1

    # Create directory structure
    project_dir.mkdir(parents=True)
    (project_dir / "code").mkdir()

    now = datetime.now(timezone.utc).isoformat()
    config = {
        "id": uuid.uuid4().hex,
        "slug": slug,
        "name": body.name,
        "description": body.description,
        "goals": body.goals,
        "success_criteria": body.success_criteria,
        "tech_stack": body.tech_stack,
        "status": body.status if body.status in PROJECT_STATUSES else "active",
        "access_level": body.access_level,
        "allowed_agent_ids": body.allowed_agent_ids,
        "lead_agent_id": body.lead_agent_id,
        "execution_access": body.execution_access,
        "tags": body.tags,
        "created_at": now,
        "updated_at": now,
    }
    _write_project_json(project_dir, config)
    _write_tasks_json(project_dir, [])
    _write_logs_json(project_dir, [])

    _add_log(project_dir, "info", f"Project '{body.name}' created", source="system")

    return _enrich_project(config, project_dir)


@router.get("/{slug}")
async def get_project(
    slug: str,
    _user: User = Depends(get_current_user),
):
    """Get project details."""
    project_dir, config = _get_project_or_404(slug)
    return _enrich_project(config, project_dir)


@router.patch("/{slug}")
async def update_project(
    slug: str,
    body: ProjectUpdate,
    _user: User = Depends(get_current_user),
):
    """Update project settings."""
    project_dir, config = _get_project_or_404(slug)

    update_data = body.model_dump(exclude_none=True)
    if "status" in update_data and update_data["status"] not in PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {update_data['status']}")

    config.update(update_data)
    _write_project_json(project_dir, config)
    _add_log(project_dir, "info", f"Project settings updated: {', '.join(update_data.keys())}", source="user")

    return _enrich_project(config, project_dir)


@router.delete("/{slug}")
async def delete_project(
    slug: str,
    _user: User = Depends(get_current_user),
):
    """Delete project and all its files."""
    project_dir, config = _get_project_or_404(slug)
    shutil.rmtree(project_dir)
    return MessageResponse(message=f"Project '{config.get('name', slug)}' deleted")


# ══════════════════════════════════════════════════════════
# ── TASKS (BACKLOG) ─────────────────────────────────────
# ══════════════════════════════════════════════════════════

@router.get("/{slug}/tasks")
async def list_tasks(
    slug: str,
    status: Optional[str] = None,
    _user: User = Depends(get_current_user),
):
    """List all tasks in the project backlog."""
    project_dir, _ = _get_project_or_404(slug)
    tasks = _read_tasks_json(project_dir)

    if status:
        tasks = [t for t in tasks if t.get("status") == status]

    return {"items": tasks, "total": len(tasks)}


@router.post("/{slug}/tasks", status_code=201)
async def create_task(
    slug: str,
    body: TaskCreate,
    _user: User = Depends(get_current_user),
):
    """Create a new task in the project backlog."""
    project_dir, _ = _get_project_or_404(slug)
    tasks = _read_tasks_json(project_dir)

    # Auto-generate task key
    max_num = 0
    for t in tasks:
        key = t.get("key", "")
        if key.startswith("T-"):
            try:
                num = int(key.split("-")[1])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                pass

    now = datetime.now(timezone.utc).isoformat()
    task = {
        "id": uuid.uuid4().hex[:12],
        "key": f"T-{max_num + 1}",
        "title": body.title,
        "description": body.description,
        "status": body.status if body.status in TASK_STATUSES else "backlog",
        "priority": body.priority if body.priority in TASK_PRIORITIES else "medium",
        "assignee": body.assignee,
        "labels": body.labels,
        "story_points": body.story_points,
        "created_at": now,
        "updated_at": now,
    }
    tasks.append(task)
    _write_tasks_json(project_dir, tasks)
    _add_log(project_dir, "info", f"Task {task['key']} created: {body.title}", source="user")

    return task


@router.get("/{slug}/tasks/{task_id}")
async def get_task(
    slug: str,
    task_id: str,
    _user: User = Depends(get_current_user),
):
    """Get a single task."""
    project_dir, _ = _get_project_or_404(slug)
    tasks = _read_tasks_json(project_dir)
    for t in tasks:
        if t.get("id") == task_id:
            return t
    raise HTTPException(status_code=404, detail="Task not found")


@router.patch("/{slug}/tasks/{task_id}")
async def update_task(
    slug: str,
    task_id: str,
    body: TaskUpdate,
    _user: User = Depends(get_current_user),
):
    """Update a task."""
    project_dir, _ = _get_project_or_404(slug)
    tasks = _read_tasks_json(project_dir)

    for i, t in enumerate(tasks):
        if t.get("id") == task_id:
            update_data = body.model_dump(exclude_none=True)
            if "status" in update_data and update_data["status"] not in TASK_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid status: {update_data['status']}")
            if "priority" in update_data and update_data["priority"] not in TASK_PRIORITIES:
                raise HTTPException(status_code=400, detail=f"Invalid priority: {update_data['priority']}")

            old_status = t.get("status")
            t.update(update_data)
            t["updated_at"] = datetime.now(timezone.utc).isoformat()
            tasks[i] = t
            _write_tasks_json(project_dir, tasks)

            if "status" in update_data and old_status != update_data["status"]:
                _add_log(project_dir, "info",
                         f"Task {t.get('key')} moved: {old_status} → {update_data['status']}",
                         source="user")

            return t

    raise HTTPException(status_code=404, detail="Task not found")


@router.delete("/{slug}/tasks/{task_id}")
async def delete_task(
    slug: str,
    task_id: str,
    _user: User = Depends(get_current_user),
):
    """Delete a task."""
    project_dir, _ = _get_project_or_404(slug)
    tasks = _read_tasks_json(project_dir)
    original = len(tasks)
    tasks = [t for t in tasks if t.get("id") != task_id]
    if len(tasks) == original:
        raise HTTPException(status_code=404, detail="Task not found")
    _write_tasks_json(project_dir, tasks)
    return MessageResponse(message="Task deleted")


# ══════════════════════════════════════════════════════════
# ── CODE FILES ──────────────────────────────────────────
# ══════════════════════════════════════════════════════════

@router.get("/{slug}/files")
async def list_code_files(
    slug: str,
    _user: User = Depends(get_current_user),
):
    """List all files in the project code directory (tree)."""
    project_dir, _ = _get_project_or_404(slug)
    code_dir = project_dir / "code"
    code_dir.mkdir(exist_ok=True)
    return _scan_code_dir(code_dir, code_dir)


@router.get("/{slug}/files/read")
async def read_code_file(
    slug: str,
    path: str = Query(...),
    _user: User = Depends(get_current_user),
):
    """Read content of a file in the project code directory."""
    project_dir, _ = _get_project_or_404(slug)
    file_path = _resolve_code_path(project_dir, path)

    if not file_path.exists() or file_path.is_dir():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Binary file cannot be read as text")

    return {"path": path, "content": content, "language": _get_language(file_path.name)}


@router.post("/{slug}/files/create")
async def create_code_file(
    slug: str,
    body: FileCreate,
    _user: User = Depends(get_current_user),
):
    """Create a new file or folder in the project code directory."""
    project_dir, _ = _get_project_or_404(slug)
    code_dir = project_dir / "code"
    code_dir.mkdir(exist_ok=True)

    if not body.path:
        raise HTTPException(status_code=400, detail="path is required")

    target = _resolve_code_path(project_dir, body.path)
    if target.exists():
        raise HTTPException(status_code=409, detail="File or folder already exists")

    if body.is_dir:
        target.mkdir(parents=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.content, encoding="utf-8")

    _add_log(project_dir, "info",
             f"{'Folder' if body.is_dir else 'File'} created: {body.path}",
             source="user")

    return MessageResponse(message="Created")


@router.put("/{slug}/files/write")
async def write_code_file(
    slug: str,
    body: FileWrite,
    _user: User = Depends(get_current_user),
):
    """Write/update content of a file in the project code directory."""
    project_dir, _ = _get_project_or_404(slug)

    if not body.path:
        raise HTTPException(status_code=400, detail="path is required")

    file_path = _resolve_code_path(project_dir, body.path)

    # Create file if it doesn't exist
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body.content, encoding="utf-8")

    return MessageResponse(message="File saved")


@router.delete("/{slug}/files/delete")
async def delete_code_file(
    slug: str,
    path: str = Query(...),
    _user: User = Depends(get_current_user),
):
    """Delete a file or folder from the project code directory."""
    project_dir, _ = _get_project_or_404(slug)
    target = _resolve_code_path(project_dir, path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()

    _add_log(project_dir, "info", f"Deleted: {path}", source="user")
    return MessageResponse(message="Deleted")


@router.post("/{slug}/files/rename")
async def rename_code_file(
    slug: str,
    body: dict,
    _user: User = Depends(get_current_user),
):
    """Rename/move a file or folder within the project code directory."""
    project_dir, _ = _get_project_or_404(slug)
    old_path = body.get("old_path", "")
    new_path = body.get("new_path", "")
    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="old_path and new_path required")

    src = _resolve_code_path(project_dir, old_path)
    dst = _resolve_code_path(project_dir, new_path)

    if not src.exists():
        raise HTTPException(status_code=404, detail="Source not found")
    if dst.exists():
        raise HTTPException(status_code=409, detail="Destination already exists")

    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    _add_log(project_dir, "info", f"Renamed: {old_path} → {new_path}", source="user")
    return MessageResponse(message="Renamed")


# ══════════════════════════════════════════════════════════
# ── CODE EXECUTION ──────────────────────────────────────
# ══════════════════════════════════════════════════════════

@router.post("/{slug}/execute")
async def execute_in_project(
    slug: str,
    body: ExecuteRequest,
    _user: User = Depends(get_current_user),
):
    """Execute a shell command in the project code directory."""
    project_dir, config = _get_project_or_404(slug)
    code_dir = project_dir / "code"

    # Check execution access
    exec_access = config.get("execution_access", "restricted")
    if exec_access == "restricted":
        # In restricted mode, only allow running code inside the project dir
        pass  # We still allow execution — just in the project's code dir

    timeout = min(body.timeout, 300)
    env = os.environ.copy()
    if body.env:
        env.update(body.env)
    env["PROJECT_DIR"] = str(code_dir)

    start = time.monotonic()
    timed_out = False

    try:
        proc = await asyncio.create_subprocess_shell(
            body.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(code_dir),
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            timed_out = True

    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Code directory not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    duration = int((time.monotonic() - start) * 1000)
    stdout = stdout_bytes.decode("utf-8", errors="replace")[:1_000_000]
    stderr = stderr_bytes.decode("utf-8", errors="replace")[:1_000_000]
    exit_code = proc.returncode

    _add_log(project_dir, "info" if exit_code == 0 else "warning",
             f"Execute: `{body.command}` → exit {exit_code} ({duration}ms)",
             source="execution")
    return {
        "command": body.command,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration_ms": duration,
        "timed_out": timed_out,
    }


@router.post("/{slug}/execute-stream")
async def execute_stream_in_project(
    slug: str,
    body: ExecuteRequest,
    _user: User = Depends(get_current_user),
):
    """Execute a command and stream output via SSE."""
    project_dir, config = _get_project_or_404(slug)
    code_dir = project_dir / "code"

    timeout = min(body.timeout, 300)
    env = os.environ.copy()
    if body.env:
        env.update(body.env)
    env["PROJECT_DIR"] = str(code_dir)

    async def stream():
        try:
            proc = await asyncio.create_subprocess_shell(
                body.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(code_dir),
                env=env,
            )

            async def read_stream(stream, stream_type):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    yield f"data: {json.dumps({'type': stream_type, 'text': text})}\n\n"

            async for chunk in read_stream(proc.stdout, "stdout"):
                yield chunk
            async for chunk in read_stream(proc.stderr, "stderr"):
                yield chunk

            exit_code = await proc.wait()
            yield f"data: {json.dumps({'type': 'exit', 'code': exit_code})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ══════════════════════════════════════════════════════════
# ── PROJECT LOGS ────────────────────────────────────────
# ══════════════════════════════════════════════════════════

@router.get("/{slug}/logs")
async def get_project_logs(
    slug: str,
    limit: int = Query(50, ge=1, le=500),
    level: Optional[str] = None,
    source: Optional[str] = None,
    _user: User = Depends(get_current_user),
):
    """Get project activity logs."""
    project_dir, _ = _get_project_or_404(slug)
    logs = _read_logs_json(project_dir)

    if level:
        logs = [l for l in logs if l.get("level") == level]
    if source:
        logs = [l for l in logs if l.get("source") == source]

    # Return most recent first
    logs.reverse()
    return {"items": logs[:limit], "total": len(logs)}
