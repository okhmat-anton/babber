"""Telegram integration service — Telethon client management, auth flow, message handling."""
import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Media storage directory ──────────────────────────────────────────────
CHAT_MEDIA_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))).resolve() / "data" / "chat_media"
CHAT_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# ── Global client registry ───────────────────────────────────────────────
# messenger_id -> { client, agent_id, config, trusted_users, ... }
_active_clients: Dict[str, Dict[str, Any]] = {}

# Pending auth flows: messenger_id -> { client, phone_code_hash }
_pending_auth: Dict[str, Dict[str, Any]] = {}

# Per-messenger lock: ensures at most ONE TelegramClient connection per account at a time
_session_locks: Dict[str, asyncio.Lock] = {}


def _get_session_lock(messenger_id: str) -> asyncio.Lock:
    """Get or create an asyncio Lock for the given messenger_id."""
    if messenger_id not in _session_locks:
        _session_locks[messenger_id] = asyncio.Lock()
    return _session_locks[messenger_id]


# ── Helper: log to MongoDB ──────────────────────────────────────────────

async def _log_messenger_event(
    messenger_id: str, agent_id: str,
    level: str, event: str, message: str,
    context: dict = None,
):
    """Write a log entry to messenger_logs collection. Non-blocking on error."""
    try:
        from app.database import get_mongodb
        from app.mongodb.models.messenger import MongoMessengerLog
        from app.mongodb.services import MessengerLogService
        db = get_mongodb()
        log = MongoMessengerLog(
            messenger_id=messenger_id,
            agent_id=agent_id,
            level=level,
            event=event,
            message=message,
            context=context,
        )
        await MessengerLogService(db).create(log)
    except Exception as e:
        logger.warning(f"Failed to write messenger log: {e}")


async def _log_messenger_error(
    messenger_id: str, agent_id: str,
    error_type: str, message: str,
    context: dict = None,
):
    """Create both a messenger log and an AgentError (source=messenger)."""
    try:
        from app.database import get_mongodb
        from app.mongodb.models.agent import MongoAgentError
        from app.mongodb.services import AgentErrorService
        db = get_mongodb()
        await _log_messenger_event(messenger_id, agent_id, "error", "error", message, context)
        err = MongoAgentError(
            agent_id=agent_id,
            error_type=error_type,
            source="messenger",
            message=message,
            context={**(context or {}), "messenger_id": messenger_id},
        )
        await AgentErrorService(db).create(err)
    except Exception as e:
        logger.warning(f"Failed to write messenger error: {e}")

# Session files directory
_SESSION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "messengers", "sessions"
)
os.makedirs(_SESSION_DIR, exist_ok=True)


def _session_path(messenger_id: str) -> str:
    return os.path.join(_SESSION_DIR, messenger_id)


# ── Auth Flow ────────────────────────────────────────────────────────────

async def start_auth_flow(messenger_id: str, api_id: int, api_hash: str, phone: str) -> dict:
    """Start Telegram auth — send code to phone. Returns phone_code_hash."""
    lock = _get_session_lock(messenger_id)
    async with lock:
        # Disconnect active listener if running (auth takes priority)
        existing = _active_clients.get(messenger_id)
        if existing and existing.get("client"):
            try:
                existing["stop_requested"] = True
                await existing["client"].disconnect()
            except Exception:
                pass
            _active_clients.pop(messenger_id, None)

        session_file = _session_path(messenger_id)
        client = TelegramClient(session_file, api_id, api_hash)
        await client.connect()

        if await client.is_user_authorized():
            me = await client.get_me()
            await client.disconnect()
            _pending_auth.pop(messenger_id, None)
            return {
                "status": "already_authenticated",
                "username": me.username or "",
                "phone": me.phone or "",
                "first_name": me.first_name or "",
            }

        result = await client.send_code_request(phone)

        _pending_auth[messenger_id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": result.phone_code_hash,
        }

        return {
            "status": "code_sent",
            "phone_code_hash": result.phone_code_hash,
            "message": f"Verification code sent to {phone}",
        }


# ── Test Connection ──────────────────────────────────────────────────────

async def test_telegram_connection(
    messenger_id: str,
    creds: dict,
    test_message: str = "Hello from AI Agent test! 🤖",
    chat_id: str = None,
) -> dict:
    """
    Test Telegram connectivity: connect, verify auth, send a test message
    to Saved Messages (or specified chat), read it back.
    """
    api_id = int(creds["api_id"])
    api_hash = creds["api_hash"]
    session_file = _session_path(messenger_id)

    # Use session lock to prevent concurrent SQLite access
    lock = _get_session_lock(messenger_id)
    async with lock:
        existing = _active_clients.get(messenger_id)
        client = existing["client"] if existing else TelegramClient(session_file, api_id, api_hash)
        own_client = not existing

        try:
            if own_client:
                await client.connect()

            if not await client.is_user_authorized():
                raise RuntimeError("Client not authenticated. Complete auth flow first.")

            me = await client.get_me()

            # Send to specified chat or to Saved Messages (self)
            target = int(chat_id) if chat_id else "me"
            sent_msg = await client.send_message(target, test_message)

            # Determine recipient display name
            sent_to = "Saved Messages"
            if chat_id:
                try:
                    entity = await client.get_entity(int(chat_id))
                    name = getattr(entity, 'first_name', '') or getattr(entity, 'title', '') or str(chat_id)
                    username = getattr(entity, 'username', '') or ''
                    sent_to = f"{name} (@{username})" if username else name
                except Exception:
                    sent_to = str(chat_id)

            result = {
                "status": "success",
                "username": me.username or "",
                "phone": me.phone or "",
                "first_name": me.first_name or "",
                "message_id": sent_msg.id,
                "sent_to": sent_to,
                "test_message": test_message,
                "user_info": {
                    "username": me.username or "",
                    "first_name": me.first_name or "",
                    "phone": me.phone or "",
                },
            }

            return result

        except Exception as e:
            logger.error(f"Test connection failed for {messenger_id}: {e}")
            raise
        finally:
            if own_client:
                try:
                    await client.disconnect()
                except Exception:
                    pass


