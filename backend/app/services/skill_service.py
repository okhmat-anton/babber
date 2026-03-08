from motor.motor_asyncio import AsyncIOMotorDatabase
from app.mongodb.models import MongoSkill
from app.mongodb.services import SkillService
from app.api.skill_files import init_skill_directory


SYSTEM_SKILLS = [
    {
        "name": "web_fetch",
        "display_name": "Web Fetch",
        "description": "HTTP GET/POST requests to URL",
        "category": "web",
        "code": "import httpx\nasync def execute(url, method='GET', **kwargs):\n    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=15) as c:\n        r = await getattr(c, method.lower())(url, **kwargs)\n        return {'status': r.status_code, 'text': r.text[:5000]}",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "method": {"type": "string", "default": "GET"}}},
    },
    {
        "name": "web_scrape",
        "display_name": "Web Scrape",
        "description": "Parse HTML pages (BeautifulSoup)",
        "category": "web",
        "code": "# HTML scraping skill",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "selector": {"type": "string"}}},
    },
    {
        "name": "file_read",
        "display_name": "File Read",
        "description": "Read files from filesystem",
        "category": "files",
        "code": "async def execute(path):\n    with open(path) as f:\n        return {'content': f.read()}",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "file_write",
        "display_name": "File Write",
        "description": "Write files to filesystem",
        "category": "files",
        "code": "async def execute(path, content):\n    with open(path, 'w') as f:\n        f.write(content)\n    return {'written': len(content)}",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
    },
    {
        "name": "shell_exec",
        "display_name": "Shell Execute",
        "description": "Execute shell commands (sandbox)",
        "category": "code",
        "code": "import asyncio\nasync def execute(command):\n    proc = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)\n    stdout, stderr = await proc.communicate()\n    return {'stdout': stdout.decode()[:5000], 'stderr': stderr.decode()[:2000], 'returncode': proc.returncode}",
        "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}},
    },
    {
        "name": "code_execute",
        "display_name": "Code Execute",
        "description": "Execute Python code (sandbox)",
        "category": "code",
        "code": "# Python code execution in sandbox",
        "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}},
    },
    {
        "name": "json_parse",
        "display_name": "JSON Parse",
        "description": "Parse and transform JSON",
        "category": "data",
        "code": "import json\ndef execute(text):\n    return json.loads(text)",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
    {
        "name": "text_summarize",
        "display_name": "Text Summarize",
        "description": "Summarize text using LLM",
        "category": "general",
        "code": "# Uses LLM to summarize text",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}, "max_length": {"type": "integer", "default": 200}}},
    },
    {
        "name": "memory_store",
        "display_name": "Memory Store",
        "description": "Save information to long-term memory",
        "category": "general",
        "code": "# Stores memory entry via MemoryService",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "type": {"type": "string"}, "importance": {"type": "number"}, "tags": {"type": "array"}}},
    },
    {
        "name": "memory_search",
        "display_name": "Memory Search",
        "description": "Semantic search through agent memory",
        "category": "general",
        "code": "# Searches memory via MemoryService",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}}},
    },
    {
        "name": "memory_deep_process",
        "display_name": "Memory Deep Process",
        "description": "Analyze all memory records, establish typed links between them, build knowledge graph (see Memory Links)",
        "category": "general",
        "code": "# Deep memory processing: analyzes all records and creates links",
        "input_schema": {"type": "object", "properties": {"depth": {"type": "integer", "default": 2}}},
    },
    {
        "name": "project_file_write",
        "display_name": "Project File Write",
        "description": "Write/create a file inside a project's code directory. Use this to save code to your assigned projects.",
        "description_for_agent": (
            "Write or create a file inside a project's code directory. "
            "Parameters: project_slug (string, e.g. 'hello-world'), path (string, relative path inside project code dir, e.g. 'main.py' or 'src/utils.py'), "
            "content (string, file content). Creates parent directories automatically. "
            "ALWAYS use this skill to save code to projects instead of file_write."
        ),
        "category": "files",
        "code": (
            "from pathlib import Path\n"
            "import os\n"
            "async def execute(project_slug, path, content):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    code_dir = (base / project_slug / 'code').resolve()\n"
            "    if not str(code_dir).startswith(str(base)):\n"
            "        return {'error': 'Invalid project slug'}\n"
            "    file_path = (code_dir / path).resolve()\n"
            "    if not str(file_path).startswith(str(code_dir)):\n"
            "        return {'error': 'Path traversal not allowed'}\n"
            "    file_path.parent.mkdir(parents=True, exist_ok=True)\n"
            "    existed = file_path.exists()\n"
            "    file_path.write_text(content, encoding='utf-8')\n"
            "    result = {'written': len(content), 'path': str(file_path.relative_to(code_dir))}\n"
            "    if existed:\n"
            "        result['warning'] = f'File {path} already existed and was OVERWRITTEN. Previous content was lost.'\n"
            "    return result\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "path": {"type": "string", "description": "Relative file path inside project code dir"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["project_slug", "path", "content"],
        },
    },
    {
        "name": "project_file_read",
        "display_name": "Project File Read",
        "description": "Read a file from a project's code directory.",
        "description_for_agent": (
            "Read a file from a project's code directory. "
            "Parameters: project_slug (string), path (string, relative path). "
            "Returns the file content. Use this to read existing project files before modifying them."
        ),
        "category": "files",
        "code": (
            "from pathlib import Path\n"
            "import os\n"
            "async def execute(project_slug, path):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    code_dir = (base / project_slug / 'code').resolve()\n"
            "    if not str(code_dir).startswith(str(base)):\n"
            "        return {'error': 'Invalid project slug'}\n"
            "    file_path = (code_dir / path).resolve()\n"
            "    if not str(file_path).startswith(str(code_dir)):\n"
            "        return {'error': 'Path traversal not allowed'}\n"
            "    if not file_path.exists():\n"
            "        return {'error': f'File not found: {path}'}\n"
            "    return {'content': file_path.read_text(encoding='utf-8'), 'path': str(file_path.relative_to(code_dir))}\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "path": {"type": "string", "description": "Relative file path inside project code dir"},
            },
            "required": ["project_slug", "path"],
        },
    },
    {
        "name": "project_list_files",
        "display_name": "Project List Files",
        "description": "List files in a project's code directory.",
        "description_for_agent": (
            "List all files in a project's code directory (recursively). "
            "Parameters: project_slug (string). Returns list of file paths relative to code dir."
        ),
        "category": "files",
        "code": (
            "from pathlib import Path\n"
            "import os\n"
            "async def execute(project_slug):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    code_dir = (base / project_slug / 'code').resolve()\n"
            "    if not code_dir.exists():\n"
            "        return {'files': [], 'error': 'No code directory found'}\n"
            "    files = []\n"
            "    for f in sorted(code_dir.rglob('*')):\n"
            "        if f.is_file():\n"
            "            files.append(str(f.relative_to(code_dir)))\n"
            "    return {'files': files, 'total': len(files)}\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug"},
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "project_update_task",
        "display_name": "Project Update Task",
        "description": "Update the status of a project task (e.g. move to in_progress, review, done).",
        "description_for_agent": (
            "Update a project task's status or other fields. "
            "Parameters: project_slug (string), task_id (string, the task ID from the task list), "
            "status (string, optional: 'backlog', 'todo', 'in_progress', 'review', 'done', 'cancelled'), "
            "assignee (string, optional: your agent name). "
            "Use this after completing work on a task to move it to 'done' or 'review'. "
            "ALWAYS update task status when you start or finish working on a task."
        ),
        "category": "project",
        "code": (
            "from pathlib import Path\n"
            "import os, json\n"
            "from datetime import datetime, timezone\n"
            "async def execute(project_slug, task_id, status=None, assignee=None):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    tasks_path = base / project_slug / 'tasks.json'\n"
            "    if not tasks_path.exists():\n"
            "        return {'error': f'Project {project_slug} tasks not found'}\n"
            "    tasks = json.loads(tasks_path.read_text(encoding='utf-8'))\n"
            "    valid_statuses = ['backlog', 'todo', 'in_progress', 'review', 'done', 'cancelled']\n"
            "    for t in tasks:\n"
            "        if t.get('id') == task_id or t.get('key') == task_id:\n"
            "            old_status = t.get('status')\n"
            "            if status:\n"
            "                if status not in valid_statuses:\n"
            "                    return {'error': f'Invalid status: {status}. Valid: {valid_statuses}'}\n"
            "                t['status'] = status\n"
            "            if assignee is not None:\n"
            "                t['assignee'] = assignee\n"
            "            t['updated_at'] = datetime.now(timezone.utc).isoformat()\n"
            "            tasks_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding='utf-8')\n"
            "            # Write to project log\n"
            "            log_path = base / project_slug / 'log.jsonl'\n"
            "            entry = json.dumps({'ts': datetime.now(timezone.utc).isoformat(), 'level': 'info', "
            "'message': f\"Task {t.get('key')} moved: {old_status} → {status or old_status}\", 'source': 'agent'})\n"
            "            with open(log_path, 'a') as f:\n"
            "                f.write(entry + '\\n')\n"
            "            return {'updated': True, 'task_key': t.get('key'), 'old_status': old_status, 'new_status': t.get('status')}\n"
            "    return {'error': f'Task {task_id} not found in project {project_slug}'}\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "task_id": {"type": "string", "description": "Task ID or key (e.g. '245dd6f23bde' or 'T-1')"},
                "status": {"type": "string", "description": "New status: backlog, todo, in_progress, review, done, cancelled"},
                "assignee": {"type": "string", "description": "Agent name to assign (optional)"},
            },
            "required": ["project_slug", "task_id"],
        },
    },
    {
        "name": "project_task_comment",
        "display_name": "Project Task Comment",
        "description": "Add a comment to a project task.",
        "description_for_agent": (
            "Add a comment to a project task. "
            "Parameters: project_slug (string), task_id (string, the task ID or key), "
            "content (string, the comment text). "
            "Use this to document your progress, explain what you did, or note any issues. "
            "ALWAYS leave a comment when you complete or make progress on a task."
        ),
        "category": "project",
        "code": (
            "from pathlib import Path\n"
            "import os, json, uuid\n"
            "from datetime import datetime, timezone\n"
            "async def execute(project_slug, task_id, content, author='agent'):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    tasks_path = base / project_slug / 'tasks.json'\n"
            "    if not tasks_path.exists():\n"
            "        return {'error': f'Project {project_slug} tasks not found'}\n"
            "    tasks = json.loads(tasks_path.read_text(encoding='utf-8'))\n"
            "    for t in tasks:\n"
            "        if t.get('id') == task_id or t.get('key') == task_id:\n"
            "            if 'comments' not in t:\n"
            "                t['comments'] = []\n"
            "            comment = {\n"
            "                'id': uuid.uuid4().hex[:12],\n"
            "                'content': content,\n"
            "                'author': author,\n"
            "                'created_at': datetime.now(timezone.utc).isoformat(),\n"
            "            }\n"
            "            t['comments'].append(comment)\n"
            "            t['updated_at'] = datetime.now(timezone.utc).isoformat()\n"
            "            tasks_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding='utf-8')\n"
            "            return {'added': True, 'comment_id': comment['id'], 'task_key': t.get('key')}\n"
            "    return {'error': f'Task {task_id} not found in project {project_slug}'}\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "task_id": {"type": "string", "description": "Task ID or key (e.g. '245dd6f23bde' or 'T-2')"},
                "content": {"type": "string", "description": "Comment text"},
                "author": {"type": "string", "description": "Comment author (default: 'agent')"},
            },
            "required": ["project_slug", "task_id", "content"],
        },
    },
    {
        "name": "project_run_code",
        "display_name": "Project Run Code",
        "description": "Execute a Python file from a project's code directory.",
        "description_for_agent": (
            "Run/execute a Python file from project code directory. "
            "Parameters: project_slug (string), file_path (string, relative path like 'main.py' or 't-5_solution.py'). "
            "Returns stdout, stderr, exit code. Use this to test/run your code after writing it. "
            "Working directory is set to the project's code directory."
        ),
        "category": "code",
        "code": (
            "from pathlib import Path\n"
            "import os\n"
            "import asyncio\n"
            "async def execute(project_slug, file_path):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    code_dir = (base / project_slug / 'code').resolve()\n"
            "    if not str(code_dir).startswith(str(base)):\n"
            "        return {'error': 'Invalid project slug'}\n"
            "    target = (code_dir / file_path).resolve()\n"
            "    if not str(target).startswith(str(code_dir)):\n"
            "        return {'error': 'Path traversal not allowed'}\n"
            "    if not target.exists():\n"
            "        return {'error': f'File {file_path} not found'}\n"
            "    proc = await asyncio.create_subprocess_exec(\n"
            "        'python3', target.name,\n"
            "        stdout=asyncio.subprocess.PIPE,\n"
            "        stderr=asyncio.subprocess.PIPE,\n"
            "        cwd=str(code_dir)\n"
            "    )\n"
            "    stdout, stderr = await proc.communicate()\n"
            "    return {\n"
            "        'stdout': stdout.decode('utf-8', errors='replace')[:5000],\n"
            "        'stderr': stderr.decode('utf-8', errors='replace')[:2000],\n"
            "        'exit_code': proc.returncode,\n"
            "        'success': proc.returncode == 0\n"
            "    }\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "file_path": {"type": "string", "description": "Relative file path (e.g. 'main.py', 't-5_solution.py')"},
            },
            "required": ["project_slug", "file_path"],
        },
    },
    {
        "name": "project_context_build",
        "display_name": "Project Context Build",
        "description": "Build complete project context including metadata, tasks, files, and recent activity",
        "description_for_agent": (
            "Get comprehensive project context in a single call. Returns project info, task statistics, file tree, and recent activity logs. "
            "Parameters: project_slug (string), include_logs (boolean, default: true), include_file_tree (boolean, default: true), max_recent_logs (integer, default: 50). "
            "Use this when starting work on a project to understand its current state, goals, and recent activity."
        ),
        "category": "project",
        "code": (
            "from pathlib import Path\n"
            "import os\n"
            "import json\n\n"
            "async def execute(project_slug, include_logs=True, include_file_tree=True, max_recent_logs=50):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    project_dir = (base / project_slug).resolve()\n"
            "    if not str(project_dir).startswith(str(base)):\n"
            "        return {'error': 'Invalid project slug'}\n"
            "    if not project_dir.exists():\n"
            "        return {'error': f'Project not found: {project_slug}'}\n"
            "    project_json = project_dir / 'project.json'\n"
            "    if not project_json.exists():\n"
            "        return {'error': 'Project config not found'}\n"
            "    try:\n"
            "        project_data = json.loads(project_json.read_text(encoding='utf-8'))\n"
            "    except Exception as e:\n"
            "        return {'error': f'Failed to read project config: {str(e)}'}\n"
            "    tasks_json = project_dir / 'tasks.json'\n"
            "    tasks = []\n"
            "    if tasks_json.exists():\n"
            "        try:\n"
            "            tasks = json.loads(tasks_json.read_text(encoding='utf-8'))\n"
            "        except Exception:\n"
            "            pass\n"
            "    task_stats = {\n"
            "        'total': len(tasks),\n"
            "        'backlog': sum(1 for t in tasks if t.get('status') == 'backlog'),\n"
            "        'todo': sum(1 for t in tasks if t.get('status') == 'todo'),\n"
            "        'in_progress': sum(1 for t in tasks if t.get('status') == 'in_progress'),\n"
            "        'review': sum(1 for t in tasks if t.get('status') == 'review'),\n"
            "        'done': sum(1 for t in tasks if t.get('status') == 'done'),\n"
            "        'cancelled': sum(1 for t in tasks if t.get('status') == 'cancelled'),\n"
            "    }\n"
            "    task_summaries = []\n"
            "    for task in tasks:\n"
            "        task_summaries.append({\n"
            "            'id': task.get('id'),\n"
            "            'key': task.get('key'),\n"
            "            'title': task.get('title'),\n"
            "            'status': task.get('status'),\n"
            "            'priority': task.get('priority'),\n"
            "            'assignee': task.get('assignee'),\n"
            "            'labels': task.get('labels', []),\n"
            "            'story_points': task.get('story_points'),\n"
            "            'comment_count': len(task.get('comments', [])),\n"
            "            'created_at': task.get('created_at'),\n"
            "            'updated_at': task.get('updated_at'),\n"
            "        })\n"
            "    result = {\n"
            "        'project': {\n"
            "            'id': project_data.get('id'),\n"
            "            'slug': project_data.get('slug'),\n"
            "            'name': project_data.get('name'),\n"
            "            'description': project_data.get('description', ''),\n"
            "            'goals': project_data.get('goals', ''),\n"
            "            'success_criteria': project_data.get('success_criteria', ''),\n"
            "            'tech_stack': project_data.get('tech_stack', []),\n"
            "            'status': project_data.get('status'),\n"
            "            'tags': project_data.get('tags', []),\n"
            "            'lead_agent_id': project_data.get('lead_agent_id'),\n"
            "            'created_at': project_data.get('created_at'),\n"
            "            'updated_at': project_data.get('updated_at'),\n"
            "        },\n"
            "        'task_stats': task_stats,\n"
            "        'tasks': task_summaries,\n"
            "    }\n"
            "    if include_file_tree:\n"
            "        code_dir = project_dir / 'code'\n"
            "        if code_dir.exists():\n"
            "            files = []\n"
            "            for file_path in sorted(code_dir.rglob('*')):\n"
            "                if file_path.is_file():\n"
            "                    files.append(str(file_path.relative_to(code_dir)))\n"
            "            result['file_tree'] = {'total_files': len(files), 'files': files}\n"
            "        else:\n"
            "            result['file_tree'] = {'total_files': 0, 'files': []}\n"
            "    if include_logs:\n"
            "        logs_json = project_dir / 'logs.json'\n"
            "        if logs_json.exists():\n"
            "            try:\n"
            "                logs = json.loads(logs_json.read_text(encoding='utf-8'))\n"
            "                recent_logs = logs[-max_recent_logs:] if len(logs) > max_recent_logs else logs\n"
            "                result['recent_activity'] = recent_logs\n"
            "            except Exception:\n"
            "                result['recent_activity'] = []\n"
            "        else:\n"
            "            result['recent_activity'] = []\n"
            "    return result\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "include_logs": {"type": "boolean", "description": "Include recent activity logs (default: true)"},
                "include_file_tree": {"type": "boolean", "description": "Include project file tree (default: true)"},
                "max_recent_logs": {"type": "integer", "description": "Maximum number of recent log entries (default: 50)"},
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "task_context_build",
        "display_name": "Task Context Build",
        "description": "Build complete task context including details, comments, related files, and activity history",
        "description_for_agent": (
            "Get comprehensive task context in a single call. Returns task details, all comments, related files inferred from activity logs, and task-specific activity timeline. "
            "Parameters: project_slug (string), task_id (string, task ID or key like 'T-1'), include_comments (boolean, default: true), include_related_files (boolean, default: true), include_activity (boolean, default: true). "
            "Use this when starting work on a task to understand what has been done, what files are involved, and the full context."
        ),
        "category": "project",
        "code": (
            "from pathlib import Path\n"
            "import os\n"
            "import json\n"
            "import re\n\n"
            "async def execute(project_slug, task_id, include_comments=True, include_related_files=True, include_activity=True):\n"
            "    base = Path(os.environ.get('PROJECTS_DIR', './data/projects')).resolve()\n"
            "    project_dir = (base / project_slug).resolve()\n"
            "    if not str(project_dir).startswith(str(base)):\n"
            "        return {'error': 'Invalid project slug'}\n"
            "    if not project_dir.exists():\n"
            "        return {'error': f'Project not found: {project_slug}'}\n"
            "    tasks_json = project_dir / 'tasks.json'\n"
            "    if not tasks_json.exists():\n"
            "        return {'error': 'Tasks file not found'}\n"
            "    try:\n"
            "        tasks = json.loads(tasks_json.read_text(encoding='utf-8'))\n"
            "    except Exception as e:\n"
            "        return {'error': f'Failed to read tasks: {str(e)}'}\n"
            "    task = None\n"
            "    for t in tasks:\n"
            "        if t.get('id') == task_id or t.get('key') == task_id:\n"
            "            task = t\n"
            "            break\n"
            "    if not task:\n"
            "        return {'error': f'Task not found: {task_id}'}\n"
            "    result = {\n"
            "        'task': {\n"
            "            'id': task.get('id'),\n"
            "            'key': task.get('key'),\n"
            "            'title': task.get('title'),\n"
            "            'description': task.get('description', ''),\n"
            "            'status': task.get('status'),\n"
            "            'priority': task.get('priority'),\n"
            "            'assignee': task.get('assignee', ''),\n"
            "            'labels': task.get('labels', []),\n"
            "            'story_points': task.get('story_points'),\n"
            "            'created_at': task.get('created_at'),\n"
            "            'updated_at': task.get('updated_at'),\n"
            "        }\n"
            "    }\n"
            "    if include_comments:\n"
            "        result['comments'] = task.get('comments', [])\n"
            "    task_key = task.get('key', '')\n"
            "    logs_json = project_dir / 'logs.json'\n"
            "    logs = []\n"
            "    if logs_json.exists():\n"
            "        try:\n"
            "            logs = json.loads(logs_json.read_text(encoding='utf-8'))\n"
            "        except Exception:\n"
            "            pass\n"
            "    task_logs = []\n"
            "    if task_key:\n"
            "        for log in logs:\n"
            "            message = log.get('message', '')\n"
            "            if task_key in message or task.get('id') in message:\n"
            "                task_logs.append(log)\n"
            "    if include_activity:\n"
            "        result['activity'] = task_logs\n"
            "    if include_related_files:\n"
            "        related_files = set()\n"
            "        file_patterns = [\n"
            "            r'File created: ([^\\s]+)',\n"
            "            r'File modified: ([^\\s]+)',\n"
            "            r'File deleted: ([^\\s]+)',\n"
            "            r'`python3?\\s+([^\\s`]+)',\n"
            "            r'Execute:.*?([a-zA-Z0-9_\\-./]+\\.[a-zA-Z0-9]+)',\n"
            "        ]\n"
            "        for log in task_logs:\n"
            "            message = log.get('message', '')\n"
            "            for pattern in file_patterns:\n"
            "                matches = re.findall(pattern, message)\n"
            "                for match in matches:\n"
            "                    file_path = match.strip('`').strip()\n"
            "                    if file_path and not file_path.startswith('/'):\n"
            "                        related_files.add(file_path)\n"
            "        result['related_files'] = sorted(list(related_files))\n"
            "    subtasks = []\n"
            "    for t in tasks:\n"
            "        if t.get('parent_task_id') == task.get('id'):\n"
            "            subtasks.append({\n"
            "                'id': t.get('id'),\n"
            "                'key': t.get('key'),\n"
            "                'title': t.get('title'),\n"
            "                'status': t.get('status'),\n"
            "            })\n"
            "    result['subtasks'] = subtasks\n"
            "    parent_task_id = task.get('parent_task_id')\n"
            "    if parent_task_id:\n"
            "        for t in tasks:\n"
            "            if t.get('id') == parent_task_id:\n"
            "                result['parent_task'] = {\n"
            "                    'id': t.get('id'),\n"
            "                    'key': t.get('key'),\n"
            "                    'title': t.get('title'),\n"
            "                    'status': t.get('status'),\n"
            "                }\n"
            "                break\n"
            "    else:\n"
            "        result['parent_task'] = None\n"
            "    return result\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug (e.g. 'hello-world')"},
                "task_id": {"type": "string", "description": "Task ID or key (e.g. '245dd6f23bde' or 'T-1')"},
                "include_comments": {"type": "boolean", "description": "Include all task comments (default: true)"},
                "include_related_files": {"type": "boolean", "description": "Include related files inferred from logs (default: true)"},
                "include_activity": {"type": "boolean", "description": "Include task activity timeline (default: true)"},
            },
            "required": ["project_slug", "task_id"],
        },
    },
]


async def create_system_skills(db: AsyncIOMotorDatabase):
    """Create system skills if not exists."""
    svc = SkillService(db)
    for skill_data in SYSTEM_SKILLS:
        existing = await svc.find_one({"name": skill_data["name"]})
        if existing:
            continue

        skill = MongoSkill(
            name=skill_data["name"],
            display_name=skill_data["display_name"],
            description=skill_data["description"],
            description_for_agent=skill_data.get("description_for_agent", ""),
            category=skill_data["category"],
            code=skill_data["code"],
            input_schema=skill_data.get("input_schema", {}),
            is_system=True,
            is_shared=True,
        )
        skill = await svc.create(skill)

        # Create filesystem directory + manifest
        init_skill_directory(skill)
