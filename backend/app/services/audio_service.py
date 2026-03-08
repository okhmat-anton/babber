"""
Audio service: TTS (Text-to-Speech) and STT (Speech-to-Text) via kie.ai.

kie.ai API is ASYNC with CALLBACK:
  1. POST https://api.kie.ai/api/v1/jobs/createTask → {taskId}
  2. kie.ai calls our callBackUrl when done (POST with result data)
  3. We download audio from resultUrls

Settings:
  - kieai_api_key:      API key for kie.ai
  - callback_base_url:  Public URL of this server (e.g. https://xxx.ngrok.io)
  - tts_timeout:        Max seconds to wait for callback (default 120)
"""
import json
import os
import uuid
import time
import asyncio
import httpx
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.mongodb.services import SystemSettingService
from app.services.log_service import syslog


AUDIO_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))).resolve() / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

KIEAI_API_BASE = "https://api.kie.ai/api/v1/jobs"
KIEAI_CREATE_TASK = f"{KIEAI_API_BASE}/createTask"

KIEAI_TTS_MODEL = "elevenlabs/text-to-speech-turbo-2-5"

KIEAI_MAX_WAIT_DEFAULT = 120  # default max seconds to wait for callback


# ── Pending task registry (in-process, taskId → Event/result) ────────

_pending_tasks: dict[str, asyncio.Event] = {}
_task_results: dict[str, dict] = {}


def register_pending_task(task_id: str) -> asyncio.Event:
    """Register a task and return an Event to await."""
    event = asyncio.Event()
    _pending_tasks[task_id] = event
    return event


def resolve_task(task_id: str, data: dict):
    """Called by the callback endpoint when kie.ai sends the result."""
    _task_results[task_id] = data
    event = _pending_tasks.get(task_id)
    if event:
        event.set()


def get_task_result(task_id: str) -> dict | None:
    """Get and clean up a completed task result."""
    _pending_tasks.pop(task_id, None)
    return _task_results.pop(task_id, None)


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_setting(db: AsyncIOMotorDatabase, key: str) -> str | None:
    svc = SystemSettingService(db)
    s = await svc.get_by_key(key)
    return s.value if s else None


def _auth_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# ── kie.ai task creation ─────────────────────────────────────────────

async def _create_task(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    input_data: dict,
    callback_url: str | None = None,
) -> str:
    """Submit a task to kie.ai -> returns taskId."""
    payload = {
        "model": model,
        "input": input_data,
    }
    if callback_url:
        payload["callBackUrl"] = callback_url

    await syslog("debug", f"KIEAI createTask: model={model}, callback={callback_url}", source="audio")

    resp = await client.post(KIEAI_CREATE_TASK, headers=_auth_headers(api_key), json=payload)
    await syslog("debug", f"KIEAI createTask response: status={resp.status_code}, body={resp.text[:500]}", source="audio")

    if resp.status_code != 200:
        error_text = resp.text[:1000]
        raise ValueError(f"kie.ai createTask error: HTTP {resp.status_code}: {error_text}")

    body = resp.json()
    code = body.get("code")
    if code != 200:
        msg = body.get("msg", "Unknown error")
        raise ValueError(f"kie.ai error ({code}): {msg}")

    task_id = (body.get("data") or {}).get("taskId")
    if not task_id:
        raise ValueError(f"kie.ai createTask returned no taskId: {body}")

    await syslog("info", f"KIEAI task created: {task_id}", source="audio")
    return task_id


# ── TTS ──────────────────────────────────────────────────────────────

async def text_to_speech(
    db: AsyncIOMotorDatabase,
    text: str,
    voice: str | None = None,
    provider: str | None = None,
) -> dict:
    """
    Generate audio from text via kie.ai (async task with callback).
    Returns: {"audio_url": "/api/uploads/audio/<file>", "provider": "kieai", "duration_ms": ...}
    """
    await syslog("info", f"TTS START: text_length={len(text)}, voice={voice}", source="audio")
    start = time.time()
    try:
        result = await _tts_kieai(db, text, voice)
        duration_ms = int((time.time() - start) * 1000)
        result["duration_ms"] = duration_ms
        result["provider"] = "kieai"
        await syslog("info", f"TTS COMPLETE: {len(text)} chars -> {result.get('filename', '?')} ({duration_ms}ms)", source="audio")
        return result
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        await syslog("error", f"TTS FAILED: {type(e).__name__}: {str(e)} ({duration_ms}ms)", source="audio")
        raise


