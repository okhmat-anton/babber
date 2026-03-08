"""
Multi-stage Copilot-style pipeline for agent responses.

Architecture (6 stages, conditional execution):

  CLASSIFY  (rule-based, <1ms)  → fast intent/complexity detection, no LLM
  UNDERSTAND (focused LLM, ONLY medium/complex) → refined intent, skill suggestions
  GATHER    (conditional data collection) → memory, URLs, project context
  PLAN      (focused LLM, ONLY medium/complex with skills) → execution plan
  EXECUTE   (skill calls + smart arg inference) → results
  SYNTHESIZE (full LLM with all context) → final response

Key principles:
- Minimal stages for simple messages (greeting → CLASSIFY + SYNTHESIZE only)
- Conditional execution — only run stages that are needed
- Smart arg inference — auto-fill skill params from context, not relying on LLM
- Works with weak models (3B–7B) — focused prompts, robust JSON extraction
- Information-gathering skills run in pipeline; content-generation in SYNTHESIZE
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.llm.base import GenerationParams

# Hard timeout for SYNTHESIZE stage (LLM call) in seconds.
# If exceeded, pipeline returns a partial/error response instead of hanging.
# Set to 300s to match httpx timeout — with Ollama semaphore serialisation,
# the LLM call itself shouldn't take this long, but we keep a generous
# upper bound for large context windows.
SYNTHESIZE_TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)

# ── Rule-based patterns ──────────────────────────────────────────────

URL_PATTERN = re.compile(r'https?://[^\s<>"\')\]]+')
CODE_BLOCK_PATTERN = re.compile(r'```[\s\S]*?```')
SEARCH_KEYWORDS_RU = re.compile(
    r'\b(найди|поищи|погугли|загугли|поиск\s|искать|в\s+интернете|в\s+сети|что\s+такое|как\s+работает)\b',
    re.IGNORECASE,
)
SEARCH_KEYWORDS_EN = re.compile(
    r'\b(search\s+for|google|look\s+up|find\s+online|browse|what\s+is|how\s+does)\b',
    re.IGNORECASE,
)
GREETING_RU = re.compile(
    r'^\s*(привет|здравствуй|хай|здарова|добрый\s+(день|вечер|утро)|салют|хелло|ку|йо)\s*[!?.]*\s*$',
    re.IGNORECASE,
)
GREETING_EN = re.compile(
    r'^\s*(hi|hello|hey|yo|sup|good\s+(morning|evening|afternoon)|howdy|greetings)\s*[!?.]*\s*$',
    re.IGNORECASE,
)
STUDY_KEYWORDS_RU = re.compile(
    r'\b(изучи|выучи|прочитай|запомни|законспектируй|проанализируй\s+материал|изучить|выучить)\b',
    re.IGNORECASE,
)
STUDY_KEYWORDS_EN = re.compile(
    r'\b(study|learn|memorize|read\s+and\s+memorize|study\s+this|learn\s+from)\b',
    re.IGNORECASE,
)
RECALL_KEYWORDS_RU = re.compile(
    r'\b(вспомни|что\s+ты\s+знаешь|что\s+(?:ты\s+)?помнишь|напомни|расскажи\s+что\s+(?:выучил|изучил|запомнил))\b',
    re.IGNORECASE,
)
RECALL_KEYWORDS_EN = re.compile(
    r'\b(recall|what\s+do\s+you\s+(?:know|remember)|remember\s+about|what\s+did\s+you\s+(?:learn|study))\b',
    re.IGNORECASE,
)
PROJECT_SLUG_PATTERN = re.compile(
    r'\b(?:проект[аеу]?\s+|project\s+)[\"\']?([a-z0-9_-]+)[\"\']?',
    re.IGNORECASE,
)
TASK_PATTERN = re.compile(
    r'\b(?:задач[аеуи]\s+|task\s+|T-)\s*[\"\']?([A-Za-z0-9_-]+)[\"\']?',
    re.IGNORECASE,
)

# ── Skill categories ─────────────────────────────────────────────────
# "gather" skills collect information — safe to run automatically
# "action" skills modify state — only run from explicit plan
GATHER_SKILLS = frozenset({
    "memory_search", "web_fetch", "web_scrape", "file_read",
    "project_file_read", "project_list_files", "project_context_build",
    "task_context_build", "json_parse", "text_summarize",
    "memory_deep_process", "speech_recognize",
    "study_material", "recall_knowledge",
    "creator_context",
    "fact_read",
})

ACTION_SKILLS = frozenset({
    "memory_store", "file_write", "project_file_write", "shell_exec",
    "code_execute", "project_update_task", "project_task_comment",
    "project_run_code", "sound_generate",
    "fact_save", "fact_extract",
})

# "safe" action skills that can be auto-executed without user confirmation
# These are reversible or low-risk (project files, comments, memory)
SAFE_ACTION_SKILLS = frozenset({
    "memory_store", "project_file_write", "project_update_task",
    "project_task_comment", "code_execute", "sound_generate",
    "fact_save", "fact_extract",
})

# Dangerous skills require confirmation (never auto-execute)
DANGEROUS_ACTION_SKILLS = frozenset({
    "shell_exec", "file_write",
})

# ── Smart arg inference ──────────────────────────────────────────────


def _infer_args(skill_name: str, planned_args: dict, context: dict) -> dict:
    """
    Auto-fill missing skill arguments from pipeline context.
    Returns merged args dict.
    """
    args = dict(planned_args)  # copy
    user_input = context.get("user_input", "")
    detected_urls = context.get("detected_urls", [])
    detected_project = context.get("detected_project")
    detected_task = context.get("detected_task")

    # Resolve template variables: {{step2.output}}, {{previous_result}}, etc.
    _template_re = re.compile(r'\{\{[^}]+\}\}')
    for k, v in list(args.items()):
        if isinstance(v, str) and _template_re.search(v):
            args[k] = ""  # Clear unresolvable template — let inference fill it

    if skill_name == "memory_search":
        if "query" not in args or not args["query"]:
            args["query"] = user_input
        if "limit" not in args:
            args["limit"] = 5

    elif skill_name == "memory_store":
        if "content" not in args or not args["content"]:
            args["content"] = user_input
        if "type" not in args:
            args["type"] = "conversation"

    elif skill_name in ("web_fetch", "web_scrape"):
        if "url" not in args or not args["url"]:
            if detected_urls:
                args["url"] = detected_urls[0]

    elif skill_name == "text_summarize":
        if "text" not in args or not args["text"]:
            args["text"] = user_input

    elif skill_name == "code_execute":
        if "code" not in args or not args["code"]:
            blocks = CODE_BLOCK_PATTERN.findall(user_input)
            if blocks:
                code = blocks[0].strip('`').strip()
                if code.startswith(('python', 'py')):
                    code = code.split('\n', 1)[1] if '\n' in code else code
                args["code"] = code

    elif skill_name in ("project_context_build", "project_list_files"):
        if "project_slug" not in args or not args["project_slug"]:
            if detected_project:
                args["project_slug"] = detected_project

    elif skill_name == "task_context_build":
        if "project_slug" not in args or not args["project_slug"]:
            if detected_project:
                args["project_slug"] = detected_project
        if "task_id" not in args or not args["task_id"]:
            if detected_task:
                args["task_id"] = detected_task

    elif skill_name == "project_file_read":
        if "project_slug" not in args or not args["project_slug"]:
            if detected_project:
                args["project_slug"] = detected_project

    elif skill_name == "project_file_write":
        if "project_slug" not in args or not args["project_slug"]:
            if detected_project:
                args["project_slug"] = detected_project
        # Extract file path from user input
        if "path" not in args or not args["path"]:
            path_match = re.search(
                r'(?:файл[а]?\s+|file\s+)["\']?([\w._/\\-]+\.[\w]+)["\']?',
                user_input, re.I,
            )
            if path_match:
                args["path"] = path_match.group(1)
        # Extract content from user input (quoted or after keywords)
        if "content" not in args or not args["content"]:
            # Try 'содержимым "X"' or 'content "X"' patterns
            content_match = re.search(
                r"(?:содержим(?:ое|ым)\s+|content\s+)['\"](.+?)['\"]",
                user_input, re.I,
            )
            if content_match:
                args["content"] = content_match.group(1)
            else:
                # Try 'с текстом "X"' pattern
                content_match2 = re.search(
                    r"(?:с\s+текстом\s+|with\s+text\s+)['\"](.+?)['\"]",
                    user_input, re.I,
                )
                if content_match2:
                    args["content"] = content_match2.group(1)

    elif skill_name == "project_run_code":
        if "project_slug" not in args or not args["project_slug"]:
            if detected_project:
                args["project_slug"] = detected_project

    elif skill_name == "json_parse":
        if "text" not in args or not args["text"]:
            args["text"] = user_input

    elif skill_name == "file_read":
        if "path" not in args or not args["path"]:
            path_match = re.search(
                r'(?:файл[а]?\s+|file\s+|read\s+)["\']?([/\w._-]+)["\']?',
                user_input, re.I,
            )
            if path_match:
                args["path"] = path_match.group(1)

    elif skill_name == "shell_exec":
        if "command" not in args or not args["command"]:
            cmd_match = re.search(r'[`"\'](.+?)[`"\']', user_input)
            if cmd_match:
                args["command"] = cmd_match.group(1)

    elif skill_name == "sound_generate":
        if "text" not in args or not args["text"]:
            args["text"] = user_input

    elif skill_name == "study_material":
        if not args.get("text") and not args.get("file_path") and not args.get("topic"):
            # Try to extract file path from user input
            file_match = re.search(
                r'(?:файл[а]?\s+|file\s+)["\']?([/\w._-]+\.\w+)["\']?',
                user_input, re.I,
            )
            if file_match:
                args["file_path"] = file_match.group(1)
            else:
                # Use the user input as topic
                # Strip study keywords to get the actual topic
                topic = re.sub(
                    r'\b(изучи|выучи|прочитай|запомни|законспектируй|study|learn|memorize)\b',
                    '', user_input, flags=re.I,
                ).strip()
                if topic:
                    args["topic"] = topic
        if "depth" not in args:
            args["depth"] = "normal"

    elif skill_name == "recall_knowledge":
        if "query" not in args or not args["query"]:
            # Strip recall keywords to get the actual query
            query = re.sub(
                r'\b(вспомни|что\s+ты\s+знаешь|напомни|recall|remember|what\s+do\s+you\s+know)\b',
                '', user_input, flags=re.I,
            ).strip()
            args["query"] = query or user_input
        if "depth" not in args:
            args["depth"] = "quick"

    elif skill_name == "fact_save":
        if "content" not in args or not args["content"]:
            args["content"] = user_input
        if "type" not in args:
            args["type"] = "fact"

    elif skill_name == "fact_read":
        if "query" not in args or not args["query"]:
            args["query"] = user_input
        if "limit" not in args:
            args["limit"] = 20

    elif skill_name == "fact_extract":
        if "text" not in args or not args["text"]:
            args["text"] = user_input

    return args


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    stage: str
    data: dict
    raw_llm_response: str = ""
    tokens_used: int = 0
    duration_ms: int = 0


@dataclass
class Classification:
    """Fast rule-based classification result."""
    intent: str  # greeting, question, task, code, search, creative, project_work
    complexity: str  # simple, medium, complex
    is_greeting: bool
    skip_to_synthesize: bool  # True for greetings without skills
    skip_understand: bool  # True for simple messages
    skip_plan: bool  # True when no skills needed
    detected_urls: list[str] = field(default_factory=list)
    needs_web_search: bool = False
    has_code_blocks: bool = False
    detected_project: str | None = None
    detected_task: str | None = None


class StagedPipeline:
    """
    Multi-stage Copilot-style pipeline for agent responses.

    Works INDEPENDENTLY of the model's ability to generate <<<SKILL>>> markers,
    making it effective even with small models (3B, 7B).
    """

    def __init__(self, engine: Any, agent_context: Any, tracker: Any = None):
        self.engine = engine
        self.ctx = agent_context
        self.tracker = tracker
        # Model (resolved once)
        self._provider: str | None = None
        self._base_url: str | None = None
        self._model_name: str | None = None
        self._api_key: str | None = None
        # Cumulative counters
        self._total_tokens = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._llm_calls = 0

    # ── Helpers ───────────────────────────────────────────────────

    async def _ensure_model(self, model_id: str | None = None):
        """Resolve model once and cache."""
        if self._provider is not None:
            return
        if model_id:
            self._provider, self._base_url, self._model_name, self._api_key = \
                await self.engine.resolve_model(model_id)
        else:
            self._provider, self._base_url, self._model_name, self._api_key = \
                await self.engine.resolve_agent_model(self.ctx.agent)

    async def _llm(self, messages: list[dict], temperature: float | None = None):
        """Make a focused LLM call, optionally overriding temperature."""
        gp = self.ctx.gen_params
        if temperature is not None:
            gp = GenerationParams(
                temperature=temperature,
                top_p=gp.top_p,
                top_k=gp.top_k,
                max_tokens=gp.max_tokens,
                num_ctx=gp.num_ctx,
                repeat_penalty=gp.repeat_penalty,
                num_predict=gp.num_predict,
                stop=gp.stop,
                num_thread=gp.num_thread,
                num_gpu=gp.num_gpu,
            )
        resp = await self.engine.chat_with_model(
            self._provider, self._base_url, self._model_name, self._api_key,
            messages, gp,
        )
        self._total_tokens += resp.total_tokens
        self._prompt_tokens += getattr(resp, "prompt_tokens", 0)
        self._completion_tokens += getattr(resp, "completion_tokens", 0)
        self._llm_calls += 1
        return resp

    def _skills_catalog(self, category: str | None = None) -> str:
        """
        Build rich skill descriptions for LLM prompts.
        Includes param names, types, and required markers.

        Args:
            category: "gather", "action", or None for all.
        """
        lines = []
        for s in self.ctx.skills:
            name = s["name"]
            if category == "gather" and name not in GATHER_SKILLS:
                continue
            if category == "action" and name not in ACTION_SKILLS:
                continue

            desc = s.get("description_for_agent") or s.get("description", "")
            schema = s.get("input_schema") or {}
            props = schema.get("properties", {})
            required = set(schema.get("required", []))
            params = []
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "string")
                pdesc = pinfo.get("description", "")
                req = " REQUIRED" if pname in required else ""
                params.append(f"    {pname} ({ptype}{req}){': ' + pdesc if pdesc else ''}")
            params_block = "\n".join(params) if params else "    (no parameters)"
            cat_tag = " [info-gathering]" if name in GATHER_SKILLS else " [action]"
            lines.append(f"  {name}{cat_tag}: {desc}\n{params_block}")
        return "\n\n".join(lines) if lines else "  (no skills available)"

    def _skills_short(self) -> str:
        """Short skill list for compact prompts (just name + one-line desc)."""
        lines = []
        for s in self.ctx.skills:
            desc = s.get("description_for_agent") or s.get("description", "")
            first_sentence = desc.split('.')[0] + '.' if desc else ''
            lines.append(f"  - {s['name']}: {first_sentence}")
        return "\n".join(lines) if lines else "  (no skills)"

    def _skill_names(self) -> set[str]:
        """Get set of available skill names."""
        return {s["name"] for s in self.ctx.skills}

    def _extract_json(self, text: str) -> dict | None:
        """Robust JSON extraction from LLM output."""
        if not text:
            return None
        # 1. Try code block
        m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?\s*```', text)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass
        # 2. Try full text
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        # 3. Find JSON object
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None

    # ── System skill handlers (need DB/service access) ──────────────

    _SYSTEM_SKILL_HANDLERS = {
        "memory_search", "memory_store", "memory_deep_process",
        "text_summarize", "code_execute", "web_scrape", "web_fetch",
        "sound_generate", "speech_recognize",
        "study_material", "recall_knowledge",
        "creator_context",
        "fact_save", "fact_read", "fact_extract",
    }

    async def _exec_skill(self, name: str, args: dict) -> dict:
        """Execute a skill safely. System skills are handled internally."""
        if name not in self._skill_names():
            return {"error": f"Skill '{name}' not found"}
        try:
            # Try system skill handler first
            if name in self._SYSTEM_SKILL_HANDLERS:
                result = await self._exec_system_skill(name, args)
                if result is not None:
                    return result
            # Fallback to code-based execution
            return await self.engine.execute_skill(name, args, self.ctx.skills)
        except Exception as e:
            logger.warning(f"Skill {name} execution error: {e}")
            return {"error": str(e)}

    async def _exec_system_skill(self, name: str, args: dict) -> dict | None:
        """Handle system skills that need direct service access."""
        db = self.engine.db
        agent_id = str(self.ctx.agent.id)

        if name == "memory_search":
            return await self._sys_memory_search(db, agent_id, args)
        elif name == "memory_store":
            return await self._sys_memory_store(db, agent_id, args)
        elif name == "text_summarize":
            return await self._sys_text_summarize(args)
        elif name == "code_execute":
            return await self._sys_code_execute(args)
        elif name == "web_scrape":
            return await self._sys_web_scrape(args)
        elif name == "web_fetch":
            return await self._sys_web_fetch(args)
        elif name == "memory_deep_process":
            return {"result": "memory_deep_process requires manual trigger"}
        elif name == "sound_generate":
            return await self._sys_sound_generate(db, args)
        elif name == "speech_recognize":
            return await self._sys_speech_recognize(db, args)
        elif name == "study_material":
            return await self._sys_study_material(db, agent_id, args)
        elif name == "recall_knowledge":
            return await self._sys_recall_knowledge(db, agent_id, args)
        elif name == "creator_context":
            return await self._sys_creator_context(db, args)
        elif name == "fact_save":
            return await self._sys_fact_save(db, agent_id, args)
        elif name == "fact_read":
            return await self._sys_fact_read(db, agent_id, args)
        elif name == "fact_extract":
            return await self._sys_fact_extract(db, agent_id, args)
        return None

    async def _sys_memory_search(self, db, agent_id: str, args: dict) -> dict:
        """Search agent memories by text matching."""
        from app.mongodb.services import MemoryService
        svc = MemoryService(db)
        query = str(args.get("query", "")).lower()
        limit = int(args.get("limit", 5))

        memories = await svc.get_by_agent(agent_id, limit=200)
        if not memories:
            return {"result": [], "message": "No memories found for this agent"}

        if query:
            # Score by keyword match (simple relevance)
            scored = []
            query_words = set(query.split())
            for m in memories:
                text = f"{m.title} {m.content}".lower()
                word_hits = sum(1 for w in query_words if w in text)
                exact_hit = 1 if query in text else 0
                score = word_hits * 2 + exact_hit * 5 + m.importance
                if word_hits > 0 or exact_hit > 0:
                    scored.append((score, m))
            scored.sort(key=lambda x: x[0], reverse=True)
            memories = [m for _, m in scored[:limit]]
        else:
            # Return most recent/important
            memories.sort(key=lambda m: m.importance, reverse=True)
            memories = memories[:limit]

        results = [
            {"title": m.title, "content": m.content[:500], "type": m.type,
             "importance": m.importance, "tags": m.tags, "category": m.category}
            for m in memories
        ]
        return {"result": results}

    async def _sys_memory_store(self, db, agent_id: str, args: dict) -> dict:
        """Store a new memory entry."""
        from app.mongodb.services import MemoryService
        from app.mongodb.models.memory import MongoMemory
        svc = MemoryService(db)
        mem = MongoMemory(
            agent_id=agent_id,
            title=args.get("title", "Untitled"),
            content=args.get("content", ""),
            type=args.get("type", "note"),
            importance=float(args.get("importance", 0.5)),
            tags=args.get("tags", []),
            source="agent",
        )
        created = await svc.create(mem)
        return {"result": {"id": created.id, "title": created.title, "stored": True}}

    async def _sys_text_summarize(self, args: dict) -> dict:
        """Summarize text using LLM."""
        text = args.get("text", "")
        max_length = int(args.get("max_length", 200))
        if not text or text.startswith("{{"):
            return {"result": "(no text to summarize)"}
        # Quick LLM summarization
        try:
            resp = await self._llm_call(
                [{"role": "user", "content": f"Summarize in {max_length} words max:\n\n{text[:3000]}"}],
                system="You are a concise summarizer. Output ONLY the summary, no preamble.",
                temperature=0.1,
            )
            return {"result": resp.content if resp else text[:max_length]}
        except Exception as e:
            logger.warning(f"text_summarize LLM failed: {e}")
            return {"result": text[:max_length * 5]}

    async def _sys_code_execute(self, args: dict) -> dict:
        """Execute Python code in a subprocess sandbox."""
        import asyncio as _asyncio
        code = args.get("code", "")
        if not code:
            return {"error": "No code provided"}
        try:
            proc = await _asyncio.create_subprocess_exec(
                "python3", "-c", code,
                stdout=_asyncio.subprocess.PIPE,
                stderr=_asyncio.subprocess.PIPE,
            )
            stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=30)
            return {
                "result": {
                    "stdout": stdout.decode()[:5000],
                    "stderr": stderr.decode()[:2000],
                    "returncode": proc.returncode,
                }
            }
        except _asyncio.TimeoutError:
            return {"error": "Code execution timed out (30s)"}
        except Exception as e:
            return {"error": f"Code execution failed: {e}"}

    async def _sys_web_fetch(self, args: dict) -> dict:
        """Fetch a URL via HTTP."""
        import httpx
        url = args.get("url", "")
        method = args.get("method", "GET").upper()
        if not url:
            return {"error": "No URL provided"}
        try:
            async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=15) as client:
                r = await getattr(client, method.lower())(
                    url, headers={"User-Agent": "Mozilla/5.0"}
                )
                return {"result": {"status": r.status_code, "text": r.text[:5000]}}
        except Exception as e:
            return {"error": f"Web fetch failed: {e}"}

    async def _sys_web_scrape(self, args: dict) -> dict:
        """Scrape web page content."""
        import httpx
        import re as _re
        url = args.get("url", "")
        if not url:
            return {"error": "No URL provided"}
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                html = r.text
                # Strip scripts/styles
                html = _re.sub(r'<script[^>]*>.*?</script>', '', html, flags=_re.DOTALL)
                html = _re.sub(r'<style[^>]*>.*?</style>', '', html, flags=_re.DOTALL)
                # Extract text
                text = _re.sub(r'<[^>]+>', ' ', html)
                text = _re.sub(r'\s+', ' ', text).strip()
                return {"result": {"url": url, "status": r.status_code, "text": text[:5000]}}
        except Exception as e:
            return {"error": f"Web scrape failed: {e}"}

    async def _sys_sound_generate(self, db, args: dict) -> dict:
        """Generate audio from text using TTS."""
        from app.services.audio_service import text_to_speech
        text = args.get("text", "")
        if not text:
            return {"error": "No text provided for TTS"}
        try:
            result = await text_to_speech(
                db,
                text=text[:10000],
                voice=args.get("voice"),
                provider=args.get("provider"),
            )
            return {"result": result}
        except Exception as e:
            logger.warning(f"sound_generate failed: {e}")
            return {"error": f"TTS failed: {e}"}

    async def _sys_speech_recognize(self, db, args: dict) -> dict:
        """Transcribe audio to text using STT."""
        from app.services.audio_service import speech_to_text
        audio_url = args.get("audio_url", "")
        if not audio_url:
            return {"error": "No audio_url provided for STT"}
        try:
            # If it's a local path, read the file
            import os
            audio_data = None
            audio_format = "wav"
            if audio_url.startswith("/api/uploads/audio/"):
                filename = audio_url.split("/")[-1]
                from app.services.audio_service import AUDIO_DIR
                fpath = AUDIO_DIR / filename
                if fpath.exists():
                    audio_data = fpath.read_bytes()
                    audio_format = filename.rsplit(".", 1)[-1] if "." in filename else "wav"
                else:
                    return {"error": f"Audio file not found: {filename}"}
            else:
                # Fetch remote URL
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(audio_url)
                    if r.status_code != 200:
                        return {"error": f"Failed to fetch audio: HTTP {r.status_code}"}
                    audio_data = r.content
                    audio_format = audio_url.rsplit(".", 1)[-1] if "." in audio_url else "wav"

            result = await speech_to_text(
                db,
                audio_data=audio_data,
                audio_format=audio_format,
                provider=args.get("provider"),
                language=args.get("language"),
            )
            return {"result": result}
        except Exception as e:
            logger.warning(f"speech_recognize failed: {e}")
            return {"error": f"STT failed: {e}"}

    # ── Study & Recall skills ────────────────────────────────────────

    async def _sys_study_material(self, db, agent_id: str, args: dict) -> dict:
        """
        Study material: read source → summarize → extract topics → detailed notes → links.
        Multi-step LLM pipeline that stores knowledge in agent memory.
        """
        from app.mongodb.services import MemoryService, MemoryLinkService
        from app.mongodb.models.memory import MongoMemory, MongoMemoryLink
        from app.config import get_settings
        import os
        from pathlib import Path

        svc = MemoryService(db)
        link_svc = MemoryLinkService(db)

        topic = args.get("topic", "")
        file_path = args.get("file_path", "")
        text = args.get("text", "")
        depth = args.get("depth", "normal")

        # ── Step 1: Resolve source text ──
        source_name = topic or file_path or "direct text"
        material = text

        if file_path and not material:
            # Read from agent's data directory
            settings = get_settings()
            agent_svc = None
            try:
                from app.mongodb.services import AgentService
                agent_svc = AgentService(db)
                agent = await agent_svc.get_by_id(agent_id)
                if agent:
                    agents_dir = Path(settings.AGENTS_DIR).resolve()
                    data_dir = agents_dir / agent.name / "data"
                    fpath = (data_dir / file_path).resolve()
                    if str(fpath).startswith(str(agents_dir)) and fpath.exists():
                        material = fpath.read_text(encoding="utf-8", errors="replace")
                        source_name = f"file:{file_path}"
                    else:
                        return {"error": f"File not found or access denied: {file_path}"}
            except Exception as e:
                return {"error": f"Failed to read file: {e}"}

        if not material and topic:
            # Use topic as the material text itself (agent was given a topic to think about)
            material = topic
            source_name = f"topic:{topic}"

        if not material:
            return {"error": "No material provided. Provide text, file_path, or topic."}

        # Truncate very long material
        max_chars = {"quick": 3000, "normal": 8000, "deep": 15000}.get(depth, 8000)
        material_truncated = material[:max_chars]
        total_len = len(material)

        # ── Step 2: General summary + tags ──
        await self._ensure_model()
        try:
            summary_resp = await self._llm([
                {"role": "system", "content": (
                    "You are a study assistant. Analyze material and output JSON only.\n"
                    "Output format: {\"summary\": \"2-4 sentence summary\", \"tags\": [\"tag1\", \"tag2\", ...], \"main_subject\": \"one phrase\"}"
                )},
                {"role": "user", "content": f"Study this material and create a summary:\n\n{material_truncated[:4000]}"},
            ], temperature=0.2)
            summary_data = self._extract_json(summary_resp.content or "") or {}
        except Exception as e:
            logger.warning(f"study_material summary LLM failed: {e}")
            summary_data = {"summary": material_truncated[:300], "tags": [], "main_subject": source_name}

        summary_text = summary_data.get("summary", material_truncated[:300])
        tags = summary_data.get("tags", [])[:10]
        main_subject = summary_data.get("main_subject", source_name)

        # Save general summary
        summary_mem = MongoMemory(
            agent_id=agent_id,
            type="summary",
            title=f"📚 {main_subject}",
            content=f"Source: {source_name} ({total_len} chars)\n\n{summary_text}",
            source="study",
            importance=0.8,
            tags=tags,
            category="knowledge",
        )
        summary_mem = await svc.create(summary_mem)
        created_ids = [summary_mem.id]

        # ── Step 3: Extract key topics ──
        max_topics = {"quick": 3, "normal": 6, "deep": 12}.get(depth, 6)
        try:
            topics_resp = await self._llm([
                {"role": "system", "content": (
                    f"Extract up to {max_topics} key topics/concepts from the material. Output JSON only.\n"
                    "Format: {\"topics\": [{\"title\": \"Topic Name\", \"importance\": 0.7, \"section\": \"where in material\", \"brief\": \"1-2 sentence description\"}]}"
                )},
                {"role": "user", "content": f"Extract key topics from:\n\n{material_truncated[:5000]}"},
            ], temperature=0.2)
            topics_data = self._extract_json(topics_resp.content or "") or {}
        except Exception as e:
            logger.warning(f"study_material topics LLM failed: {e}")
            topics_data = {"topics": []}

        topics = (topics_data.get("topics") or [])[:max_topics]

        # Save each topic as a fact
        topic_mems = []
        for t in topics:
            title = t.get("title", "Untitled topic")
            importance = min(1.0, max(0.1, float(t.get("importance", 0.5))))
            brief = t.get("brief", "")
            section = t.get("section", "")
            content = brief
            if section:
                content += f"\n📍 Location: {section} in {source_name}"

            mem = MongoMemory(
                agent_id=agent_id,
                type="fact",
                title=title,
                content=content,
                source="study",
                importance=importance,
                tags=tags,
                category="knowledge",
            )
            mem = await svc.create(mem)
            topic_mems.append(mem)
            created_ids.append(mem.id)

            # Link topic to summary (part_of)
            link = MongoMemoryLink(
                agent_id=agent_id,
                source_id=mem.id,
                target_id=summary_mem.id,
                relation_type="part_of",
                strength=0.8,
                description=f"Topic from: {main_subject}",
                created_by="system",
            )
            await link_svc.create(link)

        # ── Step 4: Detailed notes for important topics (normal/deep only) ──
        detailed_count = 0
        if depth in ("normal", "deep"):
            important_topics = [t for t in topics if float(t.get("importance", 0.5)) >= 0.6]
            if depth == "deep":
                important_topics = topics  # all topics get detailed notes

            for i, t in enumerate(important_topics[:8]):
                title = t.get("title", "")
                try:
                    detail_resp = await self._llm([
                        {"role": "system", "content": (
                            "Create a detailed study note about the given topic based on the material. "
                            "Include specific facts, references to where in the material this is found, "
                            "and any important details. Output plain text (not JSON)."
                        )},
                        {"role": "user", "content": (
                            f"Topic: {title}\n\nMaterial:\n{material_truncated[:4000]}\n\n"
                            f"Write a detailed note about '{title}' based on this material. "
                            f"Reference specific sections/parts of the source: {source_name}"
                        )},
                    ], temperature=0.3)
                    detail_text = (detail_resp.content or "").strip()
                except Exception as e:
                    logger.warning(f"study_material detail note LLM failed for '{title}': {e}")
                    detail_text = t.get("brief", "")

                if detail_text:
                    note_mem = MongoMemory(
                        agent_id=agent_id,
                        type="summary",
                        title=f"📝 {title} (detailed)",
                        content=f"Source: {source_name}\n\n{detail_text}",
                        source="study",
                        importance=float(t.get("importance", 0.6)),
                        tags=tags + [title.lower().replace(" ", "_")],
                        category="knowledge",
                    )
                    note_mem = await svc.create(note_mem)
                    created_ids.append(note_mem.id)
                    detailed_count += 1

                    # Link detailed note to its topic
                    if i < len(topic_mems):
                        link = MongoMemoryLink(
                            agent_id=agent_id,
                            source_id=note_mem.id,
                            target_id=topic_mems[i].id,
                            relation_type="related_to",
                            strength=0.9,
                            description=f"Detailed note for topic",
                            created_by="system",
                        )
                        await link_svc.create(link)

        # ── Step 5: Cross-links between related topics ──
        if len(topic_mems) >= 2 and depth != "quick":
            for i in range(len(topic_mems)):
                for j in range(i + 1, min(i + 3, len(topic_mems))):
                    link = MongoMemoryLink(
                        agent_id=agent_id,
                        source_id=topic_mems[i].id,
                        target_id=topic_mems[j].id,
                        relation_type="related_to",
                        strength=0.5,
                        description=f"Co-studied from {source_name}",
                        created_by="system",
                    )
                    await link_svc.create(link)

        return {
            "result": {
                "studied": True,
                "source": source_name,
                "depth": depth,
                "summary": summary_text[:300],
                "topics_count": len(topics),
                "detailed_notes_count": detailed_count,
                "memory_entries_created": len(created_ids),
                "tags": tags,
            }
        }

    async def _sys_recall_knowledge(self, db, agent_id: str, args: dict) -> dict:
        """
        Recall knowledge: search memory for knowledge entries, aggregate results.
        """
        from app.mongodb.services import MemoryService
        svc = MemoryService(db)

        query = str(args.get("query", "")).lower()
        depth = args.get("depth", "quick")
        filter_tags = args.get("tags") or []

        if not query:
            return {"error": "No query provided for recall"}

        # Search all knowledge memories
        all_memories = await svc.get_by_agent(agent_id, limit=500)
        knowledge = [m for m in all_memories if m.category == "knowledge"]

        if not knowledge:
            return {"result": [], "message": "No studied knowledge found. Use study_material first."}

        # Score by relevance
        query_words = set(query.split())
        scored = []
        for m in knowledge:
            text = f"{m.title} {m.content}".lower()
            tags_text = " ".join(m.tags or []).lower()
            word_hits = sum(1 for w in query_words if w in text or w in tags_text)
            exact_hit = 1 if query in text else 0
            tag_match = sum(1 for t in filter_tags if t.lower() in tags_text) if filter_tags else 0
            score = word_hits * 2 + exact_hit * 5 + tag_match * 3 + m.importance
            if word_hits > 0 or exact_hit > 0 or tag_match > 0:
                scored.append((score, m))

        if not scored:
            # Fallback: return most important knowledge
            knowledge.sort(key=lambda m: m.importance, reverse=True)
            scored = [(m.importance, m) for m in knowledge[:5]]

        scored.sort(key=lambda x: x[0], reverse=True)
        limit = 10 if depth == "detailed" else 5
        top_memories = [m for _, m in scored[:limit]]

        # Update access_count
        for m in top_memories:
            try:
                await svc.update(m.id, {
                    "access_count": m.access_count + 1,
                    "last_accessed": __import__("datetime").datetime.utcnow().isoformat(),
                })
            except Exception:
                pass

        results = [
            {
                "title": m.title,
                "content": m.content[:800] if depth == "detailed" else m.content[:300],
                "type": m.type,
                "importance": m.importance,
                "tags": m.tags,
                "source": m.source,
            }
            for m in top_memories
        ]

        return {"result": results, "total_knowledge": len(knowledge), "matched": len(scored)}

    async def _sys_creator_context(self, db, args: dict) -> dict:
        """Return creator/owner profile as context for the agent."""
        from app.mongodb.services import CreatorProfileService
        svc = CreatorProfileService(db)
        profile = await svc.get_profile()
        if not profile:
            return {"result": "", "message": "Creator profile not configured yet."}
        context_str = profile.to_context_string()
        if not context_str:
            return {"result": "", "message": "Creator profile is empty."}
        return {
            "result": context_str,
            "name": profile.name or "",
        }

    async def _sys_fact_save(self, db, agent_id: str, args: dict) -> dict:
        """Save a fact or hypothesis to agent's knowledge base."""
        from app.mongodb.services import AgentFactService
        from app.mongodb.models.agent_fact import MongoAgentFact

        content = str(args.get("content", "")).strip()
        if not content:
            return {"error": "No content provided for fact"}

        fact_type = args.get("type", "fact")
        if fact_type not in ("fact", "hypothesis"):
            fact_type = "fact"

        fact = MongoAgentFact(
            agent_id=agent_id,
            type=fact_type,
            content=content,
            source=args.get("source", "agent"),
            verified=bool(args.get("verified", fact_type == "fact")),
            confidence=float(args.get("confidence", 0.8)),
            tags=args.get("tags", []),
            created_by="agent",
        )
        svc = AgentFactService(db)
        created = await svc.create(fact)
        return {
            "result": {"id": created.id, "type": created.type, "stored": True},
            "message": f"{'Fact' if fact_type == 'fact' else 'Hypothesis'} saved successfully.",
        }

    async def _sys_fact_read(self, db, agent_id: str, args: dict) -> dict:
        """Read facts/hypotheses from agent's knowledge base."""
        from app.mongodb.services import AgentFactService

        svc = AgentFactService(db)
        query = str(args.get("query", "")).strip()
        fact_type = args.get("type")  # None = both
        limit = int(args.get("limit", 20))

        if query:
            items = await svc.search_by_text(agent_id, query, limit=limit)
        else:
            items = await svc.get_by_agent(agent_id, fact_type=fact_type, limit=limit)

        if not items:
            return {"result": [], "message": "No facts/hypotheses found."}

        results = [
            {
                "type": f.type,
                "content": f.content,
                "source": f.source,
                "verified": f.verified,
                "confidence": f.confidence,
                "tags": f.tags,
            }
            for f in items
        ]
        return {"result": results}

    async def _sys_fact_extract(self, db, agent_id: str, args: dict) -> dict:
        """Extract facts from text using LLM and save them."""
        from app.mongodb.services import AgentFactService
        from app.mongodb.models.agent_fact import MongoAgentFact

        text = str(args.get("text", "")).strip()
        if not text:
            return {"error": "No text provided for fact extraction"}

        # Use LLM to extract facts
        prompt = (
            "Extract facts and hypotheses from the following text.\n"
            "Return a JSON array where each item has:\n"
            '  - "type": "fact" (confirmed information) or "hypothesis" (unverified assumption)\n'
            '  - "content": the fact/hypothesis text\n'
            '  - "confidence": float 0.0-1.0\n'
            '  - "tags": list of relevant keywords\n'
            "Return ONLY the JSON array, no other text.\n\n"
            f"Text:\n{text[:3000]}"
        )
        try:
            resp = await self._llm_call(
                [{"role": "user", "content": prompt}],
                system="You extract structured facts from text. Output only valid JSON.",
                temperature=0.1,
            )
            if not resp or not resp.content:
                return {"error": "LLM did not return extracted facts"}

            extracted = self._extract_json(resp.content)
            if not isinstance(extracted, list):
                return {"error": "Failed to parse extracted facts as JSON array"}

            svc = AgentFactService(db)
            saved = []
            for item in extracted:
                if not isinstance(item, dict) or not item.get("content"):
                    continue
                fact_type = item.get("type", "fact")
                if fact_type not in ("fact", "hypothesis"):
                    fact_type = "fact"
                fact = MongoAgentFact(
                    agent_id=agent_id,
                    type=fact_type,
                    content=str(item["content"]).strip(),
                    source=args.get("source", "extraction"),
                    verified=False,
                    confidence=float(item.get("confidence", 0.7)),
                    tags=item.get("tags", []),
                    created_by="agent",
                )
                await svc.create(fact)
                saved.append({"type": fact.type, "content": fact.content})

            return {
                "result": saved,
                "message": f"Extracted and saved {len(saved)} facts/hypotheses.",
            }
        except Exception as e:
            logger.warning(f"fact_extract failed: {e}")
            return {"error": f"Fact extraction failed: {e}"}

    def _build_context(self, classification: Classification, user_input: str) -> dict:
        """Build context dict for arg inference."""
        return {
            "user_input": user_input,
            "detected_urls": classification.detected_urls,
            "detected_project": classification.detected_project,
            "detected_task": classification.detected_task,
        }

    # ═════════════════════════════════════════════════════════════════
    # STAGE 0: CLASSIFY (pure rule-based, no LLM, <1ms)
    # ═════════════════════════════════════════════════════════════════

    def classify(self, user_input: str, history: list[dict]) -> Classification:
        """
        Fast rule-based classification. Determines which stages to run.
        """
        text = user_input.strip()
        text_lower = text.lower()
        word_count = len(text.split())

        is_greeting = bool(GREETING_RU.match(text) or GREETING_EN.match(text))
        urls = URL_PATTERN.findall(text)
        needs_search = bool(SEARCH_KEYWORDS_RU.search(text) or SEARCH_KEYWORDS_EN.search(text))
        needs_study = bool(STUDY_KEYWORDS_RU.search(text) or STUDY_KEYWORDS_EN.search(text))
        needs_recall = bool(RECALL_KEYWORDS_RU.search(text) or RECALL_KEYWORDS_EN.search(text))
        has_code = bool(CODE_BLOCK_PATTERN.search(text))

        project_match = PROJECT_SLUG_PATTERN.search(text)
        detected_project = project_match.group(1) if project_match else None
        task_match = TASK_PATTERN.search(text)
        detected_task = task_match.group(1) if task_match else None

        # Intent
        if is_greeting:
            intent = "greeting"
        elif needs_study:
            intent = "study"
        elif needs_recall:
            intent = "recall"
        elif detected_project or detected_task:
            intent = "project_work"
        elif has_code:
            intent = "code"
        elif needs_search or urls:
            intent = "search"
        elif '?' in text or any(q in text_lower for q in (
            'как ', 'что ', 'где ', 'когда ', 'почему ', 'зачем ', 'сколько ',
            'what ', 'how ', 'where ', 'when ', 'why ', 'which ',
        )):
            intent = "question"
        else:
            intent = "task"

        # Complexity
        if is_greeting:
            complexity = "simple"
        elif word_count <= 8 and intent == "question":
            complexity = "simple"
        elif word_count > 50 or (detected_project and detected_task):
            complexity = "complex"
        elif intent in ("project_work", "code", "study") or urls or needs_search:
            complexity = "medium"
        elif word_count > 20:
            complexity = "medium"
        else:
            complexity = "simple"

        # Skip logic
        has_skills = bool(self.ctx.skills)
        skip_to_synthesize = is_greeting and not has_skills
        skip_understand = complexity == "simple" and not needs_search
        skip_plan = (
            is_greeting
            or (complexity == "simple" and not needs_search and not urls)
            or not has_skills
        )

        return Classification(
            intent=intent,
            complexity=complexity,
            is_greeting=is_greeting,
            skip_to_synthesize=skip_to_synthesize,
            skip_understand=skip_understand,
            skip_plan=skip_plan,
            detected_urls=urls[:5],
            needs_web_search=needs_search,
            has_code_blocks=has_code,
            detected_project=detected_project,
            detected_task=detected_task,
        )

    # ═════════════════════════════════════════════════════════════════
    # STAGE 1: UNDERSTAND (focused LLM call, medium/complex only)
    # ═════════════════════════════════════════════════════════════════

    async def stage_understand(
        self,
        user_input: str,
        history: list[dict],
        classification: Classification,
    ) -> StageResult:
        """
        Analyze user message: refined intent, skill suggestions.
        ONLY called for medium/complex messages.
        """
        start = time.monotonic()

        recent = [m for m in history[-8:] if m.get("role") in ("user", "assistant")]
        hist_lines = []
        for m in recent:
            content = m["content"][:150].replace("\n", " ")
            hist_lines.append(f"  {m['role']}: {content}")
        history_text = "\n".join(hist_lines) if hist_lines else "  (new conversation)"

        skills_list = self._skills_short()

        prompt = f"""Analyze the user's message. Respond with JSON only.

Conversation:
{history_text}

User: {user_input}

Available skills:
{skills_list}

Respond with this JSON (no other text):
{{"intent":"{classification.intent}","complexity":"{classification.complexity}","summary":"one sentence what user wants","needs_skills":["skill1","skill2"],"can_answer_directly":false}}

Rules:
- needs_skills: list ONLY skills from the available list above
- can_answer_directly: true if you can answer without any skills
- Keep summary under 30 words"""

        messages = [
            {"role": "system", "content": "You are an intent analyzer. Output ONLY valid JSON. No explanation."},
            {"role": "user", "content": prompt},
        ]

        raw = ""
        try:
            resp = await self._llm(messages, temperature=0.1)
            raw = (resp.content or "").strip()
            analysis = self._extract_json(raw)
        except Exception as e:
            logger.warning(f"UNDERSTAND stage LLM failed: {e}")
            analysis = None

        if not analysis:
            # Heuristic fallback with smart skill suggestions
            analysis = {
                "intent": classification.intent,
                "complexity": classification.complexity,
                "summary": user_input[:200],
                "needs_skills": [],
                "can_answer_directly": classification.complexity == "simple",
            }
            available = self._skill_names()
            if classification.needs_web_search and "web_fetch" in available:
                analysis["needs_skills"].append("web_fetch")
            if classification.detected_urls:
                skill = "web_scrape" if "web_scrape" in available else "web_fetch"
                if skill in available:
                    analysis["needs_skills"].append(skill)
            if classification.detected_project and "project_context_build" in available:
                analysis["needs_skills"].append("project_context_build")
            if classification.detected_task and classification.detected_project and "task_context_build" in available:
                analysis["needs_skills"].append("task_context_build")

            # Auto-add study/recall skills based on intent
            if classification.intent == "study" and "study_material" in available:
                analysis["needs_skills"].append("study_material")
            if classification.intent == "recall" and "recall_knowledge" in available:
                analysis["needs_skills"].append("recall_knowledge")

            logger.info("UNDERSTAND: used heuristic fallback")

        # Validate skill names
        available = self._skill_names()
        analysis["needs_skills"] = [
            s for s in (analysis.get("needs_skills") or []) if s in available
        ]

        # Auto-add memory_search for non-greeting medium/complex
        if (
            not classification.is_greeting
            and classification.complexity != "simple"
            and "memory_search" in available
            and "memory_search" not in analysis.get("needs_skills", [])
        ):
            analysis["needs_skills"].insert(0, "memory_search")

        # Auto-add study_material for study intent
        if (
            classification.intent == "study"
            and "study_material" in available
            and "study_material" not in analysis.get("needs_skills", [])
        ):
            analysis["needs_skills"].append("study_material")

        # Auto-add recall_knowledge for recall intent
        if (
            classification.intent == "recall"
            and "recall_knowledge" in available
            and "recall_knowledge" not in analysis.get("needs_skills", [])
        ):
            # Use recall_knowledge instead of memory_search
            skills = analysis.get("needs_skills", [])
            if "memory_search" in skills:
                skills.remove("memory_search")
            skills.insert(0, "recall_knowledge")
            analysis["needs_skills"] = skills

        duration_ms = int((time.monotonic() - start) * 1000)

        if self.tracker:
            self.tracker.start_step_timer()
            await self.tracker.step(
                "stage_understand", "Stage 1: Analyze user intent",
                input_data={"user_input": user_input[:300], "classification": classification.intent},
                output_data={
                    "analysis": analysis,
                    "raw_llm_response": raw[:1000],
                    "used_fallback": not bool(self._extract_json(raw)),
                },
                duration_ms=duration_ms,
            )

        return StageResult("understand", analysis, raw, duration_ms=duration_ms)

    # ═════════════════════════════════════════════════════════════════
    # STAGE 2: GATHER (conditional data collection, no LLM)
    # ═════════════════════════════════════════════════════════════════

    async def stage_gather(
        self,
        user_input: str,
        classification: Classification,
        analysis: StageResult | None,
    ) -> StageResult:
        """
        Conditional information gathering based on classify + understand.
        Only collects data — never modifies state.
        """
        start = time.monotonic()
        available = self._skill_names()
        gather_results: dict[str, Any] = {}
        context = self._build_context(classification, user_input)

        # Determine what to gather
        needs_skills: set[str] = set()
        if analysis:
            needs_skills.update(analysis.data.get("needs_skills", []))

        # Rule-based additions
        if classification.detected_urls and not classification.is_greeting:
            skill = "web_scrape" if "web_scrape" in available else "web_fetch"
            if skill in available:
                needs_skills.add(skill)
        if classification.detected_project and "project_context_build" in available:
            needs_skills.add("project_context_build")
        if classification.detected_task and classification.detected_project and "task_context_build" in available:
            needs_skills.add("task_context_build")
        if not classification.is_greeting and classification.complexity != "simple" and "memory_search" in available:
            needs_skills.add("memory_search")
        # Always include creator context when available (not greetings)
        if not classification.is_greeting and "creator_context" in available:
            needs_skills.add("creator_context")

        # Filter to gather-only skills
        needs_skills = needs_skills.intersection(available).intersection(GATHER_SKILLS)

        # Execute gather skills
        for skill_name in sorted(needs_skills):  # sorted for deterministic order
            args = _infer_args(skill_name, {}, context)

            # Validate required args
            skill_schema = None
            for s in self.ctx.skills:
                if s["name"] == skill_name:
                    skill_schema = s.get("input_schema", {})
                    break
            required_params = set((skill_schema or {}).get("required", []))
            if required_params and not all(args.get(p) for p in required_params):
                logger.debug(f"Skipping {skill_name}: missing required params {required_params - set(args.keys())}")
                continue

            try:
                result = await self._exec_skill(skill_name, args)
                if result and "error" not in result:
                    gather_results[skill_name] = result
            except Exception as e:
                logger.debug(f"Gather {skill_name} failed: {e}")

        duration_ms = int((time.monotonic() - start) * 1000)

        if self.tracker:
            self.tracker.start_step_timer()
            await self.tracker.step(
                "stage_gather", "Stage 2: Gather information",
                input_data={
                    "requested_skills": sorted(needs_skills) if needs_skills else [],
                    "detected_urls": classification.detected_urls[:3],
                    "detected_project": classification.detected_project,
                },
                output_data={
                    "gathered": list(gather_results.keys()),
                    "memory_found": "memory_search" in gather_results,
                    "urls_fetched": sum(1 for k in gather_results if k in ("web_fetch", "web_scrape")),
                    "project_context": "project_context_build" in gather_results,
                },
                duration_ms=duration_ms,
            )

        return StageResult("gather", gather_results, duration_ms=duration_ms)

    # ═════════════════════════════════════════════════════════════════
    # STAGE 3: PLAN (focused LLM call, medium/complex only)
    # ═════════════════════════════════════════════════════════════════

    async def stage_plan(
        self,
        user_input: str,
        classification: Classification,
        analysis: StageResult | None,
        gather: StageResult,
    ) -> StageResult:
        """
        Create an execution plan with skill assignments and atomic steps.
        Only runs for medium/complex tasks.
        """
        start = time.monotonic()

        intent = analysis.data.get("intent", classification.intent) if analysis else classification.intent
        complexity = analysis.data.get("complexity", classification.complexity) if analysis else classification.complexity
        summary = analysis.data.get("summary", user_input[:200]) if analysis else user_input[:200]

        # Short-circuit for simple/direct
        if classification.is_greeting or (
            complexity == "simple" and (not analysis or analysis.data.get("can_answer_directly"))
        ):
            plan = {
                "approach": "direct_response",
                "steps": [{"id": 1, "action": "Respond directly", "skill": None, "args": {}}],
                "missing_skills": [],
            }
            duration_ms = int((time.monotonic() - start) * 1000)
            if self.tracker:
                self.tracker.start_step_timer()
                await self.tracker.step(
                    "stage_plan", "Stage 3: Plan (skipped — simple)",
                    output_data={"plan": plan, "short_circuit": True},
                    duration_ms=duration_ms,
                )
            return StageResult("plan", plan, "[simple]", duration_ms=duration_ms)

        # Full planning
        skills_catalog = self._skills_catalog()

        gather_ctx = []
        for skill_name in gather.data:
            gather_ctx.append(f"Already collected: {skill_name}")
        gather_text = "\n".join(gather_ctx) if gather_ctx else "No data gathered yet."

        prompt = f"""Create a step-by-step execution plan for this request.

Request: {user_input}
Intent: {intent}, Complexity: {complexity}
Summary: {summary}
{gather_text}

Available skills (with parameters):
{skills_catalog}

RULES:
1. Break into small atomic steps (1 skill per step, or reasoning step with skill=null)
2. Each step with a skill MUST include correct "args" matching the skill parameters
3. ORDER: gather info first → process → generate/act → verify
4. Skills marked [info-gathering] safe to auto-run; [action] skills modify state
5. If info is already gathered — don't re-gather
6. For memory_search: args={{"query": "relevant search text"}}
7. For project skills: args MUST include "project_slug"

JSON only:
{{"approach":"brief plan description","steps":[{{"id":1,"action":"description","skill":"skill_name_or_null","args":{{"param":"value"}}}}],"missing_skills":[{{"name":"skill","description":"what it would do"}}]}}"""

        messages = [
            {"role": "system", "content": "You are a task planner. Decompose tasks into steps with correct skill args. JSON ONLY."},
            {"role": "user", "content": prompt},
        ]

        raw = ""
        try:
            resp = await self._llm(messages, temperature=0.2)
            raw = (resp.content or "").strip()
            plan = self._extract_json(raw)
        except Exception as e:
            logger.warning(f"PLAN stage LLM failed: {e}")
            plan = None

        if not plan or "steps" not in plan:
            # Fallback from analysis suggestions
            suggested = (analysis.data.get("needs_skills", []) if analysis else [])
            steps = []
            context = self._build_context(classification, user_input)
            for i, skill in enumerate(suggested, 1):
                if skill in GATHER_SKILLS:
                    continue  # Already gathered
                args = _infer_args(skill, {}, context)
                steps.append({"id": i, "action": f"Use {skill}", "skill": skill, "args": args})
            steps.append({"id": len(steps) + 1, "action": "Generate response", "skill": None, "args": {}})
            plan = {"approach": "fallback_plan", "steps": steps, "missing_skills": []}
            logger.info("PLAN: used fallback plan (LLM didn't return valid JSON)")

        # Normalize & validate
        available = self._skill_names()
        for step in plan.get("steps", []):
            step.setdefault("id", 0)
            step.setdefault("action", "")
            step.setdefault("skill", None)
            step.setdefault("args", {})

            if step["skill"] in (None, "null", "", "none", "None"):
                step["skill"] = None
            if step["skill"] and step["skill"] not in available:
                missing = plan.setdefault("missing_skills", [])
                if not any((ms.get("name") if isinstance(ms, dict) else ms) == step["skill"] for ms in missing):
                    missing.append({"name": step["skill"], "description": f"Required for: {step['action']}"})
                step["skill"] = None
            if step["skill"] and step["skill"] in GATHER_SKILLS and step["skill"] in gather.data:
                step["_already_gathered"] = True

        duration_ms = int((time.monotonic() - start) * 1000)

        if self.tracker:
            self.tracker.start_step_timer()
            await self.tracker.step(
                "stage_plan", "Stage 3: Create execution plan",
                input_data={"intent": intent, "complexity": complexity},
                output_data={
                    "plan": plan,
                    "raw_llm_response": raw[:2000],
                    "steps_count": len(plan.get("steps", [])),
                    "skills_in_plan": [s["skill"] for s in plan.get("steps", []) if s.get("skill")],
                    "missing_skills": plan.get("missing_skills", []),
                },
                duration_ms=duration_ms,
            )

        return StageResult("plan", plan, raw, duration_ms=duration_ms)

    # ═════════════════════════════════════════════════════════════════
    # STAGE 4: EXECUTE (skill calls with smart arg inference)
    # ═════════════════════════════════════════════════════════════════

    async def stage_execute(
        self,
        user_input: str,
        classification: Classification,
        plan: StageResult,
        gather: StageResult,
    ) -> StageResult:
        """
        Execute plan steps with smart arg inference.
        Gather results carried through, only action/remaining skills run here.
        """
        start = time.monotonic()

        steps = plan.data.get("steps", [])
        approach = plan.data.get("approach", "")
        step_results: dict[str, dict] = {}
        context = self._build_context(classification, user_input)

        # Carry over gather results
        for skill_name, result in gather.data.items():
            step_results[f"gather_{skill_name}"] = {
                "type": "gather",
                "skill": skill_name,
                "result": result,
                "success": True,
            }

        # Direct response — skip
        if approach == "direct_response":
            duration_ms = int((time.monotonic() - start) * 1000)
            if self.tracker:
                self.tracker.start_step_timer()
                await self.tracker.step(
                    "stage_execute", "Stage 4: Execute (skipped — direct response)",
                    output_data={"skipped": True, "gather_count": len(gather.data)},
                    duration_ms=duration_ms,
                )
            return StageResult("execute", {"step_results": step_results, "skipped": True},
                               duration_ms=duration_ms)

        for step in steps:
            step_id = str(step.get("id", 0))
            skill_name = step.get("skill")
            raw_args = step.get("args", {})
            action = step.get("action", "")
            step_start = time.monotonic()

            if not skill_name:
                step_results[step_id] = {"type": "reasoning", "action": action}
                continue

            if step.get("_already_gathered"):
                step_results[step_id] = {
                    "type": "already_gathered",
                    "skill": skill_name,
                    "note": "Data collected in GATHER stage",
                }
                continue

            # Block dangerous action skills (require user confirmation)
            if skill_name in DANGEROUS_ACTION_SKILLS:
                logger.info(f"EXECUTE: blocking dangerous skill {skill_name} — needs confirmation")
                step_results[step_id] = {
                    "type": "blocked",
                    "skill": skill_name,
                    "reason": "Dangerous action — requires user confirmation",
                    "args": raw_args,
                }
                continue

            # Smart arg inference
            args = _infer_args(skill_name, raw_args, context)

            # Validate required args
            skip_step = False
            for s in self.ctx.skills:
                if s["name"] == skill_name:
                    required = set(s.get("input_schema", {}).get("required", []))
                    missing = required - set(k for k, v in args.items() if v)
                    if missing:
                        logger.warning(f"EXECUTE: skipping {skill_name} — missing: {missing}")
                        step_results[step_id] = {
                            "type": "skipped",
                            "skill": skill_name,
                            "reason": f"Missing required args: {missing}",
                            "args": args,
                        }
                        skip_step = True
                    break
            if skip_step:
                continue

            result = await self._exec_skill(skill_name, args)
            step_dur = int((time.monotonic() - step_start) * 1000)

            step_results[step_id] = {
                "type": "skill",
                "skill": skill_name,
                "args": args,
                "result": result,
                "success": "error" not in result,
            }

            if self.tracker:
                self.tracker.start_step_timer()
                await self.tracker.step(
                    "execute_step", f"Step {step_id}: {action[:80]}",
                    input_data={"step_id": step_id, "skill": skill_name, "args": args},
                    output_data=step_results[step_id],
                    duration_ms=step_dur,
                )

        duration_ms = int((time.monotonic() - start) * 1000)

        skill_steps = [r for r in step_results.values() if r.get("type") == "skill"]
        gather_steps = [r for r in step_results.values() if r.get("type") == "gather"]
        if self.tracker:
            self.tracker.start_step_timer()
            await self.tracker.step(
                "stage_execute", "Stage 4: Execution summary",
                output_data={
                    "total_plan_steps": len(steps),
                    "gathered_skills": [r["skill"] for r in gather_steps],
                    "executed_skills": [r["skill"] for r in skill_steps],
                    "successes": sum(1 for r in skill_steps if r.get("success")),
                    "failures": sum(1 for r in skill_steps if not r.get("success")),
                },
                duration_ms=duration_ms,
            )

        return StageResult("execute", {"step_results": step_results}, duration_ms=duration_ms)

    # ═════════════════════════════════════════════════════════════════
    # STAGE 5: SYNTHESIZE (full LLM call with all gathered context)
    # ═════════════════════════════════════════════════════════════════

    async def stage_synthesize(
        self,
        user_input: str,
        system_prompt: str,
        history: list[dict],
        classification: Classification,
        analysis: StageResult | None,
        plan: StageResult,
        execution: StageResult,
    ) -> StageResult:
        """
        Final LLM call: agent identity + all data → coherent response.
        """
        start = time.monotonic()

        # Build gathered context sections
        gathered_sections = []
        step_results = execution.data.get("step_results", {})

        # Process all results
        for key, result in step_results.items():
            if result.get("type") == "gather":
                skill = result.get("skill", "")
                data = result.get("result", {})
                if skill == "memory_search":
                    mem_data = data.get("result", data)
                    if mem_data and mem_data != [] and mem_data != {}:
                        mem_text = json.dumps(mem_data, ensure_ascii=False, default=str)[:4000]
                        gathered_sections.append(f"**Relevant memories:**\n{mem_text}")
                elif skill in ("web_fetch", "web_scrape"):
                    web_text = json.dumps(data, ensure_ascii=False, default=str)[:3000]
                    gathered_sections.append(f"**Web content ({skill}):**\n{web_text}")
                elif skill == "project_context_build":
                    ctx_text = json.dumps(data, ensure_ascii=False, default=str)[:5000]
                    gathered_sections.append(f"**Project context:**\n{ctx_text}")
                elif skill == "task_context_build":
                    ctx_text = json.dumps(data, ensure_ascii=False, default=str)[:4000]
                    gathered_sections.append(f"**Task context:**\n{ctx_text}")
                elif skill == "creator_context":
                    creator_text = data.get("result", "")
                    if creator_text:
                        gathered_sections.insert(0, f"**About your creator/owner (the person you work for):**\n{creator_text}")
                else:
                    ctx_text = json.dumps(data, ensure_ascii=False, default=str)[:2000]
                    gathered_sections.append(f"**{skill} result:**\n{ctx_text}")

            elif result.get("type") == "skill":
                skill = result.get("skill", "")
                data = result.get("result", {})
                if data:
                    skill_text = json.dumps(data, ensure_ascii=False, default=str)[:3000]
                    gathered_sections.append(f"**Skill `{skill}` result:**\n{skill_text}")

        # Missing skills note
        missing = plan.data.get("missing_skills", [])
        if missing:
            missing_lines = [
                f"- **{ms.get('name', '?') if isinstance(ms, dict) else ms}**"
                + (f": {ms.get('description', '')}" if isinstance(ms, dict) else "")
                for ms in missing
            ]
            gathered_sections.append(
                "**Note — these capabilities are not available:**\n" + "\n".join(missing_lines)
            )

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        if gathered_sections:
            context_msg = (
                "## Gathered Context (IMPORTANT — USE THIS DATA)\n\n"
                "The following data was gathered by your skills BEFORE this message. "
                "This data is REAL and available to you. "
                "DO NOT say you cannot access the web or memory — you already did. "
                "Base your response on this data:\n\n"
                + "\n\n".join(gathered_sections)
            )
            messages.append({"role": "system", "content": context_msg})

        # Plan note for non-trivial tasks
        plan_steps = plan.data.get("steps", [])
        if plan_steps and plan.data.get("approach") != "direct_response":
            plan_text = "\n".join(
                f"  {s.get('id', '?')}. {s.get('action', '')}"
                + (" [done]" if step_results.get(s.get('id', 0), {}).get("success") else "")
                for s in plan_steps
            )
            messages.append({"role": "system", "content": (
                f"## Execution Plan\n{plan_text}\n\n"
                "Follow this plan structure. Present results clearly."
            )})

        # Action execution results note
        executed_actions = []
        blocked_actions = []
        skipped_actions = []
        for key, result in step_results.items():
            if result.get("type") == "skill" and result.get("skill") in ACTION_SKILLS:
                if result.get("success"):
                    executed_actions.append(result)
                else:
                    skipped_actions.append(result)
            elif result.get("type") == "blocked":
                blocked_actions.append(result)
            elif result.get("type") == "skipped" and result.get("skill") in ACTION_SKILLS:
                skipped_actions.append(result)

        if executed_actions:
            action_lines = []
            for ea in executed_actions:
                skill = ea.get("skill", "?")
                res = ea.get("result", {})
                action_lines.append(f"- **{skill}**: executed successfully — {json.dumps(res, ensure_ascii=False, default=str)[:500]}")
            messages.append({"role": "system", "content": (
                "## Actions Completed\n"
                "These actions were executed successfully:\n"
                + "\n".join(action_lines) + "\n\n"
                "Report the results to the user. Confirm what was done."
            )})
        if blocked_actions:
            block_lines = []
            for ba in blocked_actions:
                skill = ba.get("skill", "?")
                reason = ba.get("reason", "")
                block_lines.append(f"- **{skill}**: {reason}")
            messages.append({"role": "system", "content": (
                "## Blocked Actions\n"
                "These actions were NOT executed for safety:\n"
                + "\n".join(block_lines) + "\n\n"
                "Inform the user that these actions need explicit confirmation."
            )})
        if skipped_actions and not executed_actions:
            skip_lines = []
            for sa in skipped_actions:
                skill = sa.get("skill", "?")
                reason = sa.get("reason", "")
                skip_lines.append(f"- **{skill}**: {reason}")
            messages.append({"role": "system", "content": (
                "## Actions Skipped\n"
                "These actions could not be executed:\n"
                + "\n".join(skip_lines) + "\n\n"
                "Explain what happened and what the user can do."
            )})

        messages.extend(history)

        # For gathered context: inject as an assistant "I found this" + user follow-up
        # This works much better with small models than system-only context
        if gathered_sections:
            gathered_text = "\n\n".join(gathered_sections)
            messages.append({"role": "user", "content": user_input})
            messages.append({"role": "assistant", "content": (
                "Я выполнил поиск и получил следующие данные:\n\n"
                + gathered_text
                + "\n\nДавай обработаю эту информацию для тебя."
            )})
            messages.append({"role": "user", "content": (
                "Отлично, теперь на основе этих данных дай мне полный ответ на мой вопрос: "
                + user_input
            )})
        else:
            messages.append({"role": "user", "content": user_input})

        timed_out = False
        try:
            resp = await asyncio.wait_for(
                self._llm(messages),
                timeout=SYNTHESIZE_TIMEOUT_SECONDS,
            )
            content = (resp.content or "").strip()
        except asyncio.TimeoutError:
            timed_out = True
            logger.error(
                f"SYNTHESIZE stage timed out after {SYNTHESIZE_TIMEOUT_SECONDS}s"
            )
            # Build a partial response from gathered data so user gets something
            partial_parts = []
            for section in gathered_sections:
                partial_parts.append(section)
            if partial_parts:
                content = (
                    "⚠️ **Response generation timed out** "
                    f"(>{SYNTHESIZE_TIMEOUT_SECONDS}s). "
                    "Here is the data I gathered:\n\n"
                    + "\n\n".join(partial_parts)
                )
            else:
                content = (
                    "⚠️ **Response generation timed out** "
                    f"(>{SYNTHESIZE_TIMEOUT_SECONDS}s). "
                    "Please try again or simplify your request."
                )
        except Exception as e:
            logger.error(f"SYNTHESIZE stage LLM failed: {e}")
            content = f"Error generating response: {e}"

        duration_ms = int((time.monotonic() - start) * 1000)

        if self.tracker:
            self.tracker.start_step_timer()
            await self.tracker.step(
                "stage_synthesize", "Stage 5: Synthesize response",
                input_data={
                    "gathered_sections_count": len(gathered_sections),
                    "messages_count": len(messages),
                    "plan_steps": len(plan_steps),
                },
                output_data={
                    "response_length": len(content),
                    "response": content,
                    "timed_out": timed_out,
                },
                status="timeout" if timed_out else "completed",
                duration_ms=duration_ms,
            )

        return StageResult("synthesize", {"response": content, "timed_out": timed_out}, content,
                           tokens_used=self._total_tokens, duration_ms=duration_ms)

    # ═════════════════════════════════════════════════════════════════
    # FULL PIPELINE
    # ═════════════════════════════════════════════════════════════════

    async def run(
        self,
        user_input: str,
        history: list[dict],
        system_prompt: str,
        model_id: str | None = None,
    ) -> dict:
        """
        Run the full multi-stage pipeline.

        Flow (conditional):
          CLASSIFY → [UNDERSTAND] → GATHER → [PLAN] → [EXECUTE] → SYNTHESIZE

        Stages in [] are skipped for simple messages.
        """
        pipeline_start = time.monotonic()

        await self._ensure_model(model_id)

        logger.info(
            f"StagedPipeline: starting for '{user_input[:80]}...' "
            f"model={self._model_name}"
        )

        # Stage 0: CLASSIFY
        classification = self.classify(user_input, history)
        logger.info(
            f"CLASSIFY: intent={classification.intent} complexity={classification.complexity} "
            f"skip_understand={classification.skip_understand} skip_plan={classification.skip_plan}"
        )

        if self.tracker:
            self.tracker.start_step_timer()
            await self.tracker.step(
                "stage_classify", "Stage 0: Fast classification",
                input_data={"user_input": user_input[:300]},
                output_data={
                    "intent": classification.intent,
                    "complexity": classification.complexity,
                    "is_greeting": classification.is_greeting,
                    "skip_understand": classification.skip_understand,
                    "skip_plan": classification.skip_plan,
                    "detected_urls": classification.detected_urls[:3],
                    "detected_project": classification.detected_project,
                    "detected_task": classification.detected_task,
                    "needs_web_search": classification.needs_web_search,
                },
                duration_ms=0,
            )

        # Stage 1: UNDERSTAND (LLM, skip for simple)
        analysis: StageResult | None = None
        if not classification.skip_understand:
            analysis = await self.stage_understand(user_input, history, classification)
        else:
            logger.info("UNDERSTAND: skipped (simple message)")

        # Stage 2: GATHER (conditional info collection)
        gather = await self.stage_gather(user_input, classification, analysis)

        # Stage 3: PLAN (LLM, skip for simple/greeting)
        if not classification.skip_plan:
            plan = await self.stage_plan(user_input, classification, analysis, gather)
        else:
            plan = StageResult("plan", {
                "approach": "direct_response",
                "steps": [{"id": 1, "action": "Respond directly", "skill": None, "args": {}}],
                "missing_skills": [],
            }, "[skipped]")
            logger.info("PLAN: skipped (simple/no skills)")

        # Stage 4: EXECUTE
        execution = await self.stage_execute(user_input, classification, plan, gather)

        # Stage 5: SYNTHESIZE
        synthesis = await self.stage_synthesize(
            user_input, system_prompt, history,
            classification, analysis, plan, execution,
        )

        total_duration = int((time.monotonic() - pipeline_start) * 1000)

        stages_run = ["classify"]
        if analysis:
            stages_run.append("understand")
        stages_run.append("gather")
        if not classification.skip_plan:
            stages_run.append("plan")
        stages_run.append("execute")
        stages_run.append("synthesize")

        logger.info(
            f"StagedPipeline: done in {total_duration}ms — "
            f"{self._llm_calls} LLM calls, {self._total_tokens} tokens, "
            f"stages: {'→'.join(stages_run)}"
        )

        return {
            "content": synthesis.data.get("response", ""),
            "raw_content": synthesis.raw_llm_response,
            "analysis": analysis.data if analysis else {
                "intent": classification.intent,
                "complexity": classification.complexity,
            },
            "plan": plan.data,
            "execution": execution.data,
            "classification": {
                "intent": classification.intent,
                "complexity": classification.complexity,
                "is_greeting": classification.is_greeting,
                "detected_project": classification.detected_project,
                "detected_task": classification.detected_task,
            },
            "stages_run": stages_run,
            "model_name": self._model_name,
            "provider": self._provider,
            "total_tokens": self._total_tokens,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "llm_calls_count": self._llm_calls,
            "duration_ms": total_duration,
        }
