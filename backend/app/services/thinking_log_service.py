"""
Thinking Log Service — captures detailed agent reasoning traces.

Usage within chat.py:
    tracker = ThinkingTracker(db, agent_id, session_id, user_input)
    await tracker.start()

    await tracker.step("config_load", "Loading agent config", input_data={...}, output_data={...})
    await tracker.step("prompt_build", "Building system prompt", ...)
    await tracker.step("llm_call", "LLM inference", ...)

    await tracker.complete(agent_output, message_id, model_name, total_tokens, ...)
    # or
    await tracker.fail(error_message)
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.mongodb.models import MongoThinkingLog, MongoThinkingStep
from app.mongodb.services import ThinkingLogService, ThinkingStepService


class ThinkingTracker:
    """Context manager-style tracker for a single thinking iteration."""

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        agent_id,
        session_id,
        user_input: str,
    ):
        self.db = db
        self.agent_id = str(agent_id)
        self.session_id = str(session_id)
        self.user_input = user_input
        self.log: MongoThinkingLog | None = None
        self._step_order = 0
        self._start_time = 0.0
        self._step_start = 0.0

    async def start(self) -> MongoThinkingLog:
        """Create the thinking log entry in DB."""
        self._start_time = time.monotonic()
        self.log = MongoThinkingLog(
            agent_id=self.agent_id,
            session_id=self.session_id,
            user_input=self.user_input[:2000],
            status="started",
        )
        self.log = await ThinkingLogService(self.db).create(self.log)
        return self.log

    async def step(
        self,
        step_type: str,
        step_name: str,
        *,
        input_data: dict | None = None,
        output_data: dict | None = None,
        status: str = "completed",
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> MongoThinkingStep:
        """Record a single step in the thinking process."""
        if not self.log:
            await self.start()

        self._step_order += 1

        step = MongoThinkingStep(
            thinking_log_id=self.log.id,
            step_order=self._step_order,
            step_type=step_type,
            step_name=step_name,
            input_data=_safe_jsonb(input_data),
            output_data=_safe_jsonb(output_data),
            status=status,
            error_message=error_message,
            duration_ms=duration_ms or 0,
        )
        step = await ThinkingStepService(self.db).create(step)
        return step

    def start_step_timer(self):
        """Start a timer for measuring step duration."""
        self._step_start = time.monotonic()

    def elapsed_step_ms(self) -> int:
        """Get ms since last start_step_timer."""
        return int((time.monotonic() - self._step_start) * 1000)

    async def complete(
        self,
        agent_output: str,
        *,
        message_id=None,
        model_name: str | None = None,
        total_tokens: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        llm_calls_count: int = 1,
    ) -> MongoThinkingLog:
        """Mark the thinking log as completed."""
        if not self.log:
            return None

        total_ms = int((time.monotonic() - self._start_time) * 1000)

        update_data = {
            "agent_output": (agent_output[:5000] if agent_output else None),
            "message_id": str(message_id) if message_id else None,
            "model_name": model_name,
            "total_duration_ms": total_ms,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "llm_calls_count": llm_calls_count,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.log = await ThinkingLogService(self.db).update(self.log.id, update_data)
        return self.log

    async def fail(self, error_message: str) -> MongoThinkingLog:
        """Mark the thinking log as failed."""
        if not self.log:
            return None

        total_ms = int((time.monotonic() - self._start_time) * 1000)
        update_data = {
            "total_duration_ms": total_ms,
            "status": "error",
            "error_message": error_message,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.log = await ThinkingLogService(self.db).update(self.log.id, update_data)
        return self.log


async def cleanup_stale_thinking_logs(db) -> int:
    """Mark all 'started' thinking logs as stale (server restart cleanup).

    Called on startup to close any thinking logs that were left in 'started'
    status from a previous run (e.g. due to server crash or task cancellation).
    Returns the number of cleaned-up logs.
    """
    from app.mongodb.services import ThinkingLogService as TLS
    svc = TLS(db)
    collection = svc.collection
    result = await collection.update_many(
        {"status": "started"},
        {"$set": {
            "status": "error",
            "error_message": "Stale: cleaned up on server restart",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    count = result.modified_count
    if count:
        logging.getLogger(__name__).info(f"Cleaned up {count} stale thinking log(s)")
    return count


def _safe_jsonb(data: dict | None) -> dict | None:
    """Ensure data is JSON-serializable and not too large."""
    if data is None:
        return None
    # Truncate very large string values to keep DB manageable
    result = {}
    for k, v in data.items():
        if isinstance(v, str) and len(v) > 3000:
            result[k] = v[:3000] + "... [truncated]"
        elif isinstance(v, list) and len(v) > 50:
            result[k] = v[:50]
            result[f"_{k}_total"] = len(v)
        else:
            result[k] = v
    return result