async def get_telegram_dialogs(
    messenger_id: str,
    creds: dict,
    limit: int = 50,
) -> list:
    """
    Get list of recent Telegram dialogs (contacts / chats / groups).
    Returns a list of dicts with id, name, username, type, unread_count.
    """
    api_id = int(creds["api_id"])
    api_hash = creds["api_hash"]
    session_file = _session_path(messenger_id)

    lock = _get_session_lock(messenger_id)
    async with lock:
        existing = _active_clients.get(messenger_id)
        client = existing["client"] if existing else TelegramClient(session_file, api_id, api_hash)
        own_client = not existing

        try:
            if own_client:
                await client.connect()

            if not await client.is_user_authorized():
                raise RuntimeError("Client not authenticated.")

            result = []
            async for dialog in client.iter_dialogs(limit=limit):
                entity = dialog.entity
                dtype = "user"
                if dialog.is_group:
                    dtype = "group"
                elif dialog.is_channel:
                    dtype = "channel"

                result.append({
                    "id": str(dialog.id),
                    "name": dialog.name or "",
                    "username": getattr(entity, 'username', '') or "",
                    "type": dtype,
                    "unread_count": dialog.unread_count,
                    "is_user": dialog.is_user,
                    "is_group": dialog.is_group,
                    "is_channel": dialog.is_channel,
                    "last_message": dialog.message.text[:100] if dialog.message and dialog.message.text else "",
                })

            return result

        except Exception as e:
            logger.error(f"Failed to get dialogs for {messenger_id}: {e}")
            raise
        finally:
            if own_client:
                try:
                    await client.disconnect()
                except Exception:
                    pass


async def send_telegram_message(
    messenger_id: str,
    creds: dict,
    recipient: str,
    message: str,
) -> dict:
    """
    Send a message to a specific Telegram user/chat.
    recipient can be: chat_id (numeric), @username, or phone number.
    Uses active client if available, otherwise creates a temporary connection.
    """
    api_id = int(creds["api_id"])
    api_hash = creds["api_hash"]
    session_file = _session_path(messenger_id)

    lock = _get_session_lock(messenger_id)
    async with lock:
        existing = _active_clients.get(messenger_id)
        client = existing["client"] if existing else TelegramClient(session_file, api_id, api_hash)
        own_client = not existing

        try:
            if own_client:
                await client.connect()

            if not await client.is_user_authorized():
                raise RuntimeError("Client not authenticated.")

            # Resolve recipient
            target = None
            if recipient.lstrip('-').isdigit():
                target = int(recipient)
            elif recipient.startswith("@"):
                target = recipient[1:]  # Remove @ for Telethon
            elif recipient.startswith("+"):
                target = recipient  # Phone number
            else:
                target = recipient  # try as-is (username without @)

            # Get entity for display name
            try:
                entity = await client.get_entity(target)
                name = getattr(entity, 'first_name', '') or getattr(entity, 'title', '') or str(target)
                username = getattr(entity, 'username', '') or ''
                display = f"{name} (@{username})" if username else name
            except Exception:
                entity = None
                display = str(recipient)

            # Send with typing indicator for realism
            try:
                if entity:
                    await client(SetTypingRequest(
                        peer=entity,
                        action=SendMessageTypingAction()
                    ))
                    # Brief typing delay
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass

            sent = await client.send_message(target, message)

            return {
                "status": "success",
                "message_id": sent.id,
                "sent_to": display,
                "chat_id": str(sent.chat_id) if hasattr(sent, 'chat_id') else str(target),
            }

        except Exception as e:
            logger.error(f"Failed to send message for {messenger_id}: {e}")
            raise
        finally:
            if own_client:
                try:
                    await client.disconnect()
                except Exception:
                    pass


async def submit_auth_code(messenger_id: str, code: str, phone_code_hash: str = None) -> dict:
    """Submit the verification code."""
    pending = _pending_auth.get(messenger_id)
    if not pending:
        return {"status": "error", "message": "No pending auth flow. Call /auth/start first."}

    client = pending["client"]
    phone = pending["phone"]
    pch = phone_code_hash or pending.get("phone_code_hash", "")

    try:
        await client.sign_in(phone, code, phone_code_hash=pch)
        me = await client.get_me()
        _pending_auth.pop(messenger_id, None)
        return {
            "status": "authenticated",
            "username": me.username or "",
            "phone": me.phone or "",
            "first_name": me.first_name or "",
        }
    except SessionPasswordNeededError:
        # 2FA needed
        return {"status": "2fa_required", "message": "Two-factor authentication password required."}
    except PhoneCodeInvalidError:
        return {"status": "error", "message": "Invalid verification code."}
    except Exception as e:
        logger.error(f"Auth code error for {messenger_id}: {e}")
        return {"status": "error", "message": str(e)}


async def submit_2fa_password(messenger_id: str, password: str) -> dict:
    """Submit 2FA password."""
    pending = _pending_auth.get(messenger_id)
    if not pending:
        return {"status": "error", "message": "No pending auth flow."}

    client = pending["client"]
    try:
        await client.sign_in(password=password)
        me = await client.get_me()
        _pending_auth.pop(messenger_id, None)
        return {
            "status": "authenticated",
            "username": me.username or "",
            "phone": me.phone or "",
            "first_name": me.first_name or "",
        }
    except Exception as e:
        logger.error(f"2FA error for {messenger_id}: {e}")
        return {"status": "error", "message": str(e)}


# ── Listener Management ─────────────────────────────────────────────────

