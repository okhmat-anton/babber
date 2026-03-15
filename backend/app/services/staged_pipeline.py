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


# ── ScrapeCreators platform detection ────────────────────────────────

def _detect_video_platform(url: str) -> tuple[str | None, str | None]:
    """Detect platform from video URL and return (platform_name, api_path).
    Returns (None, None) if the platform is not supported.
    """
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return ("youtube", "/v1/youtube/video/transcript")
    elif "tiktok.com" in url_lower:
        return ("tiktok", "/v1/tiktok/video/transcript")
    elif "instagram.com" in url_lower:
        return ("instagram", "/v2/instagram/media/transcript")
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return ("facebook", "/v1/facebook/post/transcript")
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return ("twitter", "/v1/twitter/tweet/transcript")
    elif "threads.net" in url_lower:
        return ("threads", "/v1/threads/post")
    elif "linkedin.com" in url_lower:
        return ("linkedin", "/v1/linkedin/post")
    elif "reddit.com" in url_lower:
        return ("reddit", "/v1/reddit/post/comments")
    elif "twitch.tv" in url_lower or "clips.twitch.tv" in url_lower:
        return ("twitch", "/v1/twitch/clip")
    elif "kick.com" in url_lower:
        return ("kick", "/v1/kick/clip")
    return (None, None)


def _parse_transcript_response(
    platform: str, data: dict
) -> tuple[str | None, str | None, list | None, str | None]:
    """Parse ScrapeCreators API response and extract transcript text.
    Returns (transcript_text, video_id, segments, language).
    """
    transcript_text = None
    video_id = None
    segments = None
    language = None

    if platform == "youtube":
        # YouTube returns {videoId, transcript: [{text, startMs, endMs, startTimeText}], transcript_only_text, language}
        video_id = data.get("videoId")
        transcript_text = data.get("transcript_only_text")
        language = data.get("language")
        raw_segments = data.get("transcript")
        if isinstance(raw_segments, list):
            segments = raw_segments
        # Fallback: build text from segments
        if not transcript_text and segments:
            transcript_text = " ".join(s.get("text", "") for s in segments if isinstance(s, dict))

    elif platform == "tiktok":
        # TikTok returns {id, url, transcript: "WEBVTT string"}
        video_id = data.get("id")
        raw = data.get("transcript")
        if isinstance(raw, str) and raw.strip():
            # Extract plain text from WEBVTT format
            lines = raw.split("\n")
            text_lines = []
            for line in lines:
                line = line.strip()
                if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                    continue
                text_lines.append(line)
            transcript_text = " ".join(text_lines) if text_lines else None

    elif platform == "instagram":
        # Instagram returns {success, transcripts: [{id, shortcode, text}]}
        transcripts = data.get("transcripts", [])
        if isinstance(transcripts, list) and transcripts:
            parts = []
            for t in transcripts:
                if isinstance(t, dict) and t.get("text"):
                    parts.append(t["text"])
                    if not video_id:
                        video_id = t.get("id") or t.get("shortcode")
            transcript_text = " ".join(parts) if parts else None

    elif platform == "facebook":
        # Facebook returns transcript similarly to TikTok/YouTube
        video_id = data.get("id")
        transcript_text = data.get("transcript_only_text") or data.get("transcript")
        if isinstance(transcript_text, list):
            transcript_text = " ".join(
                s.get("text", "") for s in transcript_text if isinstance(s, dict)
            )
        language = data.get("language")

    elif platform == "twitter":
        # Twitter returns transcript similarly
        video_id = data.get("id")
        transcript_text = data.get("transcript_only_text") or data.get("transcript")
        if isinstance(transcript_text, list):
            transcript_text = " ".join(
                s.get("text", "") for s in transcript_text if isinstance(s, dict)
            )
        language = data.get("language")

    elif platform == "threads":
        # Threads returns {success, post: {id, user, caption: {text}, transcription_data, ...}, comments, relatedPosts}
        post = data.get("post") or {}
        video_id = post.get("pk") or post.get("id")
        # Try transcription_data first (for actual video transcripts)
        transcription = post.get("transcription_data")
        if transcription and isinstance(transcription, dict):
            transcript_text = transcription.get("text") or transcription.get("transcript")
        # Fallback to caption text
        if not transcript_text:
            caption = post.get("caption") or {}
            transcript_text = caption.get("text")
        # Also extract text from text_fragments
        if not transcript_text:
            tpa = post.get("text_post_app_info") or {}
            frags = (tpa.get("text_fragments") or {}).get("fragments") or []
            parts = [f.get("plaintext", "") for f in frags if isinstance(f, dict) and f.get("plaintext")]
            if parts:
                transcript_text = " ".join(parts)
        user = post.get("user") or {}
        if user.get("username"):
            video_id = video_id or user["username"]

    elif platform == "linkedin":
        # LinkedIn returns {success, url, name, headline, description, author: {name}, comments, ...}
        video_id = data.get("url")
        title = data.get("name") or ""
        description = data.get("description") or ""
        headline = data.get("headline") or ""
        parts = [p for p in [title, headline, description] if p]
        transcript_text = "\n\n".join(parts) if parts else None
        author = data.get("author") or {}
        if author.get("name"):
            video_id = video_id or author["name"]

    elif platform == "reddit":
        # Reddit returns {post: {title, selftext, author, id, is_video, ...}, comments: [...]}
        post = data.get("post") or {}
        video_id = post.get("id")
        title = post.get("title") or ""
        selftext = post.get("selftext") or ""
        parts = [p for p in [title, selftext] if p.strip()]
        transcript_text = "\n\n".join(parts) if parts else None
        # Also include top comments for context
        comments = data.get("comments") or []
        if comments and isinstance(comments, list):
            comment_texts = []
            for c in comments[:10]:  # Top 10 comments
                if isinstance(c, dict):
                    body = c.get("body", "").strip()
                    author = c.get("author", "unknown")
                    if body:
                        comment_texts.append(f"[{author}]: {body}")
            if comment_texts:
                existing = transcript_text or ""
                transcript_text = existing + "\n\n--- Comments ---\n" + "\n".join(comment_texts)

    elif platform == "twitch":
        # Twitch returns complex GraphQL response: [{data: {clip: {title, viewCount, durationSeconds, ...}}}]
        clip_data = None
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    nested = (item.get("data") or {}).get("clip")
                    if nested and isinstance(nested, dict) and nested.get("title"):
                        clip_data = nested
                        break
        elif isinstance(data, dict):
            clip_data = data.get("clip") or (data.get("data") or {}).get("clip")
        if clip_data and isinstance(clip_data, dict):
            video_id = clip_data.get("slug") or clip_data.get("id")
            title = clip_data.get("title") or ""
            broadcaster = (clip_data.get("broadcaster") or {}).get("displayName", "")
            game = (clip_data.get("game") or {}).get("name", "")
            duration = clip_data.get("durationSeconds", "")
            views = clip_data.get("viewCount", "")
            parts = [f"Clip: {title}"]
            if broadcaster:
                parts.append(f"Channel: {broadcaster}")
            if game:
                parts.append(f"Category: {game}")
            if duration:
                parts.append(f"Duration: {duration}s")
            if views:
                parts.append(f"Views: {views}")
            language = clip_data.get("language")
            transcript_text = "\n".join(parts)

    elif platform == "kick":
        # Kick returns {clip: {id, title, clip_url, views, duration, creator, channel, ...}}
        clip_data = data.get("clip") or {}
        video_id = clip_data.get("id")
        title = clip_data.get("title") or ""
        creator = (clip_data.get("creator") or {}).get("username", "")
        channel = (clip_data.get("channel") or {}).get("username", "")
        duration = clip_data.get("duration", "")
        views = clip_data.get("views") or clip_data.get("view_count", "")
        parts = [f"Clip: {title}"]
        if channel:
            parts.append(f"Channel: {channel}")
        if creator:
            parts.append(f"Clipped by: {creator}")
        if duration:
            parts.append(f"Duration: {duration}s")
        if views:
            parts.append(f"Views: {views}")
        category = (clip_data.get("category") or {}).get("name", "")
        if category:
            parts.append(f"Category: {category}")
        transcript_text = "\n".join(parts)

    # Clean up transcript text
    if isinstance(transcript_text, str):
        transcript_text = transcript_text.strip()
        if not transcript_text:
            transcript_text = None

    return (transcript_text, str(video_id) if video_id else None, segments, language)


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
    "event_read",
    "video_watch",
    # New gather skills
    "web_search", "project_search_code", "csv_parse", "pdf_read",
    "yaml_parse", "xml_parse", "regex_extract", "math_calculate",
    "rss_read", "translate", "image_analyze",
    "weather_check",
})

