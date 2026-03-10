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
    {
        "name": "sound_generate",
        "display_name": "Sound Generate (TTS)",
        "description": "Generate speech audio from text using OpenAI or MiniMax TTS.",
        "description_for_agent": (
            "Generate speech audio from text. Returns an audio_url you can include in your response. "
            "Parameters: text (string, required, max 10000 chars), voice (string, optional — provider-specific voice name), "
            "provider (string, optional: 'openai' or 'minimax', uses system default if omitted). "
            "OpenAI voices: alloy, echo, fable, onyx, nova, shimmer. "
            "MiniMax voices: male-qn-qingse, female-shaonv, female-yujie, etc. "
            "Use this skill when the user asks you to read something aloud, generate speech, or create audio."
        ),
        "category": "general",
        "code": "# TTS via audio_service — executed by pipeline handler",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert to speech (max 10000 chars)"},
                "voice": {"type": "string", "description": "Voice name (provider-specific, optional)"},
                "provider": {"type": "string", "description": "TTS provider: openai or minimax (optional, uses system default)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "speech_recognize",
        "display_name": "Speech Recognize (STT)",
        "description": "Transcribe audio to text using OpenAI Whisper.",
        "description_for_agent": (
            "Transcribe audio to text (Speech-to-Text). "
            "Parameters: audio_url (string, URL or local path to the audio file), "
            "language (string, optional, ISO-639-1 code like 'en', 'ru' for better accuracy), "
            "provider (string, optional: 'openai', uses system default if omitted). "
            "Use this ONLY when user provides a direct URL to an audio file that needs transcription. "
            "Do NOT use this for Telegram voice messages — they are already transcribed automatically. "
            "If the user's message is plain text, it does not need speech recognition."
        ),
        "category": "general",
        "code": "# STT via audio_service — executed by pipeline handler",
        "input_schema": {
            "type": "object",
            "properties": {
                "audio_url": {"type": "string", "description": "URL or path of the audio file to transcribe"},
                "language": {"type": "string", "description": "Language code (e.g. 'en', 'ru') for better accuracy"},
                "provider": {"type": "string", "description": "STT provider: openai (optional, uses system default)"},
            },
            "required": ["audio_url"],
        },
    },
    {
        "name": "study_material",
        "display_name": "Study Material",
        "description": "Study and memorize material from text, file, or topic. Creates structured knowledge in memory.",
        "description_for_agent": (
            "Study and deeply learn material. Reads the input, creates a summary, "
            "extracts key topics, writes detailed notes with source references, "
            "and links everything in the knowledge graph. "
            "Parameters: topic (string, optional — subject to study), "
            "file_path (string, optional — path to a file in agent's data/ folder), "
            "text (string, optional — direct text to study), "
            "depth (string, optional: 'quick', 'normal', 'deep', default 'normal'). "
            "At least one of topic/file_path/text must be provided. "
            "Use this when asked to study, learn, read, memorize material."
        ),
        "category": "general",
        "code": "# Multi-step LLM study pipeline — executed by pipeline handler",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic/subject to study"},
                "file_path": {"type": "string", "description": "Path to file in agent data/ folder"},
                "text": {"type": "string", "description": "Direct text to study"},
                "depth": {"type": "string", "description": "Study depth: quick, normal, deep (default: normal)"},
            },
        },
    },
    {
        "name": "recall_knowledge",
        "display_name": "Recall Knowledge",
        "description": "Search and aggregate previously studied knowledge from memory.",
        "description_for_agent": (
            "Recall previously studied knowledge. Searches agent memory for knowledge entries, "
            "aggregates findings, and provides a structured answer based on what was learned. "
            "Parameters: query (string, required — what to recall/remember), "
            "depth (string, optional: 'quick', 'detailed', default 'quick'), "
            "tags (array of strings, optional — filter by specific tags). "
            "Use this when asked to recall, remember, or answer based on previously studied material."
        ),
        "category": "general",
        "code": "# Knowledge recall from memory — executed by pipeline handler",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to recall/remember"},
                "depth": {"type": "string", "description": "Recall depth: quick or detailed (default: quick)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "creator_context",
        "display_name": "Creator Context",
        "description": "Get information about the creator/owner who manages the bots.",
        "description_for_agent": (
            "Get information about the creator/owner — the person who manages and configures the bots. "
            "Returns their name, goals, dreams, skills, current situation, principles, successes, "
            "failures, action history, and ideas. No parameters needed. "
            "Use this when the user asks about themselves, their goals, or when you need personal context."
        ),
        "category": "general",
        "code": "# Creator context — executed by pipeline handler",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "video_watch",
        "display_name": "Video Watch",
        "description": "Fetch video transcript or post content from YouTube (incl. Shorts), TikTok, Instagram, Facebook, Twitter/X, Threads, LinkedIn, Reddit, Twitch, or Kick via ScrapeCreators API.",
        "description_for_agent": (
            "Fetch the transcript (subtitles/captions) of a video or post content from YouTube (including Shorts), "
            "TikTok, Instagram, Facebook, Twitter/X, Threads, LinkedIn, Reddit, Twitch clips, or Kick clips "
            "using the ScrapeCreators API. For YouTube, TikTok, Instagram, Facebook, and Twitter the actual "
            "video transcript is fetched. For Threads, LinkedIn, Reddit, Twitch, and Kick the post/clip content "
            "and metadata is fetched instead. The result is saved to the watched videos database so repeated "
            "requests for the same URL are served from cache. "
            "Parameters: url (string, required — full video/post URL), "
            "language (string, optional — 2-letter language code like 'en', 'es', 'fr'; default: auto-detect). "
            "Returns: {platform, video_id, transcript, language, cached} on success or {error} on failure. "
            "Use this when asked to watch, transcribe, or get the content of a video or social media post."
        ),
        "category": "web",
        "code": "# Video transcript via ScrapeCreators — executed by pipeline handler",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full video/post URL (YouTube, TikTok, Instagram, Facebook, Twitter/X, Threads, LinkedIn, Reddit, Twitch, Kick)"},
                "language": {"type": "string", "description": "2-letter language code (en, es, fr, etc.). Optional."},
            },
            "required": ["url"],
        },
    },
    # --- New utility skills ---
    {
        "name": "web_search",
        "display_name": "Web Search",
        "description": "Search the internet via DuckDuckGo. Returns titles, snippets, and URLs.",
        "description_for_agent": (
            "Search the internet using DuckDuckGo. Returns search results with titles, URLs, and snippets. "
            "Parameters: query (string, required — search query), limit (integer, optional, default 10 — max results), "
            "region (string, optional — region code like 'us-en', 'ru-ru'). "
            "Use this when you need to find information, research a topic, or discover URLs."
        ),
        "category": "web",
        "code": "import httpx\nimport re\n\nasync def execute(query, limit=10, region=\"wt-wt\"):\n    \"\"\"Search the internet via DuckDuckGo HTML.\"\"\"\n    url = \"https://html.duckduckgo.com/html/\"\n    headers = {\"User-Agent\": \"Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0\"}\n    data = {\"q\": query, \"kl\": region}\n    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:\n        resp = await client.post(url, data=data, headers=headers)\n        resp.raise_for_status()\n    html = resp.text\n    results = []\n    for m in re.finditer(\n        r'<a rel=\"nofollow\" class=\"result__a\" href=\"([^\"]*)\"[^>]*>(.*?)</a>',\n        html, re.DOTALL\n    ):\n        href, title = m.group(1), re.sub(r\"<[^>]+>\", \"\", m.group(2)).strip()\n        snippet = \"\"\n        snip = re.search(r'<a class=\"result__snippet\"[^>]*>(.*?)</a>', html[m.end():m.end()+2000], re.DOTALL)\n        if snip:\n            snippet = re.sub(r\"<[^>]+>\", \"\", snip.group(1)).strip()\n        results.append({\"title\": title, \"url\": href, \"snippet\": snippet})\n        if len(results) >= limit:\n            break\n    return {\"results\": results, \"total\": len(results), \"query\": query}",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results (default: 10)"},
                "region": {"type": "string", "description": "Region code (e.g. 'us-en', 'ru-ru')"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "telegram_send",
        "display_name": "Telegram Send",
        "description": "Send a message to a Telegram chat via configured messenger.",
        "description_for_agent": (
            "Send a proactive message to a Telegram chat using a configured messenger integration. "
            "Parameters: messenger_id (string, required — ID of the messenger config), "
            "chat_id (string, required — Telegram chat ID or username), "
            "text (string, required — message text, supports Markdown), "
            "parse_mode (string, optional — 'markdown' or 'html', default 'markdown'). "
            "Use this to send notifications, reports, or alerts to Telegram."
        ),
        "category": "messaging",
        "code": "# Telegram message sending — requires running Telethon client from messenger config.\n# Primary execution path is via the pipeline handler (_sys_telegram_send).\n# This standalone fallback will not work without active messenger sessions.\n\nasync def execute(messenger_id, chat_id, text, parse_mode=\"markdown\"):\n    \"\"\"Send a Telegram message. Requires active messenger session in pipeline context.\"\"\"\n    return {\n        \"error\": \"telegram_send requires an active Telethon session. \"\n                 \"This skill must be executed through the pipeline handler, \"\n                 \"not standalone. Ensure a Telegram messenger is configured and running.\"\n    }",
        "input_schema": {
            "type": "object",
            "properties": {
                "messenger_id": {"type": "string", "description": "Messenger configuration ID"},
                "chat_id": {"type": "string", "description": "Telegram chat ID or username"},
                "text": {"type": "string", "description": "Message text (supports Markdown)"},
                "parse_mode": {"type": "string", "description": "Parse mode: markdown or html (default: markdown)"},
            },
            "required": ["messenger_id", "chat_id", "text"],
        },
    },
    {
        "name": "notification_send",
        "display_name": "Send Notification",
        "description": "Send a notification to the owner via configured channel.",
        "description_for_agent": (
            "Send a notification to the creator/owner. "
            "Parameters: title (string, required — notification title), "
            "message (string, required — notification body), "
            "priority (string, optional — 'low', 'normal', 'high', 'urgent'; default 'normal'). "
            "The notification is delivered via the first available configured messenger. "
            "Use this when something important happens that the owner needs to know about."
        ),
        "category": "general",
        "code": "# Notification sending — routes through configured messenger.\n# Primary execution path is via the pipeline handler (_sys_notification_send).\n\nasync def execute(title, message, priority=\"normal\"):\n    \"\"\"Send a notification to the owner. Requires pipeline context for messenger access.\"\"\"\n    return {\n        \"error\": \"notification_send requires messenger context from the pipeline. \"\n                 \"This skill must be executed through the pipeline handler.\"\n    }",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "message": {"type": "string", "description": "Notification body text"},
                "priority": {"type": "string", "description": "Priority: low, normal, high, urgent (default: normal)"},
            },
            "required": ["title", "message"],
        },
    },
    {
        "name": "image_analyze",
        "display_name": "Image Analyze",
        "description": "Analyze an image using a vision-capable LLM (describe, OCR, answer questions).",
        "description_for_agent": (
            "Analyze an image using a vision-capable LLM. Can describe content, extract text (OCR), "
            "or answer questions about the image. "
            "Parameters: image_url (string, required — URL or local path to the image), "
            "question (string, optional — specific question about the image; default: 'Describe this image in detail'). "
            "Use this when you receive an image and need to understand its content."
        ),
        "category": "ai",
        "code": "# Image analysis using vision-capable LLM.\n# Primary execution path is via the pipeline handler (_sys_image_analyze).\n\nasync def execute(image_url, question=\"Describe this image in detail\"):\n    \"\"\"Analyze an image using vision LLM. Requires pipeline context for LLM access.\"\"\"\n    return {\n        \"error\": \"image_analyze requires a vision-capable LLM accessed through the pipeline. \"\n                 \"This skill must be executed through the pipeline handler.\"\n    }",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL or path to the image"},
                "question": {"type": "string", "description": "Question about the image (default: describe)"},
            },
            "required": ["image_url"],
        },
    },
    {
        "name": "git_operations",
        "display_name": "Git Operations",
        "description": "Perform git operations: clone, status, diff, commit, push, pull, log, branch.",
        "description_for_agent": (
            "Perform git version control operations on a project directory. "
            "Parameters: operation (string, required — 'clone', 'status', 'diff', 'commit', 'push', 'pull', 'log', 'branch', 'checkout'), "
            "project_slug (string, optional — project slug for project-based repos), "
            "repo_url (string, optional — repository URL for clone), "
            "branch (string, optional — branch name for branch/checkout), "
            "message (string, optional — commit message), "
            "files (array, optional — files to add/commit, default: all). "
            "Use this to manage version control for project code."
        ),
        "category": "code",
        "code": "import asyncio\nimport os\n\nasync def execute(operation, project_slug=None, repo_url=None, branch=None, message=None, files=None):\n    \"\"\"Perform git operations: clone, status, diff, commit, push, pull, log, branch, checkout.\"\"\"\n    projects_dir = os.environ.get(\"PROJECTS_DIR\", os.path.join(os.path.dirname(os.path.abspath(__file__)), \"..\", \"..\", \"projects\"))\n    cwd = os.path.join(projects_dir, project_slug) if project_slug else projects_dir\n    async def run(cmd):\n        proc = await asyncio.create_subprocess_shell(\n            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd\n        )\n        out, err = await proc.communicate()\n        return {\"stdout\": out.decode()[:5000], \"stderr\": err.decode()[:2000], \"returncode\": proc.returncode}\n    if operation == \"clone\":\n        if not repo_url:\n            return {\"error\": \"repo_url is required for clone\"}\n        target = os.path.join(projects_dir, project_slug) if project_slug else projects_dir\n        return await run(f\"git clone {repo_url} {target}\")\n    elif operation == \"status\":\n        return await run(\"git status --porcelain\")\n    elif operation == \"diff\":\n        return await run(\"git diff\")\n    elif operation == \"commit\":\n        msg = message or \"Auto commit\"\n        if files:\n            await run(\"git add \" + \" \".join(files))\n        else:\n            await run(\"git add -A\")\n        return await run(f'git commit -m \"{msg}\"')\n    elif operation == \"push\":\n        cmd = f\"git push origin {branch}\" if branch else \"git push\"\n        return await run(cmd)\n    elif operation == \"pull\":\n        cmd = f\"git pull origin {branch}\" if branch else \"git pull\"\n        return await run(cmd)\n    elif operation == \"log\":\n        return await run(\"git log --oneline -20\")\n    elif operation == \"branch\":\n        if branch:\n            return await run(f\"git checkout -b {branch}\")\n        return await run(\"git branch -a\")\n    elif operation == \"checkout\":\n        if not branch:\n            return {\"error\": \"branch is required for checkout\"}\n        return await run(f\"git checkout {branch}\")\n    return {\"error\": f\"Unknown git operation: {operation}\"}",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "description": "Git operation: clone, status, diff, commit, push, pull, log, branch, checkout"},
                "project_slug": {"type": "string", "description": "Project slug (for project-based repos)"},
                "repo_url": {"type": "string", "description": "Repository URL (for clone)"},
                "branch": {"type": "string", "description": "Branch name"},
                "message": {"type": "string", "description": "Commit message"},
                "files": {"type": "array", "items": {"type": "string"}, "description": "Files to stage (default: all)"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "project_search_code",
        "display_name": "Project Search Code",
        "description": "Search through project files by text or regex pattern.",
        "description_for_agent": (
            "Search through project source files using text or regex. Like grep across the codebase. "
            "Parameters: project_slug (string, required), query (string, required — search text or regex), "
            "is_regex (boolean, optional, default false), file_pattern (string, optional — glob like '*.py'), "
            "max_results (integer, optional, default 50). "
            "Returns matching lines with file paths and line numbers. "
            "Use this to find code patterns, function definitions, or specific strings in a project."
        ),
        "category": "code",
        "code": "import os\nimport re\nimport fnmatch\n\ndef execute(project_slug, query, is_regex=False, file_pattern=None, max_results=50):\n    \"\"\"Search through project source files by text or regex pattern.\"\"\"\n    projects_dir = os.environ.get(\"PROJECTS_DIR\", os.path.join(os.path.dirname(os.path.abspath(__file__)), \"..\", \"..\", \"projects\"))\n    project_dir = os.path.join(projects_dir, project_slug)\n    if not os.path.isdir(project_dir):\n        return {\"error\": f\"Project directory not found: {project_slug}\"}\n    skip_dirs = {\".git\", \"node_modules\", \"__pycache__\", \".venv\", \"venv\", \".next\", \"dist\", \"build\", \".idea\"}\n    if is_regex:\n        try:\n            pat = re.compile(query, re.IGNORECASE)\n        except re.error as e:\n            return {\"error\": f\"Invalid regex: {e}\"}\n    results = []\n    for root, dirs, files in os.walk(project_dir):\n        dirs[:] = [d for d in dirs if d not in skip_dirs]\n        for fname in files:\n            if file_pattern and not fnmatch.fnmatch(fname, file_pattern):\n                continue\n            fpath = os.path.join(root, fname)\n            rel_path = os.path.relpath(fpath, project_dir)\n            try:\n                with open(fpath, \"r\", encoding=\"utf-8\", errors=\"ignore\") as f:\n                    for line_num, line in enumerate(f, 1):\n                        matched = pat.search(line) if is_regex else (query.lower() in line.lower())\n                        if matched:\n                            results.append({\"file\": rel_path, \"line\": line_num, \"text\": line.rstrip()[:200]})\n                            if len(results) >= max_results:\n                                return {\"results\": results, \"total\": len(results), \"truncated\": True}\n            except (UnicodeDecodeError, PermissionError, IsADirectoryError):\n                continue\n    return {\"results\": results, \"total\": len(results), \"truncated\": False}",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_slug": {"type": "string", "description": "Project slug"},
                "query": {"type": "string", "description": "Search text or regex pattern"},
                "is_regex": {"type": "boolean", "description": "Treat query as regex (default: false)"},
                "file_pattern": {"type": "string", "description": "File glob pattern (e.g. '*.py', '*.js')"},
                "max_results": {"type": "integer", "description": "Max results (default: 50)"},
            },
            "required": ["project_slug", "query"],
        },
    },
    {
        "name": "image_generate",
        "display_name": "Image Generate",
        "description": "Generate images using DALL-E or compatible API.",
        "description_for_agent": (
            "Generate an image from a text description using DALL-E or compatible API. "
            "Parameters: prompt (string, required — detailed image description), "
            "size (string, optional — '1024x1024', '1792x1024', '1024x1792'; default '1024x1024'), "
            "quality (string, optional — 'standard' or 'hd'; default 'standard'), "
            "style (string, optional — 'natural' or 'vivid'; default 'vivid'). "
            "Returns an image URL. Use this for creative tasks, thumbnails, diagrams."
        ),
        "category": "ai",
        "code": "import httpx\nimport os\n\nasync def execute(prompt, size=\"1024x1024\", quality=\"standard\", style=\"vivid\"):\n    \"\"\"Generate images using DALL-E 3 API. Requires OPENAI_API_KEY.\"\"\"\n    api_key = os.environ.get(\"OPENAI_API_KEY\", \"\")\n    if not api_key:\n        return {\"error\": \"OPENAI_API_KEY not set. Configure openai_api_key in system settings.\"}\n    async with httpx.AsyncClient(timeout=60) as client:\n        resp = await client.post(\n            \"https://api.openai.com/v1/images/generations\",\n            headers={\"Authorization\": f\"Bearer {api_key}\", \"Content-Type\": \"application/json\"},\n            json={\"model\": \"dall-e-3\", \"prompt\": prompt, \"n\": 1, \"size\": size, \"quality\": quality, \"style\": style},\n        )\n        if resp.status_code != 200:\n            return {\"error\": f\"DALL-E API error ({resp.status_code}): {resp.text[:500]}\"}\n        data = resp.json()\n    img = data.get(\"data\", [{}])[0]\n    return {\"url\": img.get(\"url\", \"\"), \"revised_prompt\": img.get(\"revised_prompt\", \"\"), \"prompt\": prompt}",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Image description/prompt"},
                "size": {"type": "string", "description": "Image size: 1024x1024, 1792x1024, 1024x1792"},
                "quality": {"type": "string", "description": "Quality: standard or hd"},
                "style": {"type": "string", "description": "Style: natural or vivid"},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "translate",
        "display_name": "Translate Text",
        "description": "Translate text between languages using LLM.",
        "description_for_agent": (
            "Translate text from one language to another using LLM. "
            "Parameters: text (string, required — text to translate), "
            "to_language (string, required — target language name like 'English', 'Russian', 'Spanish'), "
            "from_language (string, optional — source language, auto-detected if omitted). "
            "Use this when you need to translate text between languages."
        ),
        "category": "general",
        "code": "import httpx\n\nasync def execute(text, to_language, from_language=None):\n    \"\"\"Translate text between languages. Tries MyMemory free API as standalone fallback.\"\"\"\n    src = from_language or \"autodetect\"\n    lang_map = {\n        \"english\": \"en\", \"russian\": \"ru\", \"spanish\": \"es\", \"french\": \"fr\",\n        \"german\": \"de\", \"italian\": \"it\", \"portuguese\": \"pt\", \"chinese\": \"zh\",\n        \"japanese\": \"ja\", \"korean\": \"ko\", \"arabic\": \"ar\", \"hindi\": \"hi\",\n        \"dutch\": \"nl\", \"polish\": \"pl\", \"turkish\": \"tr\", \"swedish\": \"sv\",\n        \"czech\": \"cs\", \"ukrainian\": \"uk\",\n    }\n    src_code = lang_map.get(src.lower(), src.lower()[:2]) if src != \"autodetect\" else \"autodetect\"\n    tgt_code = lang_map.get(to_language.lower(), to_language.lower()[:2])\n    langpair = f\"{src_code}|{tgt_code}\"\n    try:\n        async with httpx.AsyncClient(timeout=15) as client:\n            resp = await client.get(\n                \"https://api.mymemory.translated.net/get\",\n                params={\"q\": text[:500], \"langpair\": langpair},\n            )\n            data = resp.json()\n        translated = data.get(\"responseData\", {}).get(\"translatedText\", \"\")\n        if translated:\n            return {\"translated\": translated, \"from\": src, \"to\": to_language, \"source\": \"mymemory\"}\n        return {\"error\": f\"Translation failed: {data.get('responseStatus', 'unknown')}\"}\n    except Exception as e:\n        return {\"error\": f\"Translation error: {e}. For better results, use through pipeline with LLM.\"}",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to translate"},
                "to_language": {"type": "string", "description": "Target language (e.g. 'English', 'Russian')"},
                "from_language": {"type": "string", "description": "Source language (auto-detect if omitted)"},
            },
            "required": ["text", "to_language"],
        },
    },
    {
        "name": "csv_parse",
        "display_name": "CSV Parse",
        "description": "Parse, filter, and analyze CSV data.",
        "description_for_agent": (
            "Parse and analyze CSV data from text or file. "
            "Parameters: text (string, optional — raw CSV text), "
            "file_path (string, optional — path to CSV file), "
            "operation (string, optional — 'parse', 'filter', 'stats', 'convert'; default 'parse'), "
            "columns (array, optional — select specific columns), "
            "filter_expr (string, optional — filter expression like 'age > 25'), "
            "limit (integer, optional — max rows to return, default 100). "
            "Returns structured data. At least text or file_path required."
        ),
        "category": "data",
        "code": "import csv\nimport io\nimport statistics\n\ndef execute(text=None, file_path=None, operation=\"parse\", columns=None, filter_expr=None, limit=100):\n    \"\"\"Parse, filter, and analyze CSV data.\"\"\"\n    if not text and not file_path:\n        return {\"error\": \"Either text or file_path is required\"}\n    if file_path and not text:\n        with open(file_path, \"r\", encoding=\"utf-8\") as f:\n            text = f.read()\n    reader = csv.DictReader(io.StringIO(text))\n    rows = []\n    for row in reader:\n        if columns:\n            row = {k: v for k, v in row.items() if k in columns}\n        rows.append(row)\n    if operation == \"stats\":\n        stats = {}\n        all_cols = rows[0].keys() if rows else []\n        for col in all_cols:\n            vals = []\n            for r in rows:\n                try:\n                    vals.append(float(r[col]))\n                except (ValueError, TypeError):\n                    pass\n            if vals:\n                stats[col] = {\n                    \"count\": len(vals),\n                    \"mean\": round(statistics.mean(vals), 4),\n                    \"min\": min(vals),\n                    \"max\": max(vals),\n                    \"sum\": round(sum(vals), 4),\n                }\n                if len(vals) > 1:\n                    stats[col][\"stdev\"] = round(statistics.stdev(vals), 4)\n        return {\"stats\": stats, \"total_rows\": len(rows)}\n    return {\"rows\": rows[:limit], \"total_rows\": len(rows), \"columns\": list(rows[0].keys()) if rows else []}",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Raw CSV text"},
                "file_path": {"type": "string", "description": "Path to CSV file"},
                "operation": {"type": "string", "description": "Operation: parse, filter, stats, convert"},
                "columns": {"type": "array", "items": {"type": "string"}, "description": "Select specific columns"},
                "filter_expr": {"type": "string", "description": "Filter expression (e.g. 'age > 25')"},
                "limit": {"type": "integer", "description": "Max rows (default: 100)"},
            },
        },
    },
    {
        "name": "pdf_read",
        "display_name": "PDF Read",
        "description": "Extract text and metadata from PDF files.",
        "description_for_agent": (
            "Extract text content from PDF files. "
            "Parameters: file_path (string, optional — local path to PDF), "
            "url (string, optional — URL to download PDF from), "
            "pages (string, optional — page range like '1-5' or 'all'; default 'all'), "
            "max_chars (integer, optional — max characters to return, default 10000). "
            "Returns extracted text. At least file_path or url required."
        ),
        "category": "files",
        "code": "import os\n\nasync def execute(file_path=None, url=None, pages=\"all\", max_chars=10000):\n    \"\"\"Extract text from PDF files. Tries PyMuPDF (fitz) first, falls back to basic extraction.\"\"\"\n    if not file_path and not url:\n        return {\"error\": \"Either file_path or url is required\"}\n    if url and not file_path:\n        import httpx\n        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:\n            resp = await client.get(url)\n            resp.raise_for_status()\n        file_path = \"/tmp/_skill_pdf_temp.pdf\"\n        with open(file_path, \"wb\") as f:\n            f.write(resp.content)\n    if not os.path.exists(file_path):\n        return {\"error\": f\"File not found: {file_path}\"}\n    text = \"\"\n    page_count = 0\n    try:\n        import fitz  # PyMuPDF\n        doc = fitz.open(file_path)\n        page_count = len(doc)\n        if pages == \"all\":\n            page_nums = range(page_count)\n        elif \"-\" in str(pages):\n            start, end = pages.split(\"-\")\n            page_nums = range(int(start) - 1, min(int(end), page_count))\n        else:\n            page_nums = [int(pages) - 1]\n        for i in page_nums:\n            if i < page_count:\n                text += doc[i].get_text() + \"\\n\"\n        doc.close()\n    except ImportError:\n        with open(file_path, \"rb\") as f:\n            raw = f.read()\n        import re\n        chunks = re.findall(rb\"\\(([^)]+)\\)\", raw)\n        text = b\" \".join(chunks).decode(\"latin-1\", errors=\"replace\")\n        text = re.sub(r\"[\\x00-\\x08\\x0b-\\x0c\\x0e-\\x1f]\", \"\", text)\n    text = text[:max_chars]\n    return {\"text\": text, \"length\": len(text), \"pages\": page_count}",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Local path to PDF file"},
                "url": {"type": "string", "description": "URL to download PDF from"},
                "pages": {"type": "string", "description": "Page range: 'all', '1-5', '3' (default: all)"},
                "max_chars": {"type": "integer", "description": "Max characters to return (default: 10000)"},
            },
        },
    },
    {
        "name": "email_send",
        "display_name": "Email Send",
        "description": "Send emails via SMTP.",
        "description_for_agent": (
            "Send an email via SMTP. Requires SMTP settings in system configuration. "
            "Parameters: to (string, required — recipient email), "
            "subject (string, required — email subject), "
            "body (string, required — email body text), "
            "html (boolean, optional — send as HTML, default false), "
            "reply_to (string, optional — reply-to address). "
            "Use this to send reports, alerts, or communications via email."
        ),
        "category": "messaging",
        "code": "import smtplib\nfrom email.mime.text import MIMEText\nfrom email.mime.multipart import MIMEMultipart\nimport os\n\ndef execute(to, subject, body, html=False, reply_to=None):\n    \"\"\"Send email via SMTP. Requires SMTP env vars or system settings.\"\"\"\n    smtp_host = os.environ.get(\"SMTP_HOST\", \"smtp.gmail.com\")\n    smtp_port = int(os.environ.get(\"SMTP_PORT\", \"587\"))\n    smtp_user = os.environ.get(\"SMTP_USER\", \"\")\n    smtp_pass = os.environ.get(\"SMTP_PASSWORD\", \"\")\n    if not smtp_user or not smtp_pass:\n        return {\"error\": \"SMTP credentials not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD.\"}\n    msg = MIMEMultipart(\"alternative\")\n    msg[\"From\"] = smtp_user\n    msg[\"To\"] = to\n    msg[\"Subject\"] = subject\n    if reply_to:\n        msg[\"Reply-To\"] = reply_to\n    content_type = \"html\" if html else \"plain\"\n    msg.attach(MIMEText(body, content_type, \"utf-8\"))\n    try:\n        with smtplib.SMTP(smtp_host, smtp_port) as server:\n            server.starttls()\n            server.login(smtp_user, smtp_pass)\n            server.send_message(msg)\n        return {\"sent\": True, \"to\": to, \"subject\": subject}\n    except Exception as e:\n        return {\"error\": f\"Failed to send email: {e}\"}",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"},
                "html": {"type": "boolean", "description": "Send as HTML (default: false)"},
                "reply_to": {"type": "string", "description": "Reply-to address"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "schedule_reminder",
        "display_name": "Schedule Reminder",
        "description": "Create a reminder that triggers at a specified time.",
        "description_for_agent": (
            "Create a scheduled reminder that will trigger a notification at a specified time. "
            "Parameters: title (string, required — reminder title), "
            "message (string, required — reminder message), "
            "trigger_at (string, required — ISO datetime like '2024-03-15T14:00:00' or relative like '+1h', '+30m', '+2d'), "
            "recurring (boolean, optional — repeat on the same schedule, default false). "
            "Use this when the user asks to be reminded about something."
        ),
        "category": "general",
        "code": "# Reminder scheduling — creates a task in MongoDB.\n# Primary execution path is via the pipeline handler (_sys_schedule_reminder).\n\nasync def execute(title, message, trigger_at, recurring=False):\n    \"\"\"Schedule a reminder. Requires pipeline context for database access.\"\"\"\n    return {\n        \"error\": \"schedule_reminder requires database access through the pipeline. \"\n                 \"This skill must be executed through the pipeline handler.\"\n    }",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Reminder title"},
                "message": {"type": "string", "description": "Reminder message"},
                "trigger_at": {"type": "string", "description": "When to trigger: ISO datetime or relative (+1h, +30m, +2d)"},
                "recurring": {"type": "boolean", "description": "Repeat (default: false)"},
            },
            "required": ["title", "message", "trigger_at"],
        },
    },
    {
        "name": "yaml_parse",
        "display_name": "YAML Parse",
        "description": "Parse, validate, and convert YAML data.",
        "description_for_agent": (
            "Parse YAML text or files. Convert between YAML and JSON. "
            "Parameters: text (string, optional — YAML text to parse), "
            "file_path (string, optional — path to YAML file), "
            "operation (string, optional — 'parse', 'validate', 'to_json'; default 'parse'). "
            "Returns parsed data as JSON."
        ),
        "category": "data",
        "code": "import yaml\nimport json\n\ndef execute(text=None, file_path=None, operation=\"parse\"):\n    \"\"\"Parse, validate, and convert YAML data.\"\"\"\n    if not text and not file_path:\n        return {\"error\": \"Either text or file_path is required\"}\n    if file_path and not text:\n        with open(file_path, \"r\", encoding=\"utf-8\") as f:\n            text = f.read()\n    try:\n        data = yaml.safe_load(text)\n    except yaml.YAMLError as e:\n        return {\"error\": f\"YAML parse error: {e}\", \"valid\": False}\n    if operation == \"validate\":\n        return {\"valid\": True, \"type\": type(data).__name__}\n    if operation == \"to_json\":\n        return {\"json\": json.dumps(data, indent=2, ensure_ascii=False, default=str)}\n    return {\"data\": data, \"type\": type(data).__name__}",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "YAML text to parse"},
                "file_path": {"type": "string", "description": "Path to YAML file"},
                "operation": {"type": "string", "description": "Operation: parse, validate, to_json"},
            },
        },
    },
    {
        "name": "xml_parse",
        "display_name": "XML Parse",
        "description": "Parse XML data, query with XPath.",
        "description_for_agent": (
            "Parse XML text or files, optionally query with XPath. "
            "Parameters: text (string, optional — XML text), "
            "file_path (string, optional — path to XML file), "
            "xpath (string, optional — XPath query to extract specific elements), "
            "output_format (string, optional — 'json' or 'text'; default 'json'). "
            "Returns parsed XML data."
        ),
        "category": "data",
        "code": "import xml.etree.ElementTree as ET\nimport json\n\ndef _elem_to_dict(elem):\n    result = {}\n    if elem.attrib:\n        result[\"@attributes\"] = dict(elem.attrib)\n    if elem.text and elem.text.strip():\n        if not list(elem):\n            return elem.text.strip()\n        result[\"#text\"] = elem.text.strip()\n    for child in elem:\n        child_data = _elem_to_dict(child)\n        tag = child.tag.split(\"}\")[-1] if \"}\" in child.tag else child.tag\n        if tag in result:\n            if not isinstance(result[tag], list):\n                result[tag] = [result[tag]]\n            result[tag].append(child_data)\n        else:\n            result[tag] = child_data\n    return result or (elem.text.strip() if elem.text else \"\")\n\ndef execute(text=None, file_path=None, xpath=None, output_format=\"json\"):\n    \"\"\"Parse XML data, optionally query with XPath.\"\"\"\n    if not text and not file_path:\n        return {\"error\": \"Either text or file_path is required\"}\n    if file_path and not text:\n        with open(file_path, \"r\", encoding=\"utf-8\") as f:\n            text = f.read()\n    try:\n        root = ET.fromstring(text)\n    except ET.ParseError as e:\n        return {\"error\": f\"XML parse error: {e}\"}\n    if xpath:\n        elements = root.findall(xpath)\n        results = [_elem_to_dict(el) for el in elements]\n        return {\"results\": results, \"count\": len(results), \"xpath\": xpath}\n    tag = root.tag.split(\"}\")[-1] if \"}\" in root.tag else root.tag\n    return {\"root_tag\": tag, \"data\": _elem_to_dict(root)}",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "XML text to parse"},
                "file_path": {"type": "string", "description": "Path to XML file"},
                "xpath": {"type": "string", "description": "XPath query expression"},
                "output_format": {"type": "string", "description": "Output format: json or text"},
            },
        },
    },
    {
        "name": "regex_extract",
        "display_name": "Regex Extract",
        "description": "Extract data from text using regex patterns.",
        "description_for_agent": (
            "Extract data from text using regular expressions. "
            "Parameters: text (string, required — text to search in), "
            "pattern (string, required — regex pattern, supports named groups), "
            "operation (string, optional — 'extract', 'match', 'replace', 'split'; default 'extract'), "
            "replacement (string, optional — replacement string for 'replace' operation), "
            "flags (string, optional — regex flags like 'i' for case-insensitive, 'm' for multiline). "
            "Use this for structured data extraction from unstructured text."
        ),
        "category": "data",
        "code": "import re\n\ndef execute(text, pattern, operation=\"extract\", replacement=None, flags=\"\"):\n    \"\"\"Extract data from text using regex patterns.\"\"\"\n    re_flags = 0\n    if \"i\" in flags:\n        re_flags |= re.IGNORECASE\n    if \"m\" in flags:\n        re_flags |= re.MULTILINE\n    if \"s\" in flags:\n        re_flags |= re.DOTALL\n    try:\n        compiled = re.compile(pattern, re_flags)\n    except re.error as e:\n        return {\"error\": f\"Invalid regex: {e}\"}\n    if operation == \"match\":\n        m = compiled.search(text)\n        if not m:\n            return {\"match\": False}\n        return {\"match\": True, \"full\": m.group(0), \"groups\": list(m.groups()), \"groupdict\": m.groupdict(), \"span\": list(m.span())}\n    if operation == \"replace\":\n        if replacement is None:\n            return {\"error\": \"replacement is required for replace operation\"}\n        result = compiled.sub(replacement, text)\n        return {\"result\": result, \"replacements\": len(compiled.findall(text))}\n    if operation == \"split\":\n        parts = compiled.split(text)\n        return {\"parts\": parts, \"count\": len(parts)}\n    # default: extract\n    matches = []\n    for m in compiled.finditer(text):\n        entry = {\"match\": m.group(0), \"span\": list(m.span())}\n        if m.groups():\n            entry[\"groups\"] = list(m.groups())\n        if m.groupdict():\n            entry[\"named\"] = m.groupdict()\n        matches.append(entry)\n    return {\"matches\": matches, \"total\": len(matches)}",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to search in"},
                "pattern": {"type": "string", "description": "Regex pattern"},
                "operation": {"type": "string", "description": "Operation: extract, match, replace, split"},
                "replacement": {"type": "string", "description": "Replacement string (for replace operation)"},
                "flags": {"type": "string", "description": "Regex flags: i (case-insensitive), m (multiline), s (dotall)"},
            },
            "required": ["text", "pattern"],
        },
    },
    {
        "name": "api_call",
        "display_name": "API Call",
        "description": "Make authenticated REST API calls with custom headers, body, and auth.",
        "description_for_agent": (
            "Make HTTP API calls with full control over headers, body, and authentication. "
            "Parameters: url (string, required), method (string, optional — 'GET', 'POST', 'PUT', 'PATCH', 'DELETE'; default 'GET'), "
            "headers (object, optional — custom headers), body (object or string, optional — request body), "
            "auth_type (string, optional — 'bearer', 'api_key', 'basic'), "
            "auth_value (string, optional — token/key value), "
            "timeout (integer, optional — timeout in seconds, default 30). "
            "Use this for authenticated API calls that web_fetch cannot handle."
        ),
        "category": "web",
        "code": "import httpx\n\nasync def execute(url, method=\"GET\", headers=None, body=None, auth_type=None, auth_value=None, timeout=30):\n    \"\"\"Make HTTP API calls with full control over headers, body, and authentication.\"\"\"\n    hdrs = dict(headers or {})\n    if auth_type and auth_value:\n        if auth_type == \"bearer\":\n            hdrs[\"Authorization\"] = f\"Bearer {auth_value}\"\n        elif auth_type == \"api_key\":\n            hdrs[\"X-API-Key\"] = auth_value\n        elif auth_type == \"basic\":\n            import base64\n            hdrs[\"Authorization\"] = \"Basic \" + base64.b64encode(auth_value.encode()).decode()\n    kwargs = {\"headers\": hdrs, \"timeout\": timeout}\n    if body is not None:\n        if isinstance(body, (dict, list)):\n            kwargs[\"json\"] = body\n        else:\n            kwargs[\"content\"] = str(body)\n    async with httpx.AsyncClient(follow_redirects=True) as client:\n        resp = await getattr(client, method.lower())(url, **kwargs)\n    try:\n        resp_body = resp.json()\n    except Exception:\n        resp_body = resp.text[:5000]\n    return {\"status_code\": resp.status_code, \"headers\": dict(resp.headers), \"body\": resp_body}",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "API endpoint URL"},
                "method": {"type": "string", "description": "HTTP method: GET, POST, PUT, PATCH, DELETE"},
                "headers": {"type": "object", "description": "Custom HTTP headers"},
                "body": {"type": "object", "description": "Request body (JSON)"},
                "auth_type": {"type": "string", "description": "Auth type: bearer, api_key, basic"},
                "auth_value": {"type": "string", "description": "Auth token/key value"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "math_calculate",
        "display_name": "Math Calculate",
        "description": "Evaluate mathematical expressions, statistics, and unit conversions.",
        "description_for_agent": (
            "Evaluate mathematical expressions safely. "
            "Parameters: expression (string, required — math expression like '2**10', 'sqrt(144)', 'sin(pi/4)'), "
            "operation (string, optional — 'eval', 'statistics', 'convert'; default 'eval'), "
            "data (array, optional — list of numbers for statistics operations). "
            "Supports: basic arithmetic, powers, roots, trig, log, constants (pi, e). "
            "For statistics: mean, median, stdev, min, max, sum, count."
        ),
        "category": "data",
        "code": "import math\nimport statistics as stat_mod\n\ndef execute(expression, operation=\"eval\", data=None):\n    \"\"\"Evaluate math expressions safely. Supports arithmetic, trig, log, statistics.\"\"\"\n    if operation == \"statistics\" and data:\n        result = {\n            \"count\": len(data),\n            \"sum\": sum(data),\n            \"mean\": round(stat_mod.mean(data), 6),\n            \"median\": round(stat_mod.median(data), 6),\n            \"min\": min(data),\n            \"max\": max(data),\n        }\n        if len(data) > 1:\n            result[\"stdev\"] = round(stat_mod.stdev(data), 6)\n            result[\"variance\"] = round(stat_mod.variance(data), 6)\n        return {\"result\": result}\n    allowed_names = {\n        \"abs\": abs, \"round\": round, \"min\": min, \"max\": max, \"sum\": sum,\n        \"int\": int, \"float\": float, \"pow\": pow, \"len\": len,\n        \"pi\": math.pi, \"e\": math.e, \"tau\": math.tau, \"inf\": math.inf,\n        \"sqrt\": math.sqrt, \"cbrt\": lambda x: x ** (1/3),\n        \"sin\": math.sin, \"cos\": math.cos, \"tan\": math.tan,\n        \"asin\": math.asin, \"acos\": math.acos, \"atan\": math.atan, \"atan2\": math.atan2,\n        \"log\": math.log, \"log2\": math.log2, \"log10\": math.log10,\n        \"exp\": math.exp, \"ceil\": math.ceil, \"floor\": math.floor,\n        \"factorial\": math.factorial, \"gcd\": math.gcd,\n        \"radians\": math.radians, \"degrees\": math.degrees,\n        \"hypot\": math.hypot, \"isnan\": math.isnan, \"isinf\": math.isinf,\n    }\n    try:\n        code = compile(expression, \"<math>\", \"eval\")\n        for name in code.co_names:\n            if name not in allowed_names:\n                return {\"error\": f\"Function or variable not allowed: {name}\"}\n        result = eval(code, {\"__builtins__\": {}}, allowed_names)\n        return {\"expression\": expression, \"result\": result}\n    except Exception as exc:\n        return {\"error\": str(exc), \"expression\": expression}",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression to evaluate"},
                "operation": {"type": "string", "description": "Operation: eval, statistics, convert"},
                "data": {"type": "array", "items": {"type": "number"}, "description": "Numbers for statistics"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "code_review",
        "display_name": "Code Review",
        "description": "Review code for bugs, security issues, and improvements using LLM.",
        "description_for_agent": (
            "Review code for bugs, security vulnerabilities, style issues, and suggest improvements. "
            "Parameters: code (string, optional — code to review), "
            "file_path (string, optional — path to file to review), "
            "language (string, optional — programming language, auto-detected), "
            "focus (string, optional — 'bugs', 'security', 'style', 'performance', 'all'; default 'all'). "
            "Returns categorized review findings with suggestions."
        ),
        "category": "code",
        "code": "import os\n\ndef execute(code=None, file_path=None, language=None, focus=\"all\"):\n    \"\"\"Review code for bugs, security, style, performance. Returns basic static analysis standalone.\"\"\"\n    if not code and not file_path:\n        return {\"error\": \"Either code or file_path is required\"}\n    if file_path and not code:\n        if not os.path.exists(file_path):\n            return {\"error\": f\"File not found: {file_path}\"}\n        with open(file_path, \"r\", encoding=\"utf-8\") as f:\n            code = f.read()\n    if not language:\n        if file_path:\n            ext = os.path.splitext(file_path)[1]\n            lang_map = {\".py\": \"python\", \".js\": \"javascript\", \".ts\": \"typescript\", \".go\": \"go\", \".rs\": \"rust\", \".java\": \"java\", \".rb\": \"ruby\", \".php\": \"php\"}\n            language = lang_map.get(ext, \"unknown\")\n        else:\n            language = \"unknown\"\n    issues = []\n    lines = code.split(\"\\n\")\n    for i, line in enumerate(lines, 1):\n        stripped = line.rstrip()\n        if len(stripped) > 120:\n            issues.append({\"line\": i, \"type\": \"style\", \"message\": f\"Line too long ({len(stripped)} chars)\"})\n        if \"TODO\" in line or \"FIXME\" in line or \"HACK\" in line:\n            issues.append({\"line\": i, \"type\": \"info\", \"message\": f\"Found marker: {stripped.strip()[:80]}\"})\n        if language == \"python\":\n            if \"eval(\" in line and \"safe\" not in line.lower():\n                issues.append({\"line\": i, \"type\": \"security\", \"message\": \"Potential unsafe eval() usage\"})\n            if \"exec(\" in line:\n                issues.append({\"line\": i, \"type\": \"security\", \"message\": \"Potential unsafe exec() usage\"})\n            if \"import *\" in line:\n                issues.append({\"line\": i, \"type\": \"style\", \"message\": \"Wildcard import\"})\n            if \"except:\" in line and \"except Exception\" not in line:\n                issues.append({\"line\": i, \"type\": \"bugs\", \"message\": \"Bare except clause\"})\n            if \"password\" in line.lower() and \"=\" in line and (\"'\" in line or '\"' in line):\n                issues.append({\"line\": i, \"type\": \"security\", \"message\": \"Possible hardcoded password\"})\n        if language in (\"javascript\", \"typescript\"):\n            if \"eval(\" in line:\n                issues.append({\"line\": i, \"type\": \"security\", \"message\": \"eval() usage\"})\n            if \"var \" in line:\n                issues.append({\"line\": i, \"type\": \"style\", \"message\": \"Use let/const instead of var\"})\n            if \"console.log\" in line:\n                issues.append({\"line\": i, \"type\": \"info\", \"message\": \"console.log found\"})\n    if focus != \"all\":\n        issues = [iss for iss in issues if iss[\"type\"] == focus]\n    return {\n        \"language\": language, \"total_lines\": len(lines), \"issues\": issues[:50],\n        \"issue_count\": len(issues),\n        \"note\": \"Basic static analysis only. For deeper LLM-powered review, execute through the pipeline handler.\"\n    }",
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to review"},
                "file_path": {"type": "string", "description": "Path to file to review"},
                "language": {"type": "string", "description": "Programming language"},
                "focus": {"type": "string", "description": "Review focus: bugs, security, style, performance, all"},
            },
        },
    },
    {
        "name": "docker_manage",
        "display_name": "Docker Manage",
        "description": "Manage Docker containers: list, start, stop, logs, status.",
        "description_for_agent": (
            "Manage Docker containers and images. "
            "Parameters: operation (string, required — 'list', 'start', 'stop', 'restart', 'logs', 'status', 'images'), "
            "container (string, optional — container name or ID), "
            "tail (integer, optional — number of log lines, default 50). "
            "Use this to check service health, restart containers, or view logs."
        ),
        "category": "system",
        "code": "import asyncio\n\nasync def execute(operation, container=None, tail=50):\n    \"\"\"Manage Docker containers: list, start, stop, restart, logs, status, images.\"\"\"\n    async def run(cmd):\n        proc = await asyncio.create_subprocess_shell(\n            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE\n        )\n        out, err = await proc.communicate()\n        return {\"stdout\": out.decode()[:5000], \"stderr\": err.decode()[:2000], \"returncode\": proc.returncode}\n    if operation == \"list\":\n        return await run(\"docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\\t{{.Image}}'\")\n    elif operation == \"start\":\n        if not container:\n            return {\"error\": \"container name required\"}\n        return await run(f\"docker start {container}\")\n    elif operation == \"stop\":\n        if not container:\n            return {\"error\": \"container name required\"}\n        return await run(f\"docker stop {container}\")\n    elif operation == \"restart\":\n        if not container:\n            return {\"error\": \"container name required\"}\n        return await run(f\"docker restart {container}\")\n    elif operation == \"logs\":\n        if not container:\n            return {\"error\": \"container name required\"}\n        return await run(f\"docker logs --tail {tail} {container}\")\n    elif operation == \"status\":\n        if container:\n            return await run(f\"docker inspect --format '{{{{.State.Status}}}}' {container}\")\n        return await run(\"docker ps -a --format 'table {{.Names}}\\t{{.Status}}'\")\n    elif operation == \"images\":\n        return await run(\"docker images --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}'\")\n    return {\"error\": f\"Unknown docker operation: {operation}\"}",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "description": "Operation: list, start, stop, restart, logs, status, images"},
                "container": {"type": "string", "description": "Container name or ID"},
                "tail": {"type": "integer", "description": "Number of log lines (default: 50)"},
            },
            "required": ["operation"],
        },
    },
    {
        "name": "rss_read",
        "display_name": "RSS Read",
        "description": "Parse RSS/Atom feeds, return latest entries.",
        "description_for_agent": (
            "Read and parse RSS or Atom feeds. "
            "Parameters: url (string, required — RSS/Atom feed URL), "
            "limit (integer, optional — max entries to return, default 20). "
            "Returns entries with title, link, summary, and published date. "
            "Use this to monitor news, blogs, or any content with an RSS feed."
        ),
        "category": "web",
        "code": "import httpx\nimport xml.etree.ElementTree as ET\n\nasync def execute(url, limit=20):\n    \"\"\"Read and parse RSS/Atom feeds.\"\"\"\n    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:\n        resp = await client.get(url, headers={\"User-Agent\": \"Mozilla/5.0 (compatible; bot/1.0)\"})\n        resp.raise_for_status()\n    root = ET.fromstring(resp.text)\n    entries = []\n    # RSS 2.0\n    for item in root.iter(\"item\"):\n        entry = {}\n        for field in (\"title\", \"link\", \"description\", \"pubDate\", \"author\", \"guid\"):\n            el = item.find(field)\n            if el is not None and el.text:\n                entry[field] = el.text.strip()\n        if \"description\" in entry:\n            entry[\"description\"] = entry[\"description\"][:500]\n        entries.append(entry)\n    # Atom\n    if not entries:\n        ns = {\"atom\": \"http://www.w3.org/2005/Atom\"}\n        for item in root.findall(\".//atom:entry\", ns):\n            entry = {}\n            t = item.find(\"atom:title\", ns)\n            if t is not None and t.text:\n                entry[\"title\"] = t.text.strip()\n            link = item.find(\"atom:link\", ns)\n            if link is not None:\n                entry[\"link\"] = link.get(\"href\", \"\")\n            s = item.find(\"atom:summary\", ns)\n            if s is not None and s.text:\n                entry[\"description\"] = s.text.strip()[:500]\n            u = item.find(\"atom:updated\", ns)\n            if u is not None and u.text:\n                entry[\"pubDate\"] = u.text.strip()\n            entries.append(entry)\n    return {\"entries\": entries[:limit], \"total\": len(entries), \"feed_url\": url}",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "RSS/Atom feed URL"},
                "limit": {"type": "integer", "description": "Max entries (default: 20)"},
            },
            "required": ["url"],
        },
    },
    # --- AKM Advisor CRM Skills ---
    {
        "name": "akm_list_projects",
        "display_name": "AKM: List Projects",
        "description": "List all business projects from AKM Advisor CRM.",
        "description_for_agent": (
            "List all projects in the AKM Advisor CRM/ERP system. "
            "Returns project names, keys, task statistics. No parameters needed. "
            "Use this when user asks about their business projects or tasks overview."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute():\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured. Go to Settings to add them.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    async with httpx.AsyncClient(timeout=20, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/context', headers=headers)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        data = r.json()\n"
            "        return {'project': {'id': data.get('id'), 'key': data.get('key'), 'name': data.get('name'), 'description': data.get('description'), 'total_issues': data.get('total_issues'), 'open_issues': data.get('open_issues'), 'in_progress_issues': data.get('in_progress_issues'), 'done_issues': data.get('done_issues'), 'statuses': data.get('statuses'), 'team_members': data.get('team_members')}}\n"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "akm_project_tasks",
        "display_name": "AKM: Project Tasks",
        "description": "Get tasks and backlog for the AKM project.",
        "description_for_agent": (
            "Get tasks/backlog for the project in AKM Advisor. "
            "Parameters: status (string, optional — filter: backlog, todo, in_progress, review, testing, done), "
            "include_done (boolean, optional, default false). "
            "Returns list of issues/tasks with their status, priority, assignee."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute(status=None, include_done=False):\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    params = {'limit': 200, 'include_done': str(include_done).lower()}\n"
            "    if status:\n"
            "        params['status'] = status\n"
            "    async with httpx.AsyncClient(timeout=20, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/issues', headers=headers, params=params)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        data = r.json()\n"
            "        items = data.get('items', data) if isinstance(data, dict) else data\n"
            "        return {'tasks': items, 'total': data.get('total', len(items))}\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: backlog, todo, in_progress, review, testing, done"},
                "include_done": {"type": "boolean", "description": "Include completed tasks (default: false)"},
            },
        },
    },
    {
        "name": "akm_get_task",
        "display_name": "AKM: Get Task",
        "description": "Get a specific task by ID from AKM project.",
        "description_for_agent": (
            "Get detailed info about a specific task/issue in AKM Advisor. "
            "Parameters: task_id (string, required — issue ID or key like PROJ-123). "
            "Returns full task details: summary, description, status, priority, comments, assignee."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute(task_id):\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    async with httpx.AsyncClient(timeout=20, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/issues/{task_id}', headers=headers)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        return r.json()\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task/issue ID or key (e.g. PROJ-123)"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "akm_email_accounts",
        "display_name": "AKM: Email Accounts",
        "description": "List connected email accounts from AKM Advisor.",
        "description_for_agent": (
            "List all connected email accounts in AKM Advisor. "
            "No parameters needed. Returns account email addresses, providers, sync status, "
            "and message counts. Use this first to discover available email accounts."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute():\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    async with httpx.AsyncClient(timeout=20, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/email/accounts', headers=headers)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        data = r.json()\n"
            "        return {'accounts': data.get('items', []), 'total': data.get('total', 0)}\n"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "akm_email_messages",
        "display_name": "AKM: Email Messages",
        "description": "List and search email messages from AKM Advisor.",
        "description_for_agent": (
            "List and search email messages in AKM Advisor across all accounts. "
            "Parameters: folder (string, optional, default 'inbox' — inbox, sent, drafts, trash, spam), "
            "search (string, optional — search in subject, sender, snippet), "
            "is_read (boolean, optional — filter read/unread), "
            "limit (integer, optional, default 50, max 200), page (integer, optional, default 1). "
            "Returns emails with subject, sender, date, snippet, read status."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute(folder='inbox', search=None, is_read=None, limit=50, page=1):\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    params = {'folder': folder, 'limit': min(limit, 200), 'page': page}\n"
            "    if search:\n"
            "        params['search'] = search\n"
            "    if is_read is not None:\n"
            "        params['is_read'] = str(is_read).lower()\n"
            "    async with httpx.AsyncClient(timeout=30, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/email/messages', headers=headers, params=params)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        data = r.json()\n"
            "        return {'emails': data.get('items', []), 'total': data.get('total', 0), "
            "'page': data.get('page', page), 'pages': data.get('pages', 0)}\n"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Folder: inbox, sent, drafts, trash, spam (default: inbox)"},
                "search": {"type": "string", "description": "Search in subject, sender, snippet"},
                "is_read": {"type": "boolean", "description": "Filter by read status (true/false)"},
                "limit": {"type": "integer", "description": "Results per page (default: 50, max: 200)"},
                "page": {"type": "integer", "description": "Page number (default: 1)"},
            },
        },
    },
    {
        "name": "akm_email_stats",
        "display_name": "AKM: Email Stats",
        "description": "Get email statistics from AKM Advisor.",
        "description_for_agent": (
            "Get email statistics from AKM Advisor — message counts per folder, "
            "unread counts, per-account breakdown. No parameters needed. "
            "Use this for a quick overview of the email situation."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute():\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    async with httpx.AsyncClient(timeout=20, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/email/stats', headers=headers)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        return r.json()\n"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "akm_permissions",
        "display_name": "AKM: Permissions",
        "description": "Get agent permissions and available sections from AKM Advisor.",
        "description_for_agent": (
            "Get the current agent API key permissions from AKM Advisor. "
            "Returns which sections are accessible (e.g. wiki, email, leads, deals, contacts, goals, projects, sprints, roadmap), "
            "which projects the key can access, and pipeline access scope. No parameters needed. "
            "Use this to understand what data the agent can access in AKM Advisor."
        ),
        "category": "crm",
        "code": (
            "import httpx\n"
            "import os\n"
            "async def execute():\n"
            "    api_key = os.environ.get('AKM_ADVISOR_API_KEY', '')\n"
            "    base_url = os.environ.get('AKM_ADVISOR_URL', '').rstrip('/')\n"
            "    if not api_key or not base_url:\n"
            "        return {'error': 'AKM Advisor API key/URL not configured.'}\n"
            "    headers = {'X-Agent-Key': api_key}\n"
            "    async with httpx.AsyncClient(timeout=20, verify=False) as client:\n"
            "        r = await client.get(f'{base_url}/permissions', headers=headers)\n"
            "        if r.status_code != 200:\n"
            "            return {'error': f'API error {r.status_code}: {r.text[:500]}'}\n"
            "        return r.json()\n"
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


async def create_system_skills(db: AsyncIOMotorDatabase):
    """Create or update system skills. Removes obsolete ones."""
    import logging
    logger = logging.getLogger(__name__)
    svc = SkillService(db)

    # Names of skills that were removed and should be cleaned up
    OBSOLETE_SKILLS = [
        "akm_list_lead_boards", "akm_list_leads",
        "akm_list_deal_boards", "akm_list_deals",
        "akm_list_contacts", "akm_crm_goals",
    ]
    for name in OBSOLETE_SKILLS:
        existing = await svc.find_one({"name": name})
        if existing:
            await svc.delete(existing.id)
            logger.info(f"Removed obsolete system skill: {name}")

    system_skill_names = {s["name"] for s in SYSTEM_SKILLS}

    for skill_data in SYSTEM_SKILLS:
        existing = await svc.find_one({"name": skill_data["name"]})
        if existing:
            # Update system skills if code or description changed
            updates = {}
            if existing.code != skill_data["code"]:
                updates["code"] = skill_data["code"]
            if existing.description != skill_data["description"]:
                updates["description"] = skill_data["description"]
            desc_for_agent = skill_data.get("description_for_agent", "")
            if existing.description_for_agent != desc_for_agent:
                updates["description_for_agent"] = desc_for_agent
            new_schema = skill_data.get("input_schema", {})
            if existing.input_schema != new_schema:
                updates["input_schema"] = new_schema
            if updates and existing.is_system:
                await svc.update(existing.id, updates)
                logger.info(f"Updated system skill: {skill_data['name']}")
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
        logger.info(f"Created system skill: {skill_data['name']}")

        # Create filesystem directory + manifest
        init_skill_directory(skill)