async def start_telegram_listener(
    messenger_id: str,
    agent_id: str,
    creds: dict,
    account_doc: dict,
):
    """Start a Telegram client and register message handlers."""
    if messenger_id in _active_clients:
        logger.info(f"Telegram listener already active for {messenger_id}")
        return

    lock = _get_session_lock(messenger_id)
    async with lock:
        # Double-check after acquiring lock
        if messenger_id in _active_clients:
            logger.info(f"Telegram listener already active for {messenger_id} (after lock)")
            return

        # Disconnect any pending auth client for the same session
        pending = _pending_auth.pop(messenger_id, None)
        if pending and pending.get("client"):
            try:
                await pending["client"].disconnect()
            except Exception:
                pass

        api_id = int(creds["api_id"])
        api_hash = creds["api_hash"]
        session_file = _session_path(messenger_id)

        client = TelegramClient(session_file, api_id, api_hash)
        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Client not authenticated. Complete auth flow first.")

        me = await client.get_me()
        logger.info(f"Telegram listener started for {messenger_id} as @{me.username}")

        await _log_messenger_event(
            messenger_id, agent_id, "info", "listener_started",
            f"Telegram listener started as @{me.username or 'unknown'}",
            {"username": me.username, "phone": me.phone, "user_id": me.id},
        )

        # Config
        trusted_users = account_doc.get("trusted_users", [])
        public_permissions = account_doc.get("public_permissions", [])
        config = account_doc.get("config", {})
        delay_min = config.get("response_delay_min", 2)
        delay_max = config.get("response_delay_max", 8)
        typing_indicator = config.get("typing_indicator", True)
        humanize = config.get("humanize_responses", True)
        casual = config.get("casual_tone", True)
        respond_mentions = config.get("respond_to_mentions", True)
        respond_groups = config.get("respond_in_groups", False)
        max_daily = config.get("max_daily_messages", 100)
        context_messages_limit = config.get("context_messages_limit", None)  # None = use agent default

        # Store in registry (include creds + account_doc for auto-reconnect)
        _active_clients[messenger_id] = {
            "client": client,
            "agent_id": agent_id,
            "messenger_id": messenger_id,
            "me": me,
            "trusted_users": trusted_users,
            "public_permissions": public_permissions,
            "config": config,
            "daily_count": 0,
            "last_count_reset": datetime.now(timezone.utc).date(),
            "creds": creds,
            "account_doc": account_doc,
            "stop_requested": False,  # set True on intentional stop to prevent reconnect
            "reconnecting": False,  # set True while _run_client is in reconnect loop
        }

        @client.on(events.NewMessage(incoming=True))
        async def on_new_message(event):
            """Handle incoming Telegram messages."""
            try:
                await _handle_incoming_message(
                    event=event,
                    messenger_id=messenger_id,
                    agent_id=agent_id,
                    client=client,
                    me=me,
                    trusted_users=trusted_users,
                    public_permissions=public_permissions,
                    delay_min=delay_min,
                    delay_max=delay_max,
                    typing_indicator=typing_indicator,
                    humanize=humanize,
                    casual=casual,
                    respond_mentions=respond_mentions,
                    respond_groups=respond_groups,
                    max_daily=max_daily,
                    context_messages_limit=context_messages_limit,
                )
            except Exception as e:
                logger.error(f"Error handling Telegram message for {messenger_id}: {e}", exc_info=True)
                await _log_messenger_error(
                    messenger_id, agent_id,
                    "messenger_handler_error", f"Error handling incoming message: {e}",
                    {"exception": str(type(e).__name__), "detail": str(e)},
                )

    # Start receiving (outside lock — _run_client manages its own lock for reconnects)
    asyncio.create_task(_run_client(client, messenger_id))

    # Process unread messages that arrived while offline (in background)
    asyncio.create_task(_process_unread_messages(
        client=client,
        messenger_id=messenger_id,
        agent_id=agent_id,
        me=me,
        trusted_users=trusted_users,
        public_permissions=public_permissions,
        config=config,
        context_messages_limit=context_messages_limit,
    ))


async def _run_client(client: TelegramClient, messenger_id: str):
    """Keep client running with auto-reconnect on disconnect."""
    entry = _active_clients.get(messenger_id, {})
    agent_id = entry.get("agent_id", "")
    reconnect_delay = 5  # start at 5 seconds
    max_reconnect_delay = 300  # max 5 minutes
    max_reconnect_attempts = 50  # give up after this many consecutive failures
    attempt = 0

    while True:
        try:
            await client.run_until_disconnected()
        except Exception as e:
            logger.error(f"Telegram client {messenger_id} disconnected: {e}")
            await _log_messenger_error(
                messenger_id, agent_id,
                "messenger_disconnect", f"Telegram client disconnected with error: {e}",
                {"exception": str(e), "reconnect_attempt": attempt},
            )

        # Check if this was an intentional stop
        entry = _active_clients.get(messenger_id, {})
        if entry.get("stop_requested", False):
            logger.info(f"Telegram listener for {messenger_id} stopped (intentional)")
            _active_clients.pop(messenger_id, None)
            await _log_messenger_event(
                messenger_id, agent_id, "info", "listener_stopped",
                "Telegram listener stopped (intentional)",
            )
            return

        # Not intentional — try to reconnect
        entry["reconnecting"] = True
        attempt += 1
        if attempt > max_reconnect_attempts:
            logger.error(f"Telegram {messenger_id}: giving up after {max_reconnect_attempts} reconnect attempts")
            _active_clients.pop(messenger_id, None)
            await _log_messenger_error(
                messenger_id, agent_id,
                "reconnect_failed", f"Gave up reconnecting after {max_reconnect_attempts} attempts",
                {"attempts": max_reconnect_attempts},
            )
            return

        wait = min(reconnect_delay * (2 ** (attempt - 1)), max_reconnect_delay)
        # Add jitter ±20%
        wait = wait * (0.8 + random.random() * 0.4)
        logger.warning(f"Telegram {messenger_id}: reconnecting in {wait:.1f}s (attempt {attempt})")
        await _log_messenger_event(
            messenger_id, agent_id, "warning", "reconnecting",
            f"Connection lost. Reconnecting in {wait:.1f}s (attempt {attempt}/{max_reconnect_attempts})",
            {"attempt": attempt, "wait_seconds": round(wait, 1)},
        )
        await asyncio.sleep(wait)

        # Check again if stop was requested during the wait
        entry = _active_clients.get(messenger_id, {})
        if entry.get("stop_requested", False) or messenger_id not in _active_clients:
            _active_clients.pop(messenger_id, None)
            return

        new_client = None
        # Attempt reconnect — acquire lock to prevent concurrent session access
        lock = _get_session_lock(messenger_id)
        async with lock:
            try:
                creds = entry.get("creds", {})
                account_doc = entry.get("account_doc", {})
                api_id = int(creds["api_id"])
                api_hash = creds["api_hash"]
                session_file = _session_path(messenger_id)

                # Disconnect old client to release SQLite session lock
                try:
                    await client.disconnect()
                except Exception:
                    pass

                # Small delay to ensure SQLite lock is fully released
                await asyncio.sleep(0.5)

                # Create fresh client
                new_client = TelegramClient(session_file, api_id, api_hash)
                try:
                    await new_client.connect()
                except Exception:
                    # If connect fails, make sure to clean up the partial client
                    try:
                        await new_client.disconnect()
                    except Exception:
                        pass
                    raise

                if not await new_client.is_user_authorized():
                    logger.error(f"Telegram {messenger_id}: session expired during reconnect")
                    await _log_messenger_error(
                        messenger_id, agent_id,
                        "reconnect_auth_failed", "Session expired — re-authentication required",
                        {"attempt": attempt},
                    )
                    try:
                        await new_client.disconnect()
                    except Exception:
                        pass
                    _active_clients.pop(messenger_id, None)
                    return

                me = await new_client.get_me()
                logger.info(f"Telegram {messenger_id}: reconnected as @{me.username} (attempt {attempt})")

                # Re-read config for reconnect
                trusted_users = account_doc.get("trusted_users", [])
                public_permissions = account_doc.get("public_permissions", [])
                config = account_doc.get("config", {})
                delay_min = config.get("response_delay_min", 2)
                delay_max = config.get("response_delay_max", 8)
                typing_indicator = config.get("typing_indicator", True)
                humanize = config.get("humanize_responses", True)
                casual = config.get("casual_tone", True)
                respond_mentions = config.get("respond_to_mentions", True)
                respond_groups = config.get("respond_in_groups", False)
                max_daily = config.get("max_daily_messages", 100)
                context_messages_limit = config.get("context_messages_limit", None)

                # Update registry with new client
                old_daily = entry.get("daily_count", 0)
                old_reset = entry.get("last_count_reset")
                _active_clients[messenger_id] = {
                    "client": new_client,
                    "agent_id": agent_id,
                    "messenger_id": messenger_id,
                    "me": me,
                    "trusted_users": trusted_users,
                    "public_permissions": public_permissions,
                    "config": config,
                    "daily_count": old_daily,
                    "last_count_reset": old_reset,
                    "creds": creds,
                    "account_doc": account_doc,
                    "stop_requested": False,
                }

                # Re-register handler
                @new_client.on(events.NewMessage(incoming=True))
                async def on_new_message(event):
                    try:
                        await _handle_incoming_message(
                            event=event,
                            messenger_id=messenger_id,
                            agent_id=agent_id,
                            client=new_client,
                            me=me,
                            trusted_users=trusted_users,
                            public_permissions=public_permissions,
                            delay_min=delay_min,
                            delay_max=delay_max,
                            typing_indicator=typing_indicator,
                            humanize=humanize,
                            casual=casual,
                            respond_mentions=respond_mentions,
                            respond_groups=respond_groups,
                            max_daily=max_daily,
                            context_messages_limit=context_messages_limit,
                        )
                    except Exception as e:
                        logger.error(f"Error handling Telegram message for {messenger_id}: {e}", exc_info=True)

                client = new_client  # use new client for next iteration
                attempt = 0  # reset counter on successful reconnect
                reconnect_delay = 5
                entry = _active_clients.get(messenger_id, {})
                entry["reconnecting"] = False

                await _log_messenger_event(
                    messenger_id, agent_id, "info", "reconnected",
                    f"Successfully reconnected as @{me.username} after {attempt} attempt(s)",
                    {"username": me.username, "attempt": attempt},
                )

                # Process unread messages that arrived while offline
                asyncio.create_task(_process_unread_messages(
                    client=new_client,
                    messenger_id=messenger_id,
                    agent_id=agent_id,
                    me=me,
                    trusted_users=trusted_users,
                    public_permissions=public_permissions,
                    config=config,
                    context_messages_limit=context_messages_limit,
                ))

            except Exception as e:
                # Disconnect failed new_client to release SQLite session lock
                if new_client:
                    try:
                        await new_client.disconnect()
                    except Exception:
                        pass
                    new_client = None
                logger.error(f"Telegram {messenger_id}: reconnect attempt {attempt} failed: {e}")
                await _log_messenger_error(
                    messenger_id, agent_id,
                    "reconnect_error", f"Reconnect attempt {attempt} failed: {e}",
                    {"attempt": attempt, "exception": str(e)},
                )
                # Will loop back and try again after increasing delay


