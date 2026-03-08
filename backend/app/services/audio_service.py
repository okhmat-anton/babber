"""
Audio service: TTS (Text-to-Speech) and STT (Speech-to-Text) via kie.ai.

Provider: kie.ai (ElevenLabs proxy)
 - TTS: https://api.kie.ai/v1/audio/text-to-speech
 - STT: https://api.kie.ai/v1/audio/speech-to-text

API key stored in SystemSettings: kieai_api_key
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
    Generate audio from text via kie.ai.
    Returns: {"audio_url": "/api/uploads/audio/<file>", "provider": "kieai", "duration_ms": ...}
    """
    start = time.time()
    result = await _tts_kieai(db, text, voice)
    duration_ms = int((time.time() - start) * 1000)
    result["duration_ms"] = duration_ms
    result["provider"] = "kieai"
    await syslog("info", f"TTS [kieai]: {len(text)} chars → {result.get('filename', '?')} ({duration_ms}ms)", source="audio")
    return result


async def _tts_kieai(db: AsyncIOMotorDatabase, text: str, voice: str | None) -> dict:
    """kie.ai TTS (ElevenLabs proxy): https://kie.ai/elevenlabs/text-to-dialogue-v3"""
    api_key = await _get_setting(db, "kieai_api_key")
    if not api_key:
        raise ValueError("kie.ai API key not configured. Set 'kieai_api_key' in System Settings.")

    voice = voice or "Rachel"  # ElevenLabs default voices
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = AUDIO_DIR / filename

    # kie.ai uses ElevenLabs-compatible API
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.kie.ai/v1/audio/text-to-speech",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "text": text,
                "voice_id": voice,
                "model_id": "eleven_multilingual_v2",
                "output_format": "mp3_44100_128",
            },
        )
        if resp.status_code != 200:
            error_text = resp.text[:500]
            raise ValueError(f"kie.ai TTS error: HTTP {resp.status_code}: {error_text}")
        
        # Response is direct audio bytes
        filepath.write_bytes(resp.content)

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
    Transcribe audio to text via kie.ai.
    Returns: {"text": "...", "provider": "kieai", "duration_ms": ..., "language": "..."}
    """
    start = time.time()
    result = await _stt_kieai(db, audio_data, audio_format, language)
    duration_ms = int((time.time() - start) * 1000)
    result["duration_ms"] = duration_ms
    result["provider"] = "kieai"
    await syslog("info", f"STT [kieai]: {len(audio_data)} bytes → {len(result.get('text', ''))} chars ({duration_ms}ms)", source="audio")
    return result


async def _stt_kieai(
    db: AsyncIOMotorDatabase,
    audio_data: bytes,
    audio_format: str = "wav",
    language: str | None = None,
) -> dict:
    """kie.ai STT (ElevenLabs proxy): https://kie.ai/elevenlabs-speech-to-text"""
    api_key = await _get_setting(db, "kieai_api_key")
    if not api_key:
        raise ValueError("kie.ai API key not configured. Set 'kieai_api_key' in System Settings.")

    ext = audio_format if audio_format in ("wav", "mp3", "webm", "m4a", "ogg", "flac") else "wav"

    async with httpx.AsyncClient(timeout=120) as client:
        files = {"audio": (f"audio.{ext}", audio_data, f"audio/{ext}")}
        data = {}
        if language:
            data["language"] = language

        resp = await client.post(
            "https://api.kie.ai/v1/audio/speech-to-text",
            headers={"Authorization": f"Bearer {api_key}"},
            files=files,
            data=data,
        )
        if resp.status_code != 200:
            error_text = resp.text[:500]
            raise ValueError(f"kie.ai STT error: HTTP {resp.status_code}: {error_text}")

        result = resp.json()
        return {"text": result.get("text", "")}


# ── Available voices ─────────────────────────────────────────────────

KIEAI_VOICES = [
    "Rachel",
    "Clyde",
    "Domi",
    "Dave",
    "Fin",
    "Sarah",
    "Laura",
    "Charlie",
    "George",
    "Callum",
    "Charlotte",
    "Alice",
    "Matilda",
    "Will",
]


def get_available_voices(provider: str = "kieai") -> list[str]:
    return KIEAI_VOICES
