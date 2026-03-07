"""Telegram integration service — Telethon client management, auth flow, message handling."""
import asyncio
import logging
import os
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Global client registry ───────────────────────────────────────────────
# messenger_id -> { client, agent_id, config, trusted_users, ... }
_active_clients: Dict[str, Dict[str, Any]] = {}

# Pending auth flows: messenger_id -> { client, phone_code_hash }
_pending_auth: Dict[str, Dict[str, Any]] = {}


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
    session_file = _session_path(messenger_id)

    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
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

    # Check if we already have an active client
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

    api_id = int(creds["api_id"])
    api_hash = creds["api_hash"]
    session_file = _session_path(messenger_id)

    client = TelegramClient(session_file, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
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

    # Start receiving
    asyncio.create_task(_run_client(client, messenger_id))


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

        # Attempt reconnect
        try:
            creds = entry.get("creds", {})
            account_doc = entry.get("account_doc", {})
            api_id = int(creds["api_id"])
            api_hash = creds["api_hash"]
            session_file = _session_path(messenger_id)

            # Create fresh client
            new_client = TelegramClient(session_file, api_id, api_hash)
            await new_client.connect()

            if not await new_client.is_user_authorized():
                logger.error(f"Telegram {messenger_id}: session expired during reconnect")
                await _log_messenger_error(
                    messenger_id, agent_id,
                    "reconnect_auth_failed", "Session expired — re-authentication required",
                    {"attempt": attempt},
                )
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

            await _log_messenger_event(
                messenger_id, agent_id, "info", "reconnected",
                f"Successfully reconnected as @{me.username} after {attempt} attempt(s)",
                {"username": me.username, "attempt": attempt},
            )

        except Exception as e:
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
        is_command=is_trusted,
        is_trusted_user=is_trusted,
    )
    await msg_svc.create(incoming_msg)

    await _log_messenger_event(
        messenger_id, agent_id, "debug",
        "message_received", f"Incoming message from {sender.username or sender_id_str}",
        {"chat_id": str(event.chat_id), "user_id": sender_id_str, "is_trusted": is_trusted, "length": len(message_text)},
    )

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
    """Call the agent's LLM via AgentChatEngine with full orchestrator support."""
    from app.mongodb.services import MessengerMessageService
    from app.services.agent_chat_engine import AgentChatEngine

    engine = AgentChatEngine(db)

    # ── Load agent context ──
    try:
        ctx = await engine.load_agent_context(
            agent_id,
            load_protocols=is_trusted,
            load_skills=is_trusted,
            load_beliefs=is_trusted,
            load_aspirations=is_trusted,
        )
    except ValueError as e:
        logger.error(f"Agent context load failed for messenger {messenger_id}: {e}")
        return None

    # ── Build messenger-specific system prompt ──
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

    if ctx.protocols and is_trusted:
        system_prompt = engine.build_system_prompt(ctx, extra_context=messenger_context)
    else:
        system_prompt = (ctx.base_system_prompt or "") + messenger_context

    # ── Conversation history from messenger messages ──
    effective_limit = context_messages_limit
    if effective_limit is None:
        effective_limit = getattr(ctx.agent, 'messenger_context_limit', None) or 10
    effective_limit = max(1, min(effective_limit, 100))

    msg_svc = MessengerMessageService(db)
    recent = await msg_svc.get_by_chat(messenger_id, chat_id, limit=effective_limit)
    recent.reverse()  # oldest first

    messages = [{"role": "system", "content": system_prompt}]
    for m in recent[:-1]:  # exclude the current message (already logged)
        role = "assistant" if m.direction == "outgoing" else "user"
        messages.append({"role": role, "content": m.content})
    messages.append({"role": "user", "content": message_text})

    # ── Generate via engine ──
    max_skills = 5 if is_trusted else 0

    try:
        logger.info(
            f"Calling AgentChatEngine for messenger {messenger_id} "
            f"(protocols={len(ctx.protocols)}, skills={len(ctx.skills)})"
        )
        result = await engine.generate(
            messages=messages,
            agent_context=ctx,
            max_skill_iterations=max_skills,
            parse_protocols=is_trusted,
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