async def stop_telegram_client(messenger_id: str):
    """Stop and disconnect a Telegram client."""
    entry = _active_clients.get(messenger_id)
    if entry:
        entry["stop_requested"] = True  # signal reconnect loop to stop
        if entry.get("client"):
            try:
                await entry["client"].disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting Telegram client {messenger_id}: {e}")
        _active_clients.pop(messenger_id, None)

    # Also clean up pending auth
    pending = _pending_auth.pop(messenger_id, None)
    if pending and pending.get("client"):
        try:
            await pending["client"].disconnect()
        except Exception:
            pass


async def stop_all_clients():
    """Stop all active Telegram clients (for shutdown)."""
    for mid in list(_active_clients.keys()):
        await stop_telegram_client(mid)


def get_active_clients() -> Dict[str, Any]:
    """Return info about active clients."""
    return {
        mid: {
            "agent_id": entry["agent_id"],
            "username": entry["me"].username if entry.get("me") else "",
            "daily_count": entry.get("daily_count", 0),
        }
        for mid, entry in _active_clients.items()
    }


# ── Media helpers ────────────────────────────────────────────────────────

def _detect_media_type(event) -> str | None:
    """Detect what kind of media a Telegram message contains.
    Returns: voice, audio, photo, video, video_note, document, sticker, or None.
    """
    msg = event.message
    if not msg or not msg.media:
        return None

    from telethon.tl.types import (
        MessageMediaPhoto, MessageMediaDocument,
        DocumentAttributeAudio, DocumentAttributeVideo,
        DocumentAttributeSticker, DocumentAttributeAnimated,
    )

    if isinstance(msg.media, MessageMediaPhoto):
        return "photo"

    if isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        if not doc:
            return "document"
        attrs = doc.attributes or []
        for attr in attrs:
            if isinstance(attr, DocumentAttributeAudio):
                return "voice" if attr.voice else "audio"
            if isinstance(attr, DocumentAttributeSticker):
                return "sticker"
            if isinstance(attr, DocumentAttributeAnimated):
                return "sticker"
            if isinstance(attr, DocumentAttributeVideo):
                return "video_note" if attr.round_message else "video"
        # Generic document (PDF, ZIP, etc.)
        return "document"

    return None


def _get_media_ext(media_type: str, event) -> str:
    """Get a reasonable file extension based on media type."""
    if media_type == "voice":
        return "ogg"
    if media_type == "audio":
        return "mp3"
    if media_type == "photo":
        return "jpg"
    if media_type in ("video", "video_note"):
        return "mp4"
    if media_type == "sticker":
        return "webp"
    # For documents, try to get original filename extension
    if media_type == "document" and event.message and event.message.media:
        try:
            from telethon.tl.types import DocumentAttributeFilename
            doc = event.message.media.document
            for attr in (doc.attributes or []):
                if isinstance(attr, DocumentAttributeFilename):
                    name = attr.file_name or ""
                    if "." in name:
                        return name.rsplit(".", 1)[-1].lower()
        except Exception:
            pass
    return "bin"