ACTION_SKILLS = frozenset({
    "memory_store", "file_write", "project_file_write", "shell_exec",
    "code_execute", "project_update_task", "project_task_comment",
    "project_run_code", "sound_generate",
    "fact_save", "fact_extract",
    "event_save",
    # New action skills
    "telegram_send", "notification_send", "image_generate",
    "email_send", "schedule_reminder", "git_operations",
    "code_review", "docker_manage", "api_call",
})

# "safe" action skills that can be auto-executed without user confirmation
# These are reversible or low-risk (project files, comments, memory)
SAFE_ACTION_SKILLS = frozenset({
    "memory_store", "project_file_write", "project_update_task",
    "project_task_comment", "code_execute", "sound_generate",
    "fact_save", "fact_extract",
    "event_save",
    # New safe action skills
    "notification_send", "image_generate", "code_review",
    "schedule_reminder",
})

# Dangerous skills require confirmation (never auto-execute)
DANGEROUS_ACTION_SKILLS = frozenset({
    "shell_exec", "file_write",
    # New dangerous skills
    "telegram_send", "email_send", "git_operations",
    "docker_manage", "api_call",
})

# ── Step result resolution ────────────────────────────────────────────

_step_ref_re = re.compile(r'\{\{step(\d+)\.(result|output|text)\}\}', re.IGNORECASE)
_bracket_placeholder_re = re.compile(r'^\[([^\[\]]{5,})\]$')
_unresolvable_template_re = re.compile(r'\{\{[^}]+\}\}')


def _extract_step_text(step_data: dict) -> str:
    """Extract the main text content from a step result dict."""
    result = step_data.get("result", {})
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        inner = result.get("result", "")
        if isinstance(inner, str):
            return inner
        if isinstance(inner, dict):
            # Try common text keys
            for key in ("text", "content", "summary", "output", "humanized"):
                if key in inner and isinstance(inner[key], str):
                    return inner[key]
            return json.dumps(inner, ensure_ascii=False, default=str)[:5000]
        if isinstance(inner, list):
            return json.dumps(inner, ensure_ascii=False, default=str)[:5000]
        return str(inner) if inner else ""
    return str(result) if result else ""


def _find_last_step_text(step_results: dict) -> str:
    """Find text output from the most recent successful skill step."""
    sorted_ids = sorted(
        (k for k in step_results
         if step_results[k].get("success") and step_results[k].get("type") == "skill"),
        key=lambda x: int(x) if x.isdigit() else 0,
        reverse=True,
    )
    for sid in sorted_ids:
        text = _extract_step_text(step_results[sid])
        if text and len(text) > 10:
            return text
    return ""


