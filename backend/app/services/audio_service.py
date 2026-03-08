"""
Audio service: TTS (Text-to-Speech) and STT (Speech-to-Text).

Providers:
 - OpenAI: TTS via /v1/audio/speech, STT via /v1/audio/transcriptions (Whisper)
 - MiniMax: TTS via /v1/t2a_v2, STT not natively supported (fallback to OpenAI)

API keys stored in SystemSettings: openai_api_key, minimax_api_key, minimax_group_id
Provider selection: tts_provider, stt_provider  (system settings)
"""
import os
import uuid
import time
import httpx
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.mongodb.services import SystemSettingService
from app.services.log_service import syslog


AUDIO_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))).resolve() / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


async def _get_setting(db: AsyncIOMotorDatabase, key: str) -> str | None:
    svc = SystemSettingService(db)
    s = await svc.get_by_key(key)
    return s.value if s else None


# ── TTS ──────────────────────────────────────────────────────────────

async def text_to_speech(
    db: AsyncIOMotorDatabase,
    text: str,
    voice: str | None = None,
    provider: str | None = None,
) -> dict:
    """
    Generate audio from text.
    Returns: {"audio_url": "/api/uploads/audio/<file>", "provider": "...", "duration_ms": ...}
    """
    if not provider:
        provider = await _get_setting(db, "tts_provider") or "openai"

    start = time.time()

    if provider == "minimax":
        result = await _tts_minimax(db, text, voice)
    elif provider == "openai":
        result = await _tts_openai(db, text, voice)
    else:
        raise ValueError(f"Unknown TTS provider: {provider}")

    duration_ms = int((time.time() - start) * 1000)
    result["duration_ms"] = duration_ms
    result["provider"] = provider
    await syslog("info", f"TTS [{provider}]: {len(text)} chars → {result.get('filename', '?')} ({duration_ms}ms)", source="audio")
    return result


async def _tts_openai(db: AsyncIOMotorDatabase, text: str, voice: str | None) -> dict:
    api_key = await _get_setting(db, "openai_api_key")
    if not api_key:
        raise ValueError("OpenAI API key not configured. Set 'openai_api_key' in System Settings.")

    voice = voice or "alloy"  # alloy, echo, fable, onyx, nova, shimmer
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": "tts-1",
                "input": text,
                "voice": voice,
                "response_format": "mp3",
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenAI TTS error: {resp.status_code} {resp.text[:500]}")
        filepath.write_bytes(resp.content)

    return {"audio_url": f"/api/uploads/audio/{filename}", "filename": filename}


async def _tts_minimax(db: AsyncIOMotorDatabase, text: str, voice: str | None) -> dict:
    api_key = await _get_setting(db, "minimax_api_key")
    if not api_key:
        raise ValueError("MiniMax API key not configured. Set 'minimax_api_key' in System Settings.")

    group_id = await _get_setting(db, "minimax_group_id")
    if not group_id:
        raise ValueError("MiniMax Group ID not configured. Set 'minimax_group_id' in System Settings.")

    voice = voice or "male-qn-qingse"
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    url = f"https://api.minimaxi.com/v1/t2a_v2?GroupId={group_id}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "speech-01-turbo",
                "text": text,
                "voice_setting": {
                    "voice_id": voice,
                    "speed": 1.0,
                    "vol": 1.0,
                    "pitch": 0,
                },
                "audio_setting": {
                    "sample_rate": 32000,
                    "bitrate": 128000,
                    "format": "mp3",
                },
            },
        )
        if resp.status_code != 200:
            raise ValueError(f"MiniMax TTS HTTP error: {resp.status_code} {resp.text[:500]}")

        data = resp.json()
        base_resp = data.get("base_resp", {})
        status_code = base_resp.get("status_code", 0)
        if status_code != 0:
            status_msg = base_resp.get("status_msg", "unknown error")
            if status_code == 2049 or "invalid api key" in status_msg.lower():
                raise ValueError(
                    f"MiniMax API key is invalid. Please check your API key in Settings → Audio & AI API Keys. "
                    f"(MiniMax error: {status_msg})"
                )
            elif status_code == 1004:
                raise ValueError(f"MiniMax authentication failed: {status_msg}")
            raise ValueError(f"MiniMax TTS error ({status_code}): {status_msg}")

        # MiniMax returns audio data in hex-encoded format or base64
        audio_hex = data.get("data", {}).get("audio", "")
        if not audio_hex:
            # Try direct streaming endpoint
            raise ValueError("MiniMax TTS returned no audio data")

        import base64
        audio_bytes = bytes.fromhex(audio_hex) if all(c in '0123456789abcdef' for c in audio_hex[:20]) else base64.b64decode(audio_hex)
        filepath.write_bytes(audio_bytes)

    return {"audio_url": f"/api/uploads/audio/{filename}", "filename": filename}