def _get_original_filename(event) -> str | None:
    """Try to extract original filename from document attributes."""
    try:
        from telethon.tl.types import DocumentAttributeFilename
        doc = event.message.media.document
        for attr in (doc.attributes or []):
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name
    except Exception:
        pass
    return None


def _get_media_mime(event) -> str | None:
    """Try to get MIME type from document."""
    try:
        return event.message.media.document.mime_type
    except Exception:
        return None


async def _download_telegram_media(client: TelegramClient, event, media_type: str) -> tuple[str, str, str | None]:
    """Download media from a Telegram message to local storage.
    Returns: (local_filename, media_url, original_filename)
    """
    ext = _get_media_ext(media_type, event)
    local_filename = f"{uuid.uuid4().hex}.{ext}"
    local_path = CHAT_MEDIA_DIR / local_filename
    original_filename = _get_original_filename(event)

    await client.download_media(event.message, file=str(local_path))

    media_url = f"/api/uploads/chat_media/{local_filename}"
    return local_filename, media_url, original_filename


async def _transcribe_voice(db, audio_path: Path, audio_format: str = "ogg") -> str:
    """Transcribe a voice/audio file via STT service."""
    try:
        from app.services.audio_service import speech_to_text
        audio_data = audio_path.read_bytes()
        logger.info(f"STT: transcribing {audio_path.name} ({len(audio_data)} bytes, format={audio_format})")
        result = await speech_to_text(db=db, audio_data=audio_data, audio_format=audio_format)
        text = result.get("text", "")
        logger.info(f"STT result: {len(text)} chars, text={text[:100]}")
        return text
    except Exception as e:
        logger.error(f"STT transcription failed: {type(e).__name__}: {e}")
        return ""


# ── Process Unread Messages (on connect / reconnect) ────────────────────

class _MessageAsEvent:
    """
    Thin wrapper around a Telethon Message so it can be passed to
    _handle_incoming_message and media helpers that expect event.message,
    event.chat_id, event.raw_text, etc.
    """
    def __init__(self, msg):
        self._msg = msg

    # The helpers access event.message to get the Message object
    @property
    def message(self):
        return self._msg

    # Forward everything else to the underlying Message
    def __getattr__(self, name):
        return getattr(self._msg, name)


async def _process_unread_messages(
    client: TelegramClient,
    messenger_id: str,
    agent_id: str,
    me,
    trusted_users: list,
    public_permissions: list,
    config: dict,
    context_messages_limit: int | None = None,
):
    """
    After connecting (or reconnecting), iterate through dialogs with unread
    messages and process each one sequentially — so the agent replies to
    messages that arrived while it was offline.
    """
    delay_min = config.get("response_delay_min", 2)
    delay_max = config.get("response_delay_max", 8)
    typing_indicator = config.get("typing_indicator", True)
    humanize = config.get("humanize_responses", True)
    casual = config.get("casual_tone", True)
    respond_mentions = config.get("respond_to_mentions", True)
    respond_groups = config.get("respond_in_groups", False)
    max_daily = config.get("max_daily_messages", 100)

    total_processed = 0
    MAX_UNREAD_DIALOGS = 20   # limit how many chats to process
    MAX_UNREAD_PER_CHAT = 10  # limit messages per chat to avoid huge backlogs

    try:
        dialog_count = 0
        async for dialog in client.iter_dialogs():
            if dialog.unread_count <= 0:
                continue

            # Check stop_requested between dialogs
            entry = _active_clients.get(messenger_id, {})
            if entry.get("stop_requested"):
                break

            dialog_count += 1
            if dialog_count > MAX_UNREAD_DIALOGS:
                logger.info(f"Unread catchup: hit max dialog limit ({MAX_UNREAD_DIALOGS})")
                break

            is_group = dialog.is_group or dialog.is_channel
            is_private = not is_group

            # Skip groups if not configured to respond
            if is_group and not respond_groups:
                continue

            chat_id = dialog.id
            unread_count = min(dialog.unread_count, MAX_UNREAD_PER_CHAT)

            logger.info(
                f"Unread catchup: {messenger_id} — dialog {dialog.name or chat_id} "
                f"has {dialog.unread_count} unread (processing up to {unread_count})"
            )

            # Fetch the unread messages (oldest first)
            try:
                messages = await client.get_messages(chat_id, limit=unread_count)
                messages.reverse()  # oldest first
            except Exception as e:
                logger.warning(f"Unread catchup: failed to get messages from {chat_id}: {e}")
                continue

            for msg in messages:
                # Skip our own messages
                if msg.sender_id == me.id:
                    continue
                # Skip empty
                if not msg.text and not msg.media:
                    continue

                try:
                    # Wrap Message in _MessageAsEvent so event.message returns
                    # the Message object (matching NewMessage event behaviour)
                    wrapped = _MessageAsEvent(msg)
                    await _handle_incoming_message(
                        event=wrapped,
                        messenger_id=messenger_id,
                        agent_id=agent_id,
                        client=client,
                        me=me,
                        trusted_users=trusted_users,
                        public_permissions=public_permissions,
                        delay_min=delay_min,
                        delay_max=delay_max,
                        typing_indicator=typing_indicator,
                        humanize=humanize,
                        casual=casual,
                        respond_mentions=respond_mentions,
                        respond_groups=respond_groups,
                        max_daily=max_daily,
                        context_messages_limit=context_messages_limit,
                    )
                    total_processed += 1
                except Exception as e:
                    logger.error(
                        f"Unread catchup: error processing message {msg.id} "
                        f"in chat {chat_id}: {e}", exc_info=True,
                    )

                # Small gap between messages to avoid flooding
                await asyncio.sleep(1)

        if total_processed > 0:
            await _log_messenger_event(
                messenger_id, agent_id, "info", "unread_catchup_done",
                f"Processed {total_processed} unread message(s) after connect",
                {"total_processed": total_processed, "dialogs_checked": dialog_count},
            )
            logger.info(f"Unread catchup: {messenger_id} processed {total_processed} messages from {dialog_count} dialogs")
        else:
            logger.info(f"Unread catchup: {messenger_id} — no unread messages to process")

    except Exception as e:
        logger.error(f"Unread catchup error for {messenger_id}: {e}", exc_info=True)
        await _log_messenger_error(
            messenger_id, agent_id,
            "unread_catchup_error", f"Failed to process unread messages: {e}",
            {"exception": type(e).__name__, "detail": str(e)},
        )