def _resolve_step_refs(args: dict, step_results: dict) -> dict:
    """
    Resolve {{stepN.result}} templates and bracket placeholders
    from previous step results. Must be called BEFORE _infer_args.
    """
    if not step_results:
        return args

    resolved = dict(args)
    for k, v in list(resolved.items()):
        if not isinstance(v, str) or not v.strip():
            continue

        # 1. Resolve {{stepN.result}} / {{stepN.output}} / {{stepN.text}} references
        def _replace_ref(m: re.Match) -> str:
            step_id = m.group(1)
            if step_id in step_results and step_results[step_id].get("success"):
                text = _extract_step_text(step_results[step_id])
                if text:
                    return text
            return m.group(0)  # Keep original if not found

        new_val = _step_ref_re.sub(_replace_ref, v)
        if new_val != v:
            resolved[k] = new_val
            continue

        # 2. Detect bracket placeholders like [final humanized LinkedIn post]
        stripped = v.strip()
        if _bracket_placeholder_re.match(stripped):
            last_text = _find_last_step_text(step_results)
            if last_text:
                logger.info(f"Resolved bracket placeholder '{stripped}' → {len(last_text)} chars from previous step")
                resolved[k] = last_text

    return resolved


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

    # Clear remaining unresolvable template variables (already resolved by _resolve_step_refs)
    for k, v in list(args.items()):
        if isinstance(v, str) and _unresolvable_template_re.search(v):
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
            # Try 'содержимым "X"' / 'content "X"' patterns (RU + EN)
            content_match = re.search(
                r"(?:содержим(?:ое|ым)\s+|content\s+)['\"](.+?)['\"]",
                user_input, re.I,
            )
            if content_match:
                args["content"] = content_match.group(1)
            else:
                # Try 'с текстом "X"' / 'with text "X"' pattern (RU + EN)
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

    elif skill_name == "event_save":
        if "title" not in args or not args["title"]:
            args["title"] = user_input[:200]

    elif skill_name == "event_read":
        if "query" not in args or not args["query"]:
            args["query"] = user_input
        if "limit" not in args:
            args["limit"] = 20

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
        "event_save", "event_read",
        "video_watch",
        # New system skill handlers
        "web_search", "telegram_send", "notification_send",
        "image_analyze", "git_operations", "project_search_code",
        "image_generate", "translate", "csv_parse", "pdf_read",
        "email_send", "schedule_reminder", "yaml_parse", "xml_parse",
        "regex_extract", "api_call", "math_calculate", "code_review",
        "docker_manage", "rss_read", "weather_check",
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
        elif name == "video_watch":
            return await self._sys_video_watch(db, agent_id, args)
        elif name == "event_save":
            return await self._sys_event_save(db, agent_id, args)
        elif name == "event_read":
            return await self._sys_event_read(db, agent_id, args)
        # New skill handlers
        elif name == "web_search":
            return await self._sys_web_search(args)
        elif name == "telegram_send":
            return await self._sys_telegram_send(db, args)
        elif name == "notification_send":
            return await self._sys_notification_send(db, agent_id, args)
        elif name == "image_analyze":
            return await self._sys_image_analyze(args)
        elif name == "git_operations":
            return await self._sys_git_operations(args)
        elif name == "project_search_code":
            return await self._sys_project_search_code(args)
        elif name == "image_generate":
            return await self._sys_image_generate(db, args)
        elif name == "translate":
            return await self._sys_translate(args)
        elif name == "csv_parse":
            return await self._sys_csv_parse(args)
        elif name == "pdf_read":
            return await self._sys_pdf_read(args)
        elif name == "email_send":
            return await self._sys_email_send(db, args)
        elif name == "schedule_reminder":
            return await self._sys_schedule_reminder(db, agent_id, args)
        elif name == "yaml_parse":
            return await self._sys_yaml_parse(args)
        elif name == "xml_parse":
            return await self._sys_xml_parse(args)
        elif name == "regex_extract":
            return await self._sys_regex_extract(args)
        elif name == "api_call":
            return await self._sys_api_call(args)
        elif name == "math_calculate":
            return await self._sys_math_calculate(args)
        elif name == "code_review":
            return await self._sys_code_review(args)
        elif name == "docker_manage":
            return await self._sys_docker_manage(args)
        elif name == "rss_read":
            return await self._sys_rss_read(args)
        elif name == "weather_check":
            return await self._sys_weather_check(args)
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

    async def _sys_event_save(self, db, agent_id: str, args: dict) -> dict:
        """Save an event to agent's memory timeline."""
        from app.mongodb.services import AgentEventService
        from app.mongodb.models.agent_event import MongoAgentEvent

        title = str(args.get("title", "")).strip()
        if not title:
            return {"error": "No title provided for event"}

        event_type = args.get("event_type", "observation")
        valid_types = {"conversation", "observation", "discovery", "decision", "milestone", "custom"}
        if event_type not in valid_types:
            event_type = "observation"

        importance = args.get("importance", "medium")
        if importance not in {"low", "medium", "high", "critical"}:
            importance = "medium"

        event = MongoAgentEvent(
            agent_id=agent_id,
            event_type=event_type,
            title=title,
            description=str(args.get("description", "")).strip(),
            comment=str(args.get("comment", "")).strip(),
            source=args.get("source", "agent"),
            importance=importance,
            tags=args.get("tags", []),
            created_by="agent",
        )
        svc = AgentEventService(db)
        created = await svc.create(event)
        return {
            "result": {"id": created.id, "event_type": created.event_type, "stored": True},
            "message": f"Event '{title}' saved successfully.",
        }

    async def _sys_event_read(self, db, agent_id: str, args: dict) -> dict:
        """Read events from agent's memory timeline."""
        from app.mongodb.services import AgentEventService

        svc = AgentEventService(db)
        query = str(args.get("query", "")).strip()
        event_type = args.get("event_type")  # None = all
        limit = int(args.get("limit", 20))

        if query:
            items = await svc.search_by_text(agent_id, query, limit=limit)
        else:
            items = await svc.get_by_agent(agent_id, event_type=event_type, limit=limit)

        if not items:
            return {"result": [], "message": "No events found."}

        results = [
            {
                "event_type": e.event_type,
                "title": e.title,
                "description": e.description,
                "comment": e.comment,
                "source": e.source,
                "importance": e.importance,
                "tags": e.tags,
                "event_date": e.event_date.isoformat() if hasattr(e.event_date, "isoformat") else str(e.event_date),
            }
            for e in items
        ]
        return {"result": results}

    async def _sys_video_watch(self, db, agent_id: str, args: dict) -> dict:
        """Fetch video transcript via ScrapeCreators API and cache in watched_videos collection."""
        import httpx
        from app.api.settings import get_setting_value
        from app.mongodb.services import WatchedVideoService
        from app.mongodb.models.watched_video import MongoWatchedVideo

        url = str(args.get("url", "")).strip()
        language = str(args.get("language", "")).strip() or None
        if not url:
            return {"error": "No URL provided"}

        video_svc = WatchedVideoService(db)

        # Check cache first
        existing = await video_svc.get_by_url(url)
        if existing and existing.transcript:
            return {
                "result": {
                    "platform": existing.platform,
                    "video_id": existing.video_id,
                    "transcript": existing.transcript,
                    "language": existing.language,
                    "cached": True,
                },
            }

        # Get API key from system settings
        api_key = await get_setting_value(db, "scrapecreators_api_key")
        if not api_key:
            return {"error": "ScrapeCreators API key not configured. Add it in Settings."}

        # Detect platform and build request
        platform, api_path = _detect_video_platform(url)
        if not platform:
            return {"error": f"Unsupported video URL. Supported platforms: YouTube (incl. Shorts), TikTok, Instagram, Facebook, Twitter/X, Threads, LinkedIn, Reddit, Twitch, Kick."}

        # Call ScrapeCreators API
        base_url = "https://api.scrapecreators.com"
        params = {"url": url}
        if language:
            params["language"] = language

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    f"{base_url}{api_path}",
                    params=params,
                    headers={"x-api-key": api_key},
                )
            if resp.status_code != 200:
                error_detail = resp.text[:500]
                # Save failed attempt
                failed_record = MongoWatchedVideo(
                    url=url,
                    platform=platform,
                    agent_id=agent_id,
                    error=f"HTTP {resp.status_code}: {error_detail}",
                )
                await video_svc.create(failed_record)
                return {"error": f"ScrapeCreators API error ({resp.status_code}): {error_detail}"}

            data = resp.json()
        except Exception as e:
            return {"error": f"ScrapeCreators API request failed: {e}"}

        # Extract transcript based on platform
        transcript_text, video_id, segments, lang = _parse_transcript_response(platform, data)

        if not transcript_text:
            # Save record with no transcript (video might not have captions)
            record = MongoWatchedVideo(
                url=url,
                platform=platform,
                video_id=video_id,
                agent_id=agent_id,
                language=lang or (language if language else None),
                error="No transcript available for this video",
            )
            await video_svc.create(record)
            return {"error": "No transcript available for this video."}

        # Save successful transcript
        record = MongoWatchedVideo(
            url=url,
            platform=platform,
            video_id=video_id,
            transcript=transcript_text,
            transcript_segments=segments,
            language=lang or language,
            agent_id=agent_id,
            metadata={"raw_keys": list(data.keys())},
        )
        await video_svc.create(record)

        return {
            "result": {
                "platform": platform,
                "video_id": video_id,
                "transcript": transcript_text,
                "language": lang or language,
                "cached": False,
            },
        }

    # ── New skill handlers ───────────────────────────────────────────

    async def _sys_web_search(self, args: dict) -> dict:
        """Search the web using DuckDuckGo HTML search."""
        import httpx
        import re as _re
        query = str(args.get("query", "")).strip()
        limit = int(args.get("limit", 10))
        region = args.get("region", "")
        if not query:
            return {"error": "No search query provided"}
        try:
            params = {"q": query, "kl": region} if region else {"q": query}
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Agent/1.0)"},
                )
                html = r.text
            results = []
            # Parse DuckDuckGo HTML results
            blocks = _re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>.*?<a class="result__snippet".*?>(.*?)</a>', html, _re.DOTALL)
            for href, title, snippet in blocks[:limit]:
                title = _re.sub(r'<[^>]+>', '', title).strip()
                snippet = _re.sub(r'<[^>]+>', '', snippet).strip()
                # Fix DDG redirect URLs
                if "uddg=" in href:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    href = parsed.get("uddg", [href])[0]
                results.append({"title": title, "url": href, "snippet": snippet})
            if not results:
                return {"result": [], "message": f"No results found for '{query}'"}
            return {"result": results}
        except Exception as e:
            return {"error": f"Web search failed: {e}"}

    async def _sys_telegram_send(self, db, args: dict) -> dict:
        """Send a message to Telegram via configured messenger."""
        messenger_id = args.get("messenger_id", "")
        chat_id = args.get("chat_id", "")
        text = args.get("text", "")
        if not messenger_id or not chat_id or not text:
            return {"error": "messenger_id, chat_id, and text are required"}
        try:
            from app.services.telegram_service import _running_clients
            client_data = _running_clients.get(messenger_id)
            if not client_data or not client_data.get("client"):
                return {"error": f"Messenger {messenger_id} is not running. Start it first."}
            client = client_data["client"]
            entity = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
            await client.send_message(entity, text, parse_mode="md")
            return {"result": {"sent": True, "chat_id": chat_id}}
        except Exception as e:
            return {"error": f"Telegram send failed: {e}"}

    async def _sys_notification_send(self, db, agent_id: str, args: dict) -> dict:
        """Send a notification to the owner via first available messenger."""
        title = args.get("title", "")
        message = args.get("message", "")
        priority = args.get("priority", "normal")
        if not title or not message:
            return {"error": "title and message are required"}
        priority_emoji = {"low": "ℹ️", "normal": "📌", "high": "⚠️", "urgent": "🚨"}.get(priority, "📌")
        text = f"{priority_emoji} **{title}**\n\n{message}"
        try:
            from app.services.telegram_service import _running_clients
            if _running_clients:
                # Send via first running messenger
                for mid, client_data in _running_clients.items():
                    client = client_data.get("client")
                    config = client_data.get("config", {})
                    trusted = config.get("trusted_users", [])
                    if client and trusted:
                        for user in trusted[:1]:
                            await client.send_message(user, text, parse_mode="md")
                        return {"result": {"sent": True, "channel": "telegram", "messenger_id": mid}}
            # Fallback: log it
            logger.info(f"Notification (no messenger): {title} — {message}")
            return {"result": {"sent": False, "message": "No active messenger. Notification logged.", "title": title}}
        except Exception as e:
            return {"error": f"Notification failed: {e}"}

    async def _sys_image_analyze(self, args: dict) -> dict:
        """Analyze an image using vision-capable LLM."""
        image_url = args.get("image_url", "")
        question = args.get("question", "Describe this image in detail.")
        if not image_url:
            return {"error": "No image_url provided"}
        try:
            messages = [
                {"role": "user", "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]},
            ]
            resp = await self._llm_call(
                messages, system="You are a vision assistant. Analyze the image and respond in detail.",
                temperature=0.3,
            )
            return {"result": resp.content if resp else "Could not analyze the image"}
        except Exception as e:
            return {"error": f"Image analysis failed: {e}"}

    async def _sys_git_operations(self, args: dict) -> dict:
        """Execute git operations on project directories."""
        import asyncio as _asyncio
        from pathlib import Path
        import os

        operation = args.get("operation", "").lower()
        project_slug = args.get("project_slug", "")
        repo_url = args.get("repo_url", "")
        branch = args.get("branch", "")
        message = args.get("message", "Auto-commit by AI agent")
        files = args.get("files", [])

        if not operation:
            return {"error": "No operation specified"}

        base = Path(os.environ.get("PROJECTS_DIR", "./data/projects")).resolve()
        cwd = str(base / project_slug / "code") if project_slug else str(base)

        commands = {
            "clone": f"git clone {repo_url} {cwd}" if repo_url else None,
            "status": "git status --porcelain",
            "diff": "git diff",
            "log": "git log --oneline -20",
            "branch": f"git checkout -b {branch}" if branch else "git branch -a",
            "checkout": f"git checkout {branch}" if branch else None,
            "pull": "git pull",
            "push": "git push",
            "commit": None,  # handled specially
        }

        if operation == "commit":
            add_cmd = "git add " + " ".join(files) if files else "git add -A"
            cmd = f"{add_cmd} && git commit -m \"{message}\""
        elif operation in commands:
            cmd = commands[operation]
        else:
            return {"error": f"Unknown git operation: {operation}"}

        if not cmd:
            return {"error": f"Missing required parameters for '{operation}'"}

        try:
            use_cwd = cwd if operation != "clone" else str(base)
            if not Path(use_cwd).exists():
                Path(use_cwd).mkdir(parents=True, exist_ok=True)
            proc = await _asyncio.create_subprocess_shell(
                cmd, stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE, cwd=use_cwd
            )
            stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=60)
            return {
                "result": {
                    "operation": operation,
                    "stdout": stdout.decode()[:5000],
                    "stderr": stderr.decode()[:2000],
                    "returncode": proc.returncode,
                    "success": proc.returncode == 0,
                }
            }
        except _asyncio.TimeoutError:
            return {"error": f"Git operation '{operation}' timed out (60s)"}
        except Exception as e:
            return {"error": f"Git operation failed: {e}"}

    async def _sys_project_search_code(self, args: dict) -> dict:
        """Search through project files by text or regex."""
        import re as _re
        from pathlib import Path
        import os

        project_slug = args.get("project_slug", "")
        query = args.get("query", "")
        is_regex = bool(args.get("is_regex", False))
        file_pattern = args.get("file_pattern", "")
        max_results = int(args.get("max_results", 50))

        if not project_slug or not query:
            return {"error": "project_slug and query are required"}

        base = Path(os.environ.get("PROJECTS_DIR", "./data/projects")).resolve()
        code_dir = (base / project_slug / "code").resolve()
        if not code_dir.exists():
            return {"error": f"Project code directory not found: {project_slug}"}

        try:
            pattern = _re.compile(query, _re.IGNORECASE) if is_regex else None
        except _re.error as e:
            return {"error": f"Invalid regex: {e}"}

        matches = []
        glob_pat = file_pattern if file_pattern else "*"
        for fpath in sorted(code_dir.rglob(glob_pat)):
            if not fpath.is_file():
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                found = pattern.search(line) if pattern else (query.lower() in line.lower())
                if found:
                    matches.append({
                        "file": str(fpath.relative_to(code_dir)),
                        "line": i,
                        "text": line.strip()[:200],
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        return {"result": matches, "total": len(matches)}

    async def _sys_image_generate(self, db, args: dict) -> dict:
        """Generate an image using OpenAI DALL-E API."""
        import httpx
        from app.api.settings import get_setting_value

        prompt = args.get("prompt", "")
        size = args.get("size", "1024x1024")
        quality = args.get("quality", "standard")
        style = args.get("style", "vivid")
        if not prompt:
            return {"error": "No prompt provided"}

        api_key = await get_setting_value(db, "openai_api_key")
        if not api_key:
            return {"error": "OpenAI API key not configured. Add it in Settings."}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "dall-e-3", "prompt": prompt, "n": 1, "size": size, "quality": quality, "style": style},
                )
            if resp.status_code != 200:
                return {"error": f"DALL-E API error ({resp.status_code}): {resp.text[:500]}"}
            data = resp.json()
            image_url = data.get("data", [{}])[0].get("url", "")
            revised_prompt = data.get("data", [{}])[0].get("revised_prompt", "")
            return {"result": {"image_url": image_url, "revised_prompt": revised_prompt}}
        except Exception as e:
            return {"error": f"Image generation failed: {e}"}

    async def _sys_translate(self, args: dict) -> dict:
        """Translate text using LLM."""
        text = args.get("text", "")
        to_language = args.get("to_language", "English")
        from_language = args.get("from_language", "auto-detect")
        if not text:
            return {"error": "No text provided"}
        try:
            from_part = f"from {from_language} " if from_language and from_language != "auto-detect" else ""
            resp = await self._llm_call(
                [{"role": "user", "content": f"Translate the following text {from_part}to {to_language}. Output ONLY the translation, nothing else:\n\n{text[:5000]}"}],
                system="You are a professional translator. Provide accurate, natural translations. Output only the translated text.",
                temperature=0.1,
            )
            return {"result": {"translation": resp.content if resp else text, "to_language": to_language}}
        except Exception as e:
            return {"error": f"Translation failed: {e}"}

    async def _sys_csv_parse(self, args: dict) -> dict:
        """Parse and analyze CSV data."""
        import csv
        import io

        text = args.get("text", "")
        file_path = args.get("file_path", "")
        operation = args.get("operation", "parse")
        columns = args.get("columns")
        limit = int(args.get("limit", 100))

        if file_path and not text:
            try:
                from pathlib import Path
                text = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return {"error": f"Failed to read CSV file: {e}"}
        if not text:
            return {"error": "No CSV data provided (text or file_path)"}

        try:
            reader = csv.DictReader(io.StringIO(text))
            rows = []
            for i, row in enumerate(reader):
                if i >= limit:
                    break
                if columns:
                    row = {k: v for k, v in row.items() if k in columns}
                rows.append(row)

            if operation == "stats":
                stats = {"rows": len(rows), "columns": list(rows[0].keys()) if rows else []}
                # Try numeric stats
                for col in stats["columns"]:
                    vals = []
                    for r in rows:
                        try:
                            vals.append(float(r[col]))
                        except (ValueError, TypeError):
                            pass
                    if vals:
                        stats[f"{col}_min"] = min(vals)
                        stats[f"{col}_max"] = max(vals)
                        stats[f"{col}_avg"] = sum(vals) / len(vals)
                return {"result": stats}

            return {"result": {"rows": rows, "total": len(rows), "columns": list(rows[0].keys()) if rows else []}}
        except Exception as e:
            return {"error": f"CSV parsing failed: {e}"}

    async def _sys_pdf_read(self, args: dict) -> dict:
        """Extract text from PDF files."""
        file_path = args.get("file_path", "")
        url = args.get("url", "")
        max_chars = int(args.get("max_chars", 10000))

        pdf_data = None
        if url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                    r = await client.get(url)
                    if r.status_code != 200:
                        return {"error": f"Failed to download PDF: HTTP {r.status_code}"}
                    pdf_data = r.content
            except Exception as e:
                return {"error": f"Failed to download PDF: {e}"}
        elif file_path:
            try:
                from pathlib import Path
                pdf_data = Path(file_path).read_bytes()
            except Exception as e:
                return {"error": f"Failed to read PDF file: {e}"}
        else:
            return {"error": "No file_path or url provided"}

        # Try PyMuPDF first, then fall back to simple extraction
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            text_parts = []
            for page in doc:
                text_parts.append(page.get_text())
            text = "\n\n".join(text_parts)[:max_chars]
            return {"result": {"text": text, "pages": len(doc), "chars": len(text)}}
        except ImportError:
            pass

        # Fallback: basic binary text extraction
        try:
            text = pdf_data.decode("latin-1", errors="replace")
            # Extract text between stream markers (very basic)
            import re as _re
            texts = _re.findall(r'\((.*?)\)', text)
            extracted = " ".join(t for t in texts if len(t) > 2 and t.isprintable())[:max_chars]
            return {"result": {"text": extracted, "note": "Basic extraction (install PyMuPDF for better results)", "chars": len(extracted)}}
        except Exception as e:
            return {"error": f"PDF extraction failed: {e}"}

    async def _sys_email_send(self, db, args: dict) -> dict:
        """Send email via SMTP."""
        from app.api.settings import get_setting_value
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        to_addr = args.get("to", "")
        subject = args.get("subject", "")
        body = args.get("body", "")
        is_html = bool(args.get("html", False))
        reply_to = args.get("reply_to", "")

        if not to_addr or not subject or not body:
            return {"error": "to, subject, and body are required"}

        smtp_host = await get_setting_value(db, "smtp_host")
        smtp_port = int(await get_setting_value(db, "smtp_port") or 587)
        smtp_user = await get_setting_value(db, "smtp_user")
        smtp_pass = await get_setting_value(db, "smtp_password")
        smtp_from = await get_setting_value(db, "smtp_from") or smtp_user

        if not smtp_host or not smtp_user:
            return {"error": "SMTP not configured. Add smtp_host, smtp_user, smtp_password in Settings."}

        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_from
            msg["To"] = to_addr
            msg["Subject"] = subject
            if reply_to:
                msg["Reply-To"] = reply_to
            msg.attach(MIMEText(body, "html" if is_html else "plain", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

            return {"result": {"sent": True, "to": to_addr, "subject": subject}}
        except Exception as e:
            return {"error": f"Email sending failed: {e}"}

    async def _sys_schedule_reminder(self, db, agent_id: str, args: dict) -> dict:
        """Create a scheduled reminder (stored as a task in MongoDB)."""
        from datetime import datetime, timedelta, timezone
        from app.mongodb.services import TaskService
        from app.mongodb.models.task import MongoTask

        title = args.get("title", "")
        message = args.get("message", "")
        trigger_at = args.get("trigger_at", "")
        recurring = bool(args.get("recurring", False))

        if not title or not message or not trigger_at:
            return {"error": "title, message, and trigger_at are required"}

        # Parse trigger_at
        now = datetime.now(timezone.utc)
        if trigger_at.startswith("+"):
            # Relative time: +1h, +30m, +2d
            import re as _re
            match = _re.match(r'\+(\d+)([mhd])', trigger_at)
            if not match:
                return {"error": "Invalid relative time format. Use +1h, +30m, +2d"}
            amount, unit = int(match.group(1)), match.group(2)
            delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
            trigger_dt = now + delta
        else:
            try:
                trigger_dt = datetime.fromisoformat(trigger_at.replace("Z", "+00:00"))
                if trigger_dt.tzinfo is None:
                    trigger_dt = trigger_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return {"error": f"Invalid datetime format: {trigger_at}. Use ISO format or +1h/+30m/+2d"}

        # Create as a scheduled task
        try:
            task_svc = TaskService(db)
            task = MongoTask(
                name=f"⏰ Reminder: {title}",
                description=message,
                agent_id=agent_id,
                task_type="reminder",
                schedule_cron="" if not recurring else "0 * * * *",
                enabled=True,
            )
            created = await task_svc.create(task)
            return {
                "result": {
                    "reminder_id": created.id,
                    "title": title,
                    "trigger_at": trigger_dt.isoformat(),
                    "recurring": recurring,
                    "created": True,
                }
            }
        except Exception as e:
            return {"error": f"Failed to create reminder: {e}"}

    async def _sys_yaml_parse(self, args: dict) -> dict:
        """Parse YAML text or file."""
        import yaml

        text = args.get("text", "")
        file_path = args.get("file_path", "")
        operation = args.get("operation", "parse")

        if file_path and not text:
            try:
                from pathlib import Path
                text = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return {"error": f"Failed to read YAML file: {e}"}
        if not text:
            return {"error": "No YAML data provided (text or file_path)"}

        try:
            data = yaml.safe_load(text)
            if operation == "validate":
                return {"result": {"valid": True, "type": type(data).__name__}}
            import json
            return {"result": json.loads(json.dumps(data, default=str))}
        except yaml.YAMLError as e:
            if operation == "validate":
                return {"result": {"valid": False, "error": str(e)}}
            return {"error": f"YAML parse error: {e}"}

    async def _sys_xml_parse(self, args: dict) -> dict:
        """Parse XML data, optionally query with XPath."""
        import xml.etree.ElementTree as ET

        text = args.get("text", "")
        file_path = args.get("file_path", "")
        xpath = args.get("xpath", "")

        if file_path and not text:
            try:
                from pathlib import Path
                text = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return {"error": f"Failed to read XML file: {e}"}
        if not text:
            return {"error": "No XML data provided (text or file_path)"}

        try:
            root = ET.fromstring(text)

            def elem_to_dict(elem):
                result = {"tag": elem.tag}
                if elem.attrib:
                    result["attributes"] = dict(elem.attrib)
                if elem.text and elem.text.strip():
                    result["text"] = elem.text.strip()
                children = [elem_to_dict(c) for c in elem]
                if children:
                    result["children"] = children
                return result

            if xpath:
                elements = root.findall(xpath)
                return {"result": [elem_to_dict(e) for e in elements]}

            return {"result": elem_to_dict(root)}
        except ET.ParseError as e:
            return {"error": f"XML parse error: {e}"}

    async def _sys_regex_extract(self, args: dict) -> dict:
        """Extract data from text using regex."""
        import re as _re

        text = args.get("text", "")
        pattern = args.get("pattern", "")
        operation = args.get("operation", "extract")
        replacement = args.get("replacement", "")
        flags_str = args.get("flags", "")

        if not text or not pattern:
            return {"error": "text and pattern are required"}

        flags = 0
        if "i" in flags_str:
            flags |= _re.IGNORECASE
        if "m" in flags_str:
            flags |= _re.MULTILINE
        if "s" in flags_str:
            flags |= _re.DOTALL

        try:
            compiled = _re.compile(pattern, flags)
            if operation == "match":
                m = compiled.search(text)
                if m:
                    return {"result": {"match": m.group(), "groups": m.groups(), "groupdict": m.groupdict(), "span": list(m.span())}}
                return {"result": None, "message": "No match found"}
            elif operation == "replace":
                result = compiled.sub(replacement, text)
                return {"result": {"text": result, "count": len(compiled.findall(text))}}
            elif operation == "split":
                return {"result": compiled.split(text)}
            else:  # extract
                all_matches = compiled.findall(text)
                return {"result": {"matches": all_matches[:200], "total": len(all_matches)}}
        except _re.error as e:
            return {"error": f"Regex error: {e}"}

    async def _sys_api_call(self, args: dict) -> dict:
        """Make authenticated REST API calls."""
        import httpx

        url = args.get("url", "")
        method = args.get("method", "GET").upper()
        headers = args.get("headers") or {}
        body = args.get("body")
        auth_type = args.get("auth_type", "")
        auth_value = args.get("auth_value", "")
        timeout = int(args.get("timeout", 30))

        if not url:
            return {"error": "No URL provided"}

        # Apply auth
        if auth_type and auth_value:
            if auth_type == "bearer":
                headers["Authorization"] = f"Bearer {auth_value}"
            elif auth_type == "api_key":
                headers["X-API-Key"] = auth_value
            elif auth_type == "basic":
                import base64
                headers["Authorization"] = f"Basic {base64.b64encode(auth_value.encode()).decode()}"

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                kwargs = {"headers": headers}
                if body and method in ("POST", "PUT", "PATCH"):
                    kwargs["json"] = body if isinstance(body, dict) else body
                r = await getattr(client, method.lower())(url, **kwargs)
                try:
                    resp_json = r.json()
                except Exception:
                    resp_json = None
                return {
                    "result": {
                        "status": r.status_code,
                        "body": resp_json if resp_json else r.text[:5000],
                        "headers": dict(r.headers),
                    }
                }
        except Exception as e:
            return {"error": f"API call failed: {e}"}

    async def _sys_math_calculate(self, args: dict) -> dict:
        """Evaluate math expressions safely."""
        import math
        import statistics as _stats

        expression = args.get("expression", "")
        operation = args.get("operation", "eval")
        data = args.get("data")

        if operation == "statistics" and data:
            try:
                nums = [float(x) for x in data]
                result = {
                    "count": len(nums),
                    "sum": sum(nums),
                    "mean": _stats.mean(nums),
                    "median": _stats.median(nums),
                    "min": min(nums),
                    "max": max(nums),
                }
                if len(nums) > 1:
                    result["stdev"] = _stats.stdev(nums)
                    result["variance"] = _stats.variance(nums)
                return {"result": result}
            except Exception as e:
                return {"error": f"Statistics error: {e}"}

        if not expression:
            return {"error": "No expression provided"}

        # Safe math eval
        allowed_names = {
            "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf,
            "sqrt": math.sqrt, "abs": abs, "round": round, "int": int, "float": float,
            "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
            "log": math.log, "log2": math.log2, "log10": math.log10,
            "exp": math.exp, "pow": math.pow,
            "ceil": math.ceil, "floor": math.floor,
            "radians": math.radians, "degrees": math.degrees,
            "factorial": math.factorial, "gcd": math.gcd,
            "min": min, "max": max, "sum": sum,
        }
        try:
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return {"result": {"expression": expression, "value": result}}
        except Exception as e:
            return {"error": f"Math evaluation error: {e}"}

    async def _sys_code_review(self, args: dict) -> dict:
        """Review code using LLM."""
        code = args.get("code", "")
        file_path = args.get("file_path", "")
        language = args.get("language", "auto-detect")
        focus = args.get("focus", "all")

        if file_path and not code:
            try:
                from pathlib import Path
                code = Path(file_path).read_text(encoding="utf-8")
            except Exception as e:
                return {"error": f"Failed to read file: {e}"}
        if not code:
            return {"error": "No code provided (code or file_path)"}

        focus_prompt = {
            "bugs": "Focus specifically on bugs, logic errors, and potential crashes.",
            "security": "Focus specifically on security vulnerabilities, injection risks, and unsafe patterns.",
            "style": "Focus on code style, naming, readability, and best practices.",
            "performance": "Focus on performance issues, inefficiencies, and optimization opportunities.",
            "all": "Review for bugs, security issues, code style, and performance.",
        }.get(focus, "Review for bugs, security issues, code style, and performance.")

        try:
            resp = await self._llm_call(
                [{"role": "user", "content": f"Review this {language} code:\n\n```\n{code[:8000]}\n```\n\n{focus_prompt}\n\nFormat: list each finding with severity (critical/warning/info), category, description, and fix suggestion."}],
                system="You are an expert code reviewer. Provide specific, actionable findings. Be thorough but concise.",
                temperature=0.2,
            )
            return {"result": resp.content if resp else "Could not review the code"}
        except Exception as e:
            return {"error": f"Code review failed: {e}"}

    async def _sys_docker_manage(self, args: dict) -> dict:
        """Manage Docker containers."""
        import asyncio as _asyncio

        operation = args.get("operation", "").lower()
        container = args.get("container", "")
        tail = int(args.get("tail", 50))

        commands = {
            "list": "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}'",
            "images": "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}'",
            "status": f"docker inspect --format '{{{{.State.Status}}}} ({{{{.State.StartedAt}}}})' {container}" if container else "docker ps -a --format 'table {{.Names}}\t{{.Status}}'",
            "start": f"docker start {container}" if container else None,
            "stop": f"docker stop {container}" if container else None,
            "restart": f"docker restart {container}" if container else None,
            "logs": f"docker logs --tail {tail} {container}" if container else None,
        }

        if operation not in commands:
            return {"error": f"Unknown operation: {operation}. Available: {list(commands.keys())}"}

        cmd = commands[operation]
        if not cmd:
            return {"error": f"Container name required for '{operation}'"}

        try:
            proc = await _asyncio.create_subprocess_shell(
                cmd, stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.PIPE
            )
            stdout, stderr = await _asyncio.wait_for(proc.communicate(), timeout=30)
            return {
                "result": {
                    "operation": operation,
                    "output": stdout.decode()[:5000],
                    "error": stderr.decode()[:2000] if proc.returncode != 0 else "",
                    "success": proc.returncode == 0,
                }
            }
        except _asyncio.TimeoutError:
            return {"error": f"Docker operation '{operation}' timed out"}
        except Exception as e:
            return {"error": f"Docker operation failed: {e}"}

    async def _sys_rss_read(self, args: dict) -> dict:
        """Read and parse RSS/Atom feeds."""
        import httpx
        import xml.etree.ElementTree as ET

        url = args.get("url", "")
        limit = int(args.get("limit", 20))

        if not url:
            return {"error": "No feed URL provided"}

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code != 200:
                    return {"error": f"Failed to fetch feed: HTTP {r.status_code}"}

            root = ET.fromstring(r.text)
            entries = []

            # RSS 2.0
            for item in root.findall(".//item")[:limit]:
                entries.append({
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "description": (item.findtext("description") or "").strip()[:500],
                    "pubDate": (item.findtext("pubDate") or "").strip(),
                })

            # Atom
            if not entries:
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                for entry in root.findall(".//atom:entry", ns)[:limit]:
                    link_el = entry.find("atom:link", ns)
                    entries.append({
                        "title": (entry.findtext("atom:title", "", ns)).strip(),
                        "link": link_el.get("href", "") if link_el is not None else "",
                        "description": (entry.findtext("atom:summary", "", ns)).strip()[:500],
                        "pubDate": (entry.findtext("atom:updated", "", ns)).strip(),
                    })

            return {"result": {"entries": entries, "total": len(entries), "feed_url": url}}
        except ET.ParseError as e:
            return {"error": f"Feed parse error: {e}"}
        except Exception as e:
            return {"error": f"RSS read failed: {e}"}

    async def _sys_weather_check(self, args: dict) -> dict:
        """Check weather for a location using Open-Meteo (free, no API key)."""
        import httpx

        location = str(args.get("location", "")).strip()
        if not location:
            return {"error": "No location provided"}

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                # Step 1: Geocode the location name
                geo_resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1, "language": "en"},
                )
                geo_data = geo_resp.json()
                results = geo_data.get("results", [])
                if not results:
                    return {"error": f"Location '{location}' not found"}

                place = results[0]
                lat = place["latitude"]
                lon = place["longitude"]
                resolved_name = f"{place.get('name', location)}, {place.get('country', '')}"

                # Step 2: Get current weather + 3-day forecast
                weather_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                        "timezone": "auto",
                        "forecast_days": 3,
                    },
                )
                w = weather_resp.json()

                # WMO weather codes → descriptions
                wmo_codes = {
                    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
                    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
                    55: "Dense drizzle", 56: "Freezing drizzle", 57: "Dense freezing drizzle",
                    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
                    66: "Freezing rain", 67: "Heavy freezing rain",
                    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
                    77: "Snow grains", 80: "Slight showers", 81: "Moderate showers",
                    82: "Violent showers", 85: "Slight snow showers", 86: "Heavy snow showers",
                    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
                }

                current = w.get("current", {})
                daily = w.get("daily", {})
                code = current.get("weather_code", 0)

                forecast = []
                dates = daily.get("time", [])
                for i, date in enumerate(dates):
                    fc_code = (daily.get("weather_code", []) or [0])[i] if i < len(daily.get("weather_code", [])) else 0
                    forecast.append({
                        "date": date,
                        "high": daily.get("temperature_2m_max", [None])[i],
                        "low": daily.get("temperature_2m_min", [None])[i],
                        "precipitation_mm": daily.get("precipitation_sum", [0])[i],
                        "description": wmo_codes.get(fc_code, f"Code {fc_code}"),
                    })

                return {
                    "result": {
                        "location": resolved_name,
                        "current": {
                            "temperature_c": current.get("temperature_2m"),
                            "humidity_pct": current.get("relative_humidity_2m"),
                            "wind_speed_kmh": current.get("wind_speed_10m"),
                            "description": wmo_codes.get(code, f"Code {code}"),
                        },
                        "forecast": forecast,
                    }
                }
        except Exception as e:
            return {"error": f"Weather check failed: {e}"}

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
        # Include creator context when available (not greetings) and agent has it enabled
        if not classification.is_greeting and "creator_context" in available:
            use_creator = getattr(self.ctx.agent, 'use_creator_context', True)
            if use_creator:
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
            # Build truncated results for logging
            skill_results_summary = {}
            for sk_name, sk_result in gather_results.items():
                try:
                    result_str = json.dumps(sk_result, ensure_ascii=False, default=str)
                    skill_results_summary[sk_name] = result_str[:2000] + ("…" if len(result_str) > 2000 else "")
                except Exception:
                    skill_results_summary[sk_name] = str(sk_result)[:2000]

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
                    "skill_results": skill_results_summary,
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
8. CRITICAL: When a step needs the OUTPUT of a previous step, use template {{{{stepN.result}}}} where N is the step id. Example: step 2 uses step 1 output → args={{"content": "{{{{step1.result}}}}"}}. NEVER use descriptive placeholders like [final text] or [result from step 1] — always use {{{{stepN.result}}}} templates.

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

            # Resolve references to previous step results
            resolved_args = _resolve_step_refs(raw_args, step_results)

            # Smart arg inference
            args = _infer_args(skill_name, resolved_args, context)

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
                "I performed a search and obtained the following data:\n\n"
                + gathered_text
                + "\n\nLet me process this information for you."
            )})
            messages.append({"role": "user", "content": (
                "Great, now based on this data give me a complete answer to my question: "
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
                    "messages_sent": [
                        {"role": m["role"], "content": m["content"][:3000]}
                        for m in messages
                    ],
                },
                output_data={
                    "response_length": len(content),
                    "response": content,
                    "timed_out": timed_out,
                    "tokens": self._total_tokens,
                    "model": self._model_name,
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