async def _tts_kieai(db: AsyncIOMotorDatabase, text: str, voice: str | None) -> dict:
    """
    kie.ai TTS via async job API with callback:
      1. POST createTask with callBackUrl pointing to our /api/audio/callback
      2. Wait for kie.ai to POST result to our callback endpoint
      3. Download audio from resultUrls
    """
    api_key = await _get_setting(db, "kieai_api_key")
    if not api_key:
        raise ValueError("kie.ai API key not configured. Set 'kieai_api_key' in System Settings.")

    callback_base = await _get_setting(db, "callback_base_url")
    if not callback_base:
        raise ValueError(
            "Callback Base URL not configured. kie.ai requires a public URL to send results. "
            "Set 'callback_base_url' in Settings (e.g. your public domain or ngrok URL)."
        )

    timeout_str = await _get_setting(db, "tts_timeout")
    max_wait = int(timeout_str) if timeout_str and timeout_str.isdigit() else KIEAI_MAX_WAIT_DEFAULT

    voice = voice or "Rachel"
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    input_data = {
        "text": text,
        "voice": voice,
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0,
        "speed": 1,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        callback_url = f"{callback_base.rstrip('/')}/api/audio/callback"

        # Step 1: Create task
        task_id = await _create_task(client, api_key, KIEAI_TTS_MODEL, input_data, callback_url)

        # Register BEFORE callback could arrive
        event = register_pending_task(task_id)

        await syslog("debug", f"TTS: waiting for callback, task={task_id}, max_wait={max_wait}s", source="audio")

        # Step 2: Wait for callback
        try:
            await asyncio.wait_for(event.wait(), timeout=max_wait)
        except asyncio.TimeoutError:
            _pending_tasks.pop(task_id, None)
            _task_results.pop(task_id, None)
            raise TimeoutError(
                f"kie.ai task {task_id} did not complete within {max_wait}s. "
                f"Check that callback_base_url ({callback_base}) is reachable from the internet."
            )

        # Step 3: Process result
        task_data = get_task_result(task_id)
        if not task_data:
            raise ValueError(f"Task {task_id} event fired but no result data")

        state = task_data.get("state", "unknown")
        if state != "success":
            fail_msg = task_data.get("failMsg", "Unknown failure")
            fail_code = task_data.get("failCode", "?")
            raise ValueError(f"kie.ai task failed ({fail_code}): {fail_msg}")

        # Parse resultJson -> resultUrls
        result_json_str = task_data.get("resultJson", "{}")
        try:
            result_json = json.loads(result_json_str) if isinstance(result_json_str, str) else result_json_str
        except (json.JSONDecodeError, TypeError):
            raise ValueError(f"kie.ai returned invalid resultJson: {str(result_json_str)[:500]}")

        result_urls = result_json.get("resultUrls", [])
        if not result_urls:
            raise ValueError(f"kie.ai task completed but no resultUrls in: {result_json}")

        audio_url = result_urls[0]
        await syslog("debug", f"TTS: downloading audio from {audio_url}", source="audio")

        # Step 4: Download audio
        dl_resp = await client.get(audio_url, follow_redirects=True)
        if dl_resp.status_code != 200:
            raise ValueError(f"Failed to download audio from {audio_url}: HTTP {dl_resp.status_code}")

        audio_bytes = dl_resp.content
        if not audio_bytes or len(audio_bytes) == 0:
            raise ValueError("Downloaded audio file is empty")

        filepath.write_bytes(audio_bytes)
        file_size = len(audio_bytes)
        await syslog("info", f"TTS SUCCESS: {filename} ({file_size} bytes) from task {task_id}", source="audio")

    return {"audio_url": f"/api/uploads/audio/{filename}", "filename": filename, "file_size": file_size}


# ── STT ──────────────────────────────────────────────────────────────

async def speech_to_text(
    db: AsyncIOMotorDatabase,
    audio_data: bytes,
    audio_format: str = "wav",
    provider: str | None = None,
    language: str | None = None,
) -> dict:
    """Transcribe audio to text via kie.ai."""
    await syslog("info", f"STT START: audio_size={len(audio_data)}, format={audio_format}, language={language}", source="audio")
    start = time.time()
    try:
        result = await _stt_kieai(db, audio_data, audio_format, language)
        duration_ms = int((time.time() - start) * 1000)
        result["duration_ms"] = duration_ms
        result["provider"] = "kieai"
        await syslog("info", f"STT COMPLETE: {len(audio_data)} bytes -> {len(result.get('text', ''))} chars ({duration_ms}ms)", source="audio")
        return result
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        await syslog("error", f"STT FAILED: {type(e).__name__}: {str(e)} ({duration_ms}ms)", source="audio")
        raise


async def _stt_kieai(
    db: AsyncIOMotorDatabase,
    audio_data: bytes,
    audio_format: str = "wav",
    language: str | None = None,
) -> dict:
    """kie.ai STT via direct ElevenLabs-proxy endpoint."""
    api_key = await _get_setting(db, "kieai_api_key")
    if not api_key:
        raise ValueError("kie.ai API key not configured. Set 'kieai_api_key' in System Settings.")

    ext = audio_format if audio_format in ("wav", "mp3", "webm", "m4a", "ogg", "flac") else "wav"
    url = "https://kie.ai/elevenlabs-speech-to-text"

    await syslog("debug", f"STT: direct request to {url}, audio_size={len(audio_data)}, format={ext}", source="audio")

    async with httpx.AsyncClient(timeout=120) as client:
        files = {"audio": (f"audio.{ext}", audio_data, f"audio/{ext}")}
        data = {}
        if language:
            data["language"] = language

        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
        )

        await syslog("debug", f"STT RESPONSE: status={resp.status_code}, ct={resp.headers.get('content-type', 'N/A')}", source="audio")

        if resp.status_code != 200:
            error_text = resp.text[:1000]
            raise ValueError(f"kie.ai STT error: HTTP {resp.status_code}: {error_text}")

        try:
            result = resp.json()
            text = result.get("text", "")
            await syslog("info", f"STT SUCCESS: {len(audio_data)} bytes -> {len(text)} chars", source="audio")
            return {"text": text}
        except Exception as e:
            raise ValueError(f"kie.ai STT error: Invalid JSON response: {e}")


# ── Available voices ─────────────────────────────────────────────────

KIEAI_VOICES = [
    "Rachel",
    "Aria",
    "Roger",
    "Sarah",
    "Laura",
    "Charlie",
    "George",
    "Callum",
    "River",
    "Liam",
    "Charlotte",
    "Alice",
    "Matilda",
    "Will",
    "Jessica",
    "Eric",
    "Chris",
    "Brian",
    "Daniel",
    "Lily",
    "Bill",
]


def get_available_voices(provider: str = "kieai") -> list[str]:
    return KIEAI_VOICES