# ── Message Handler ──────────────────────────────────────────────────────

async def _handle_incoming_message(
    event,
    messenger_id: str,
    agent_id: str,
    client: TelegramClient,
    me,
    trusted_users: list,
    public_permissions: list,
    delay_min: int,
    delay_max: int,
    typing_indicator: bool,
    humanize: bool,
    casual: bool,
    respond_mentions: bool,
    respond_groups: bool,
    max_daily: int,
    context_messages_limit: int | None = None,
):
    """Process an incoming Telegram message."""
    from app.database import get_mongodb
    db = get_mongodb()

    sender = await event.get_sender()
    if not sender:
        return

    # Skip our own messages
    if sender.id == me.id:
        return

    is_group = event.is_group or event.is_channel
    is_private = event.is_private

    # In groups: only respond if mentioned or if configured
    if is_group and not respond_groups:
        # Check if mentioned
        if respond_mentions and me.username:
            if f"@{me.username}" not in (event.raw_text or ""):
                return
        else:
            return

    # Check daily limit
    entry = _active_clients.get(messenger_id)
    if entry:
        today = datetime.now(timezone.utc).date()
        if entry.get("last_count_reset") != today:
            entry["daily_count"] = 0
            entry["last_count_reset"] = today
        if entry["daily_count"] >= max_daily:
            logger.warning(f"Daily message limit reached for {messenger_id}")
            await _log_messenger_event(
                messenger_id, agent_id, "warning",
                "daily_limit_reached", f"Daily limit of {max_daily} messages reached",
                {"limit": max_daily, "count": entry['daily_count']},
            )
            return

    # Determine if trusted user
    sender_username = f"@{sender.username}" if sender.username else ""
    sender_id_str = str(sender.id)
    is_trusted = (
        sender_username in trusted_users
        or sender_id_str in trusted_users
        or f"user_id:{sender.id}" in trusted_users
    )

    message_text = event.raw_text or ""
    media_type = _detect_media_type(event)
    media_url = None
    media_filename = None
    media_mime = None

    # ── Handle media (voice, audio, photo, video, document, sticker, video_note) ──
    if media_type:
        try:
            local_filename, media_url, original_filename = await _download_telegram_media(client, event, media_type)
            media_filename = original_filename or local_filename
            media_mime = _get_media_mime(event)

            await _log_messenger_event(
                messenger_id, agent_id, "debug",
                "media_received", f"Downloaded {media_type}: {local_filename}",
                {"chat_id": str(event.chat_id), "media_type": media_type, "filename": media_filename},
            )

            # Voice/audio → transcribe via STT, use as message text
            if media_type in ("voice", "audio"):
                ext = "ogg" if media_type == "voice" else "mp3"
                local_path = CHAT_MEDIA_DIR / local_filename
                transcribed = await _transcribe_voice(db, local_path, ext)
                if transcribed:
                    # Use transcribed text directly as message content
                    # The user spoke these words — treat as if they typed them
                    caption = message_text.strip()
                    if caption:
                        message_text = f"{caption}\n\n{transcribed}"
                    else:
                        message_text = transcribed
                    await _log_messenger_event(
                        messenger_id, agent_id, "info",
                        "voice_transcribed", f"STT result: {len(transcribed)} chars",
                        {"chat_id": str(event.chat_id), "text_preview": transcribed[:200]},
                    )
                elif not message_text.strip():
                    message_text = "[Пользователь отправил голосовое сообщение, но распознать его не удалось. Попросите повторить текстом.]"

            # Photo → describe
            elif media_type == "photo":
                if not message_text.strip():
                    message_text = "[Фотография]"
                else:
                    message_text = f"[Фотография] {message_text}"

            # Video / video_note
            elif media_type in ("video", "video_note"):
                label = "Видео" if media_type == "video" else "Видеосообщение"
                if not message_text.strip():
                    message_text = f"[{label}]"
                else:
                    message_text = f"[{label}] {message_text}"

            # Sticker
            elif media_type == "sticker":
                if not message_text.strip():
                    message_text = "[Стикер]"

            # Document
            elif media_type == "document":
                name_part = f": {media_filename}" if media_filename else ""
                if not message_text.strip():
                    message_text = f"[Документ{name_part}]"
                else:
                    message_text = f"[Документ{name_part}] {message_text}"

        except Exception as e:
            logger.error(f"Error downloading media for {messenger_id}: {e}")
            await _log_messenger_event(
                messenger_id, agent_id, "error",
                "media_download_error", f"Failed to download {media_type}: {e}",
                {"chat_id": str(event.chat_id), "error": str(e)},
            )
            if not message_text.strip():
                message_text = f"[{media_type} — ошибка загрузки]"

    # Skip completely empty messages (no text AND no media)
    if not message_text.strip():
        return

    # Log incoming message
    from app.mongodb.services import MessengerMessageService
    msg_svc = MessengerMessageService(db)
    incoming_msg = MongoMessengerMessage(
        messenger_id=messenger_id,
        agent_id=agent_id,
        platform_message_id=str(event.id),
        chat_id=str(event.chat_id),
        user_id=sender_id_str,
        username=sender.username or "",
        display_name=getattr(sender, 'first_name', '') or "",
        direction="incoming",
        content=message_text,
        media_type=media_type,
        media_url=media_url,
        media_filename=media_filename,
        media_mime=media_mime,
        is_command=is_trusted,
        is_trusted_user=is_trusted,
    )
    await msg_svc.create(incoming_msg)

    await _log_messenger_event(
        messenger_id, agent_id, "debug",
        "message_received", f"Incoming message from {sender.username or sender_id_str}",
        {"chat_id": str(event.chat_id), "user_id": sender_id_str, "is_trusted": is_trusted, "length": len(message_text)},
    )

    # --- Mark messages as read BEFORE starting to type (natural human behavior) ---
    try:
        await client.send_read_acknowledge(event.chat_id, event.message)
    except Exception as e:
        logger.debug(f"Failed to mark messages as read for {messenger_id}: {e}")

    # --- Start typing indicator IMMEDIATELY (within 3 sec of receiving message) ---
    typing_task = None
    if typing_indicator:
        async def _keep_typing():
            """Continuously send typing indicator every 5s (Telegram expires it after ~6s)."""
            try:
                while True:
                    try:
                        await client(SetTypingRequest(
                            peer=event.chat_id,
                            action=SendMessageTypingAction()
                        ))
                    except Exception:
                        pass
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(_keep_typing())

    # Generate response via agent (typing indicator is already showing)
    try:
        response_text = await _generate_agent_response(
            db=db,
            agent_id=agent_id,
            messenger_id=messenger_id,
            message_text=message_text,
            sender_username=sender.username or sender_id_str,
            is_trusted=is_trusted,
            public_permissions=public_permissions,
            humanize=humanize,
            casual=casual,
            chat_id=str(event.chat_id),
            context_messages_limit=context_messages_limit,
        )
    except Exception:
        if typing_task:
            typing_task.cancel()
        raise

    if not response_text:
        if typing_task:
            typing_task.cancel()
        await _log_messenger_event(
            messenger_id, agent_id, "warning",
            "no_response", f"LLM returned no response for message from {sender.username or sender_id_str}",
            {"chat_id": str(event.chat_id), "user_id": sender_id_str, "message_preview": message_text[:100]},
        )
        return

    # Calculate realistic typing delay based on response length
    # ~40 chars/sec typing speed with some randomness
    typing_time = len(response_text) / random.uniform(30, 50)
    delay = max(delay_min, min(delay_max, typing_time))
    delay = random.uniform(delay * 0.8, delay * 1.2)
    delay = max(delay_min, min(delay_max, delay))
    await asyncio.sleep(delay)

    # Cancel the typing indicator loop before sending
    if typing_task:
        typing_task.cancel()

    # Send response
    try:
        await event.reply(response_text)
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        await _log_messenger_error(
            messenger_id, agent_id,
            "message_send_error", f"Failed to send reply: {e}",
            {"chat_id": str(event.chat_id), "error": str(e)},
        )
        return

    # Log outgoing message
    outgoing_msg = MongoMessengerMessage(
        messenger_id=messenger_id,
        agent_id=agent_id,
        chat_id=str(event.chat_id),
        user_id=str(me.id),
        username=me.username or "",
        display_name=me.first_name or "",
        direction="outgoing",
        content=response_text,
        is_command=False,
        is_trusted_user=False,
        response_id=incoming_msg.id,
    )
    await msg_svc.create(outgoing_msg)

    await _log_messenger_event(
        messenger_id, agent_id, "info",
        "message_sent", f"Replied to {sender.username or sender_id_str}",
        {"chat_id": str(event.chat_id), "response_length": len(response_text)},
    )

    # Update daily count
    if entry:
        entry["daily_count"] = entry.get("daily_count", 0) + 1

    # Update last_active_at
    from app.mongodb.services import MessengerAccountService
    acc_svc = MessengerAccountService(db)
    await acc_svc.update(messenger_id, {
        "last_active_at": datetime.now(timezone.utc).isoformat(),
    })