# ── STT ──────────────────────────────────────────────────────────────

async def speech_to_text(
    db: AsyncIOMotorDatabase,
    audio_data: bytes,
    audio_format: str = "wav",
    provider: str | None = None,
    language: str | None = None,
) -> dict:
    """
    Transcribe audio to text.
    Returns: {"text": "...", "provider": "...", "duration_ms": ..., "language": "..."}
    """
    if not provider:
        provider = await _get_setting(db, "stt_provider") or "openai"

    start = time.time()

    if provider == "openai":
        result = await _stt_openai(db, audio_data, audio_format, language)
    elif provider == "minimax":
        # MiniMax doesn't have a dedicated STT API — fallback to OpenAI
        await syslog("info", "MiniMax STT not available, falling back to OpenAI", source="audio")
        result = await _stt_openai(db, audio_data, audio_format, language)
        result["provider_note"] = "MiniMax STT unavailable, used OpenAI Whisper"
    else:
        raise ValueError(f"Unknown STT provider: {provider}")

    duration_ms = int((time.time() - start) * 1000)
    result["duration_ms"] = duration_ms
    result["provider"] = provider
    await syslog("info", f"STT [{provider}]: {len(audio_data)} bytes → {len(result.get('text', ''))} chars ({duration_ms}ms)", source="audio")
    return result


async def _stt_openai(
    db: AsyncIOMotorDatabase,
    audio_data: bytes,
    audio_format: str = "wav",
    language: str | None = None,
) -> dict:
    api_key = await _get_setting(db, "openai_api_key")
    if not api_key:
        raise ValueError("OpenAI API key not configured. Set 'openai_api_key' in System Settings.")

    ext = audio_format if audio_format in ("wav", "mp3", "webm", "m4a", "ogg", "flac") else "wav"

    async with httpx.AsyncClient(timeout=120) as client:
        files = {"file": (f"audio.{ext}", audio_data, f"audio/{ext}")}
        data = {"model": "whisper-1"}
        if language:
            data["language"] = language

        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
        )
        if resp.status_code != 200:
            raise ValueError(f"OpenAI STT error: {resp.status_code} {resp.text[:500]}")

        result = resp.json()
        return {"text": result.get("text", "")}


# ── Available voices ─────────────────────────────────────────────────

OPENAI_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

MINIMAX_VOICES = [
    "male-qn-qingse",
    "male-qn-jingying", 
    "male-qn-badao",
    "male-qn-daxuesheng",
    "female-shaonv",
    "female-yujie",
    "female-chengshu",
    "female-tianmei",
    "presenter_male",
    "presenter_female",
    "audiobook_male_1",
    "audiobook_male_2",
    "audiobook_female_1",
    "audiobook_female_2",
]


def get_available_voices(provider: str) -> list[str]:
    if provider == "openai":
        return OPENAI_VOICES
    elif provider == "minimax":
        return MINIMAX_VOICES
    return []