# Need import at module level for MongoMessengerMessage
from app.mongodb.models.messenger import MongoMessengerMessage


async def _generate_agent_response(
    db,
    agent_id: str,
    messenger_id: str,
    message_text: str,
    sender_username: str,
    is_trusted: bool,
    public_permissions: list,
    humanize: bool,
    casual: bool,
    chat_id: str,
    context_messages_limit: int | None = None,
) -> Optional[str]:
    """Call the agent's LLM via AgentChatEngine.generate_full() with full context + thinking log."""
    from app.mongodb.services import MessengerMessageService, AgentService
    from app.services.agent_chat_engine import AgentChatEngine

    engine = AgentChatEngine(db)

    # ── Build messenger-specific context ──
    messenger_context = ""
    if is_trusted:
        messenger_context = (
            f"\n\n[MESSENGER CONTEXT] "
            f"You are chatting in Telegram. The user @{sender_username} is a TRUSTED user. "
            f"You can execute commands and use all your skills. Respond helpfully. "
            f"Keep responses concise — this is a messenger, not a document."
        )
    else:
        perm_str = ", ".join(public_permissions) if public_permissions else "general conversation"
        human_note = ""
        if humanize:
            human_note = " Respond naturally, like a real human would — use casual language, occasional emoji. "
        if casual:
            human_note += " Keep it brief and conversational."
        messenger_context = (
            f"\n\n[MESSENGER CONTEXT] "
            f"You are chatting in Telegram as a regular person. "
            f"The user @{sender_username} is a regular user. "
            f"Your allowed capabilities: {perm_str}. "
            f"Do NOT reveal you are an AI agent. Do NOT execute privileged commands."
            f"{human_note}"
        )

    # ── Conversation history from messenger messages ──
    # Determine context limit before loading agent (use a sensible default)
    effective_limit = context_messages_limit
    if effective_limit is None:
        # Try to get agent's messenger_context_limit
        try:
            agent_svc = AgentService(db)
            agent = await agent_svc.get_by_id(agent_id)
            effective_limit = getattr(agent, 'messenger_context_limit', None) or 10
        except Exception:
            effective_limit = 10
    effective_limit = max(1, min(effective_limit, 100))

    msg_svc = MessengerMessageService(db)
    recent = await msg_svc.get_by_chat(messenger_id, chat_id, limit=effective_limit)
    recent.reverse()  # oldest first

    # Build history (exclude current message — generate_full adds it as user_input)
    history = []
    for m in recent[:-1]:
        role = "assistant" if m.direction == "outgoing" else "user"
        history.append({"role": role, "content": m.content})

    # ── Generate via engine.generate_full() — full context + thinking log ──
    max_skills = 5 if is_trusted else 0

    try:
        logger.info(
            f"Calling AgentChatEngine.generate_full() for messenger {messenger_id} "
            f"(trusted={is_trusted}, chat_id={chat_id})"
        )
        result = await engine.generate_full(
            agent_id=agent_id,
            user_input=message_text,
            history=history,
            session_id=f"tg:{messenger_id}:{chat_id}",
            extra_context=messenger_context,
            load_protocols=is_trusted,
            load_skills=is_trusted,
            load_beliefs=is_trusted,
            load_aspirations=is_trusted,
            max_skill_iterations=max_skills,
            enable_thinking_log=True,
        )
        if not result.content:
            logger.warning(f"Engine returned empty content for messenger {messenger_id}")
            return None

        return result.content

    except Exception as e:
        logger.error(f"Engine error for messenger {messenger_id}: {e}", exc_info=True)
        await _log_messenger_error(
            messenger_id, agent_id,
            "llm_error", f"LLM call failed: {e}",
            {"exception": type(e).__name__, "detail": str(e)},
        )
        return None


# ═══════════════════════════════════════════════════════════════════════
# Startup Restore & Health-Check Watchdog
# ═══════════════════════════════════════════════════════════════════════

_telegram_watchdog_task: Optional[asyncio.Task] = None
TELEGRAM_WATCHDOG_INTERVAL = 15  # seconds — Telegram tolerates reconnects every 10-20s


async def restore_active_clients():
    """
    On server startup: find all messenger accounts with is_active=True
    and is_authenticated=True, and start their Telegram listeners.
    """
    try:
        from app.database import get_mongodb
        from app.core.encryption import decrypt_dict
        from app.mongodb.services import MessengerAccountService

        db = get_mongodb()
        svc = MessengerAccountService(db)
        active_accounts = await svc.get_active(platform="telegram")

        if not active_accounts:
            logger.info("No active Telegram accounts to restore")
            return 0

        restored = 0
        for acc in active_accounts:
            messenger_id = acc.id
            agent_id = acc.agent_id

            # Skip if already running
            if messenger_id in _active_clients:
                continue

            # Get raw doc for encrypted creds
            raw_doc = await svc.collection.find_one({"_id": messenger_id})
            if not raw_doc:
                continue

            encrypted = raw_doc.get("credentials_encrypted", "")
            if not encrypted:
                logger.warning(f"Restore skip {messenger_id}: no encrypted creds")
                continue

            try:
                creds = decrypt_dict(encrypted)
            except Exception as e:
                logger.warning(f"Restore skip {messenger_id}: decrypt failed: {e}")
                continue

            try:
                await start_telegram_listener(messenger_id, agent_id, creds, raw_doc)
                restored += 1
                logger.info(f"Restored Telegram listener for {messenger_id}")
            except Exception as e:
                logger.error(f"Failed to restore Telegram listener {messenger_id}: {e}")
                await _log_messenger_error(
                    messenger_id, agent_id,
                    "restore_failed", f"Failed to restore listener on startup: {e}",
                    {"exception": type(e).__name__, "detail": str(e)},
                )

        if restored:
            from app.services.log_service import syslog_bg
            await syslog_bg(
                "info",
                f"Restored {restored} Telegram listener(s) on startup",
                source="telegram",
                metadata={"restored": restored, "total_active": len(active_accounts)},
            )
        return restored

    except Exception as e:
        logger.error(f"Failed to restore Telegram clients: {e}", exc_info=True)
        return 0


async def _telegram_watchdog_loop():
    """
    Periodic health check: every 15s, verify that all accounts marked as
    is_active=True in DB actually have a running client.  If not — restart.
    """
    await asyncio.sleep(10)  # initial grace period after startup

    while True:
        try:
            await asyncio.sleep(TELEGRAM_WATCHDOG_INTERVAL)
            await _check_telegram_health()
        except asyncio.CancelledError:
            logger.info("Telegram watchdog cancelled")
            return
        except Exception as e:
            logger.error(f"Telegram watchdog error: {e}", exc_info=True)
            await asyncio.sleep(5)


async def _check_telegram_health():
    """Single health-check iteration."""
    from app.database import get_mongodb
    from app.core.encryption import decrypt_dict
    from app.mongodb.services import MessengerAccountService

    db = get_mongodb()
    svc = MessengerAccountService(db)
    active_accounts = await svc.get_active(platform="telegram")

    for acc in active_accounts:
        messenger_id = acc.id
        agent_id = acc.agent_id

        entry = _active_clients.get(messenger_id)

        # Case 1: No entry at all — client dropped completely
        if not entry:
            logger.warning(f"Watchdog: {messenger_id} marked active but no client — restoring")
            raw_doc = await svc.collection.find_one({"_id": messenger_id})
            if not raw_doc:
                continue

            encrypted = raw_doc.get("credentials_encrypted", "")
            if not encrypted:
                continue

            try:
                creds = decrypt_dict(encrypted)
                await start_telegram_listener(messenger_id, agent_id, creds, raw_doc)
                logger.info(f"Watchdog: restored listener for {messenger_id}")
                await _log_messenger_event(
                    messenger_id, agent_id, "info", "watchdog_restored",
                    "Telegram listener restored by health-check watchdog",
                )
            except Exception as e:
                logger.error(f"Watchdog: failed to restore {messenger_id}: {e}")
                await _log_messenger_error(
                    messenger_id, agent_id,
                    "watchdog_restore_failed",
                    f"Health-check watchdog failed to restore: {e}",
                    {"exception": type(e).__name__},
                )
            continue

        # Case 2: Entry exists but client is disconnected
        client = entry.get("client")
        if client and not client.is_connected():
            if entry.get("reconnecting"):
                # _run_client reconnect loop is already handling this — don't interfere
                continue
            logger.warning(f"Watchdog: {messenger_id} client exists but disconnected — will let _run_client handle it")
            # _run_client loop should handle reconnection
            # Only intervene if the entry has no running task (shouldn't happen normally)

    # Also check for orphaned active_clients that are no longer in DB
    for messenger_id in list(_active_clients.keys()):
        found = any(acc.id == messenger_id for acc in active_accounts)
        if not found:
            entry = _active_clients.get(messenger_id, {})
            if not entry.get("stop_requested"):
                logger.info(f"Watchdog: {messenger_id} active in memory but not in DB — stopping")
                entry["stop_requested"] = True
                try:
                    client = entry.get("client")
                    if client:
                        await client.disconnect()
                except Exception:
                    pass
                _active_clients.pop(messenger_id, None)


async def start_telegram_watchdog():
    """Start the Telegram health-check watchdog."""
    global _telegram_watchdog_task
    if _telegram_watchdog_task and not _telegram_watchdog_task.done():
        return
    _telegram_watchdog_task = asyncio.create_task(_telegram_watchdog_loop())
    logger.info("Telegram watchdog started (interval=%ds)", TELEGRAM_WATCHDOG_INTERVAL)


async def stop_telegram_watchdog():
    """Stop the Telegram health-check watchdog."""
    global _telegram_watchdog_task
    if _telegram_watchdog_task and not _telegram_watchdog_task.done():
        _telegram_watchdog_task.cancel()
        try:
            await _telegram_watchdog_task
        except asyncio.CancelledError:
            pass
    _telegram_watchdog_task = None
    logger.info("Telegram watchdog stopped")
