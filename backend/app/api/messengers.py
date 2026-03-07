"""Messenger integration API — manage messenger accounts for agents."""
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.core.encryption import encrypt_dict, decrypt_dict
from app.mongodb.models.messenger import MongoMessengerAccount, MongoMessengerMessage, MongoMessengerLog
from app.mongodb.services import MessengerAccountService, MessengerMessageService, MessengerLogService, AgentService, AgentErrorService
from app.mongodb.models.agent import MongoAgentError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents/{agent_id}/messengers", tags=["messengers"])


# ── Schemas ──────────────────────────────────────────────────────────────

class MessengerCredentials(BaseModel):
    api_id: str = ""
    api_hash: str = ""
    phone: str = ""
    session_name: str = ""


class MessengerConfig(BaseModel):
    response_delay_min: int = 2
    response_delay_max: int = 8
    typing_indicator: bool = True
    humanize_responses: bool = True
    casual_tone: bool = True
    respond_to_mentions: bool = True
    respond_in_groups: bool = False
    max_daily_messages: int = 100
    autonomous_mode: bool = True
    context_messages_limit: int | None = None  # Override agent setting; None = use agent default


class MessengerCreate(BaseModel):
    platform: str = "telegram"
    name: str = ""
    credentials: MessengerCredentials = Field(default_factory=MessengerCredentials)
    trusted_users: List[str] = Field(default_factory=list)
    public_permissions: List[str] = Field(default_factory=lambda: ["answer_questions", "web_search"])
    config: MessengerConfig = Field(default_factory=MessengerConfig)


class MessengerUpdate(BaseModel):
    name: Optional[str] = None
    credentials: Optional[MessengerCredentials] = None
    trusted_users: Optional[List[str]] = None
    public_permissions: Optional[List[str]] = None
    config: Optional[MessengerConfig] = None
    is_active: Optional[bool] = None


class MessengerResponse(BaseModel):
    id: str
    agent_id: str
    platform: str
    name: str
    # credentials intentionally omitted for security — only partial info returned
    has_credentials: bool = False
    phone_masked: str = ""
    trusted_users: List[str] = []
    public_permissions: List[str] = []
    config: dict = {}
    is_active: bool = False
    is_authenticated: bool = False
    last_active_at: Optional[str] = None
    stats: dict = {}
    created_at: str
    updated_at: str


class AuthStartRequest(BaseModel):
    """Request body for starting Telegram authentication."""
    phone: Optional[str] = None  # override phone from credentials


class AuthCodeRequest(BaseModel):
    """Submit the verification code from Telegram."""
    code: str
    phone_code_hash: Optional[str] = None


class Auth2FARequest(BaseModel):
    """Submit 2FA password if enabled."""
    password: str


class MessengerStatsResponse(BaseModel):
    messages_today: int = 0
    messages_total: int = 0
    last_active_at: Optional[str] = None


class MessengerMessageResponse(BaseModel):
    id: str
    direction: str
    chat_id: str
    user_id: str
    username: str
    display_name: str
    content: str
    is_command: bool
    is_trusted_user: bool
    created_at: str


# ── Helpers ──────────────────────────────────────────────────────────────

def _mask_phone(phone: str) -> str:
    if not phone or len(phone) < 6:
        return "***"
    return phone[:3] + "*" * (len(phone) - 5) + phone[-2:]


def _build_response(acc: MongoMessengerAccount, raw_doc: dict = None) -> dict:
    """Build safe response (no raw credentials)."""
    # Try to determine has_credentials from encrypted field in raw_doc
    has_creds = False
    phone_masked = "***"
    if raw_doc and raw_doc.get("credentials_encrypted"):
        try:
            decrypted = decrypt_dict(raw_doc["credentials_encrypted"])
            has_creds = bool(decrypted.get("api_id") and decrypted.get("api_hash"))
            phone_masked = _mask_phone(decrypted.get("phone", ""))
        except Exception:
            has_creds = True  # encrypted data exists but can't decrypt
    else:
        creds = acc.credentials or {}
        has_creds = bool(creds.get("api_id") and creds.get("api_hash"))
        phone_masked = _mask_phone(creds.get("phone", ""))

    return MessengerResponse(
        id=acc.id,
        agent_id=acc.agent_id,
        platform=acc.platform,
        name=acc.name,
        has_credentials=has_creds,
        phone_masked=phone_masked,
        trusted_users=acc.trusted_users,
        public_permissions=acc.public_permissions,
        config=acc.config,
        is_active=acc.is_active,
        is_authenticated=acc.is_authenticated,
        last_active_at=acc.last_active_at.isoformat() if acc.last_active_at else None,
        stats=acc.stats,
        created_at=acc.created_at.isoformat(),
        updated_at=acc.updated_at.isoformat(),
    ).model_dump()


# ── CRUD ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[dict])
async def list_messenger_accounts(
    agent_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List all messenger accounts for an agent."""
    # Verify agent exists
    agent_svc = AgentService(db)
    agent = await agent_svc.get_by_id(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    svc = MessengerAccountService(db)
    accounts = await svc.get_by_agent(agent_id)
    # Fetch raw docs for has_credentials resolution
    raw_docs = {}
    async for doc in svc.collection.find({"agent_id": agent_id}):
        raw_docs[doc["_id"]] = doc
    return [_build_response(a, raw_docs.get(a.id)) for a in accounts]


@router.post("", status_code=201)
async def create_messenger_account(
    agent_id: str,
    body: MessengerCreate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Create a new messenger account for an agent."""
    agent_svc = AgentService(db)
    agent = await agent_svc.get_by_id(agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")

    # Encrypt credentials before storing
    creds_plain = body.credentials.model_dump()
    encrypted_creds = encrypt_dict(creds_plain)

    account = MongoMessengerAccount(
        agent_id=agent_id,
        platform=body.platform,
        name=body.name or f"{body.platform}-{agent.name}",
        credentials=creds_plain,  # stored in memory; encrypted in DB
        trusted_users=body.trusted_users,
        public_permissions=body.public_permissions,
        config=body.config.model_dump(),
    )

    svc = MessengerAccountService(db)
    # Store with encrypted credentials
    doc = account.to_mongo()
    doc["credentials_encrypted"] = encrypted_creds
    doc["credentials"] = {}  # don't store raw
    await svc.collection.insert_one(doc)

    # Return with safe response
    return _build_response(account)


@router.get("/{messenger_id}")
async def get_messenger_account(
    agent_id: str,
    messenger_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single messenger account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")
    return _build_response(acc)


@router.patch("/{messenger_id}")
async def update_messenger_account(
    agent_id: str,
    messenger_id: str,
    body: MessengerUpdate,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Update a messenger account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    update_data = {}
    if body.name is not None:
        update_data["name"] = body.name
    if body.trusted_users is not None:
        update_data["trusted_users"] = body.trusted_users
    if body.public_permissions is not None:
        update_data["public_permissions"] = body.public_permissions
    if body.config is not None:
        update_data["config"] = body.config.model_dump()
    if body.is_active is not None:
        update_data["is_active"] = body.is_active
    if body.credentials is not None:
        creds_plain = body.credentials.model_dump()
        update_data["credentials_encrypted"] = encrypt_dict(creds_plain)
        update_data["credentials"] = {}  # never store raw

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    updated = await svc.update(messenger_id, update_data)
    if not updated:
        raise HTTPException(404, "Messenger account not found")

    # Re-fetch to build proper response
    acc = await svc.get_by_id(messenger_id)
    # Decrypt creds to build response
    raw_doc = await svc.collection.find_one({"_id": messenger_id})
    if raw_doc and raw_doc.get("credentials_encrypted"):
        try:
            decrypted = decrypt_dict(raw_doc["credentials_encrypted"])
            acc.credentials = decrypted
        except Exception:
            pass

    return _build_response(acc)


@router.delete("/{messenger_id}")
async def delete_messenger_account(
    agent_id: str,
    messenger_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Delete a messenger account and its messages."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    # Stop listener if running
    from app.services.telegram_service import stop_telegram_client
    await stop_telegram_client(messenger_id)

    # Delete messages
    msg_svc = MessengerMessageService(db)
    await msg_svc.collection.delete_many({"messenger_id": messenger_id})

    # Delete session file
    import os
    session_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "messengers", "sessions")
    for ext in ("", ".session"):
        path = os.path.join(session_dir, f"{messenger_id}{ext}")
        if os.path.exists(path):
            os.remove(path)

    # Delete account
    await svc.delete(messenger_id)
    return {"detail": "Messenger account deleted"}


# ── Telegram Auth Flow ───────────────────────────────────────────────────

@router.post("/{messenger_id}/auth/start")
async def start_telegram_auth(
    agent_id: str,
    messenger_id: str,
    body: AuthStartRequest = None,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Start Telegram authentication — sends code to phone."""
    svc = MessengerAccountService(db)
    raw_doc = await svc.collection.find_one({"_id": messenger_id})
    if not raw_doc or raw_doc.get("agent_id") != agent_id:
        raise HTTPException(404, "Messenger account not found")

    # Decrypt credentials
    encrypted = raw_doc.get("credentials_encrypted", "")
    if not encrypted:
        raise HTTPException(400, "No credentials stored. Update the account with API ID/Hash/Phone first.")

    try:
        creds = decrypt_dict(encrypted)
    except Exception:
        raise HTTPException(400, "Failed to decrypt credentials")

    api_id = creds.get("api_id")
    api_hash = creds.get("api_hash")
    phone = (body.phone if body and body.phone else creds.get("phone")) or ""

    if not api_id or not api_hash or not phone:
        raise HTTPException(400, "Missing api_id, api_hash or phone in credentials")

    from app.services.telegram_service import start_auth_flow
    result = await start_auth_flow(messenger_id, int(api_id), api_hash, phone)

    return result  # { "status": "code_sent", "phone_code_hash": "..." } or { "status": "already_authenticated" }


@router.post("/{messenger_id}/auth/code")
async def submit_telegram_code(
    agent_id: str,
    messenger_id: str,
    body: AuthCodeRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Submit the verification code received via Telegram/SMS."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    from app.services.telegram_service import submit_auth_code
    result = await submit_auth_code(messenger_id, body.code, body.phone_code_hash)

    if result.get("status") == "authenticated":
        # Mark as authenticated
        await svc.update(messenger_id, {
            "is_authenticated": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    return result


@router.post("/{messenger_id}/auth/2fa")
async def submit_telegram_2fa(
    agent_id: str,
    messenger_id: str,
    body: Auth2FARequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Submit 2FA password if account has two-step verification."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    from app.services.telegram_service import submit_2fa_password
    result = await submit_2fa_password(messenger_id, body.password)

    if result.get("status") == "authenticated":
        await svc.update(messenger_id, {
            "is_authenticated": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    return result


# ── Start / Stop Listener ────────────────────────────────────────────────

@router.post("/{messenger_id}/start")
async def start_messenger_listener(
    agent_id: str,
    messenger_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Start listening for messages on this account."""
    svc = MessengerAccountService(db)
    raw_doc = await svc.collection.find_one({"_id": messenger_id})
    if not raw_doc or raw_doc.get("agent_id") != agent_id:
        raise HTTPException(404, "Messenger account not found")

    if not raw_doc.get("is_authenticated"):
        raise HTTPException(400, "Account not authenticated. Complete auth flow first.")

    encrypted = raw_doc.get("credentials_encrypted", "")
    if not encrypted:
        raise HTTPException(400, "No credentials stored")

    try:
        creds = decrypt_dict(encrypted)
    except Exception:
        raise HTTPException(400, "Failed to decrypt credentials")

    from app.services.telegram_service import start_telegram_listener
    await start_telegram_listener(messenger_id, agent_id, creds, raw_doc)

    await svc.update(messenger_id, {
        "is_active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"detail": "Listener started", "status": "active"}


@router.post("/{messenger_id}/stop")
async def stop_messenger_listener(
    agent_id: str,
    messenger_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Stop listening for messages on this account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    from app.services.telegram_service import stop_telegram_client
    await stop_telegram_client(messenger_id)

    await svc.update(messenger_id, {
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"detail": "Listener stopped", "status": "stopped"}


# ── Stats & Messages ────────────────────────────────────────────────────

@router.get("/{messenger_id}/stats")
async def get_messenger_stats(
    agent_id: str,
    messenger_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get messenger account statistics."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    msg_svc = MessengerMessageService(db)
    today_count = await msg_svc.count_today(messenger_id)
    total = await msg_svc.count(filter={"messenger_id": messenger_id})

    return MessengerStatsResponse(
        messages_today=today_count,
        messages_total=total,
        last_active_at=acc.last_active_at.isoformat() if acc.last_active_at else None,
    ).model_dump()


@router.get("/{messenger_id}/messages", response_model=list[dict])
async def list_messenger_messages(
    agent_id: str,
    messenger_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    chat_id: Optional[str] = Query(None),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List messages for a messenger account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    msg_svc = MessengerMessageService(db)
    if chat_id:
        messages = await msg_svc.get_by_chat(messenger_id, chat_id, limit=limit)
    else:
        messages = await msg_svc.get_by_messenger(messenger_id, limit=limit, skip=offset)

    return [
        MessengerMessageResponse(
            id=m.id,
            direction=m.direction,
            chat_id=m.chat_id,
            user_id=m.user_id,
            username=m.username,
            display_name=m.display_name,
            content=m.content[:500],  # truncate for list view
            is_command=m.is_command,
            is_trusted_user=m.is_trusted_user,
            created_at=m.created_at.isoformat(),
        ).model_dump()
        for m in messages
    ]


# ── Helper: create messenger log ────────────────────────────────────────

async def _create_messenger_log(
    db, messenger_id: str, agent_id: str,
    level: str, event: str, message: str,
    context: dict = None,
):
    """Create a messenger log entry in MongoDB."""
    log = MongoMessengerLog(
        messenger_id=messenger_id,
        agent_id=agent_id,
        level=level,
        event=event,
        message=message,
        context=context,
    )
    log_svc = MessengerLogService(db)
    await log_svc.create(log)
    return log


async def _create_messenger_error(
    db, messenger_id: str, agent_id: str,
    error_type: str, message: str,
    context: dict = None,
):
    """Create both a messenger log (error level) and an AgentError with source=messenger."""
    # Log entry
    await _create_messenger_log(
        db, messenger_id, agent_id,
        level="error", event="error", message=message,
        context=context,
    )
    # Agent-level error (shows in global errors)
    err = MongoAgentError(
        agent_id=agent_id,
        error_type=error_type,
        source="messenger",
        message=message,
        context={**(context or {}), "messenger_id": messenger_id},
    )
    err_svc = AgentErrorService(db)
    await err_svc.create(err)
    return err


# ── Test ─────────────────────────────────────────────────────────────────

class TestMessageRequest(BaseModel):
    chat_id: Optional[str] = None  # If empty, send to Saved Messages (self)
    message: str = "Hello from AI Agent test! 🤖"


class SendMessageRequest(BaseModel):
    recipient: str  # chat_id, @username, or phone number
    message: str


@router.get("/{messenger_id}/contacts")
async def list_messenger_contacts(
    agent_id: str,
    messenger_id: str,
    limit: int = Query(50, le=200),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get Telegram dialogs (contacts, groups, channels) for a messenger account."""
    svc = MessengerAccountService(db)
    raw_doc = await svc.collection.find_one({"_id": messenger_id})
    if not raw_doc or raw_doc.get("agent_id") != agent_id:
        raise HTTPException(404, "Messenger account not found")

    if not raw_doc.get("is_authenticated"):
        raise HTTPException(400, "Account not authenticated")

    encrypted = raw_doc.get("credentials_encrypted", "")
    if not encrypted:
        raise HTTPException(400, "No credentials stored")

    try:
        creds = decrypt_dict(encrypted)
    except Exception:
        raise HTTPException(400, "Failed to decrypt credentials")

    from app.services.telegram_service import get_telegram_dialogs
    try:
        dialogs = await get_telegram_dialogs(
            messenger_id=messenger_id,
            creds=creds,
            limit=limit,
        )
    except Exception as e:
        raise HTTPException(500, detail=f"Failed to load contacts: {str(e)}")

    return dialogs


@router.post("/{messenger_id}/send")
async def send_messenger_message(
    agent_id: str,
    messenger_id: str,
    body: SendMessageRequest,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Send a message to a specific Telegram user/chat using the agent's messenger account."""
    svc = MessengerAccountService(db)
    raw_doc = await svc.collection.find_one({"_id": messenger_id})
    if not raw_doc or raw_doc.get("agent_id") != agent_id:
        raise HTTPException(404, "Messenger account not found")

    if not raw_doc.get("is_authenticated"):
        raise HTTPException(400, "Account not authenticated")

    encrypted = raw_doc.get("credentials_encrypted", "")
    if not encrypted:
        raise HTTPException(400, "No credentials stored")

    try:
        creds = decrypt_dict(encrypted)
    except Exception:
        raise HTTPException(400, "Failed to decrypt credentials")

    await _create_messenger_log(
        db, messenger_id, agent_id,
        level="info", event="manual_send",
        message=f"Sending message to {body.recipient}",
        context={"recipient": body.recipient, "length": len(body.message)},
    )

    from app.services.telegram_service import send_telegram_message
    try:
        result = await send_telegram_message(
            messenger_id=messenger_id,
            creds=creds,
            recipient=body.recipient,
            message=body.message,
        )
    except Exception as e:
        await _create_messenger_error(
            db, messenger_id, agent_id,
            error_type="messenger_send_error",
            message=f"Failed to send message: {str(e)}",
            context={"recipient": body.recipient},
        )
        raise HTTPException(500, detail=f"Failed to send message: {str(e)}")

    await _create_messenger_log(
        db, messenger_id, agent_id,
        level="info", event="manual_send_completed",
        message=f"Message sent to {result.get('sent_to', body.recipient)}",
        context=result,
    )

    # Log outgoing message
    from app.mongodb.models.messenger import MongoMessengerMessage
    from app.mongodb.services import MessengerMessageService
    msg_svc = MessengerMessageService(db)
    outgoing_msg = MongoMessengerMessage(
        messenger_id=messenger_id,
        agent_id=agent_id,
        chat_id=result.get("chat_id", ""),
        user_id="",
        username="",
        display_name="",
        direction="outgoing",
        content=body.message,
        is_command=False,
        is_trusted_user=False,
    )
    await msg_svc.create(outgoing_msg)

    return result


@router.post("/{messenger_id}/test")
async def test_messenger(
    agent_id: str,
    messenger_id: str,
    body: TestMessageRequest = None,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Test messenger by sending a message and verifying connectivity."""
    svc = MessengerAccountService(db)
    raw_doc = await svc.collection.find_one({"_id": messenger_id})
    if not raw_doc or raw_doc.get("agent_id") != agent_id:
        raise HTTPException(404, "Messenger account not found")

    if not raw_doc.get("is_authenticated"):
        raise HTTPException(400, "Account not authenticated")

    encrypted = raw_doc.get("credentials_encrypted", "")
    if not encrypted:
        raise HTTPException(400, "No credentials stored")

    try:
        creds = decrypt_dict(encrypted)
    except Exception:
        raise HTTPException(400, "Failed to decrypt credentials")

    test_message = (body.message if body and body.message else "Hello from AI Agent test! 🤖")
    chat_id = (body.chat_id if body and body.chat_id else None)

    await _create_messenger_log(
        db, messenger_id, agent_id,
        level="info", event="test_started",
        message=f"Test started — sending message to {'chat ' + chat_id if chat_id else 'Saved Messages'}",
    )

    from app.services.telegram_service import test_telegram_connection
    try:
        result = await test_telegram_connection(
            messenger_id=messenger_id,
            creds=creds,
            test_message=test_message,
            chat_id=chat_id,
        )
    except Exception as e:
        await _create_messenger_error(
            db, messenger_id, agent_id,
            error_type="messenger_test_error",
            message=f"Test failed: {str(e)}",
            context={"chat_id": chat_id},
        )
        raise HTTPException(500, detail=f"Test failed: {str(e)}")

    await _create_messenger_log(
        db, messenger_id, agent_id,
        level="info", event="test_completed",
        message=f"Test completed — {result.get('status', 'unknown')}",
        context=result,
    )

    return result


# ── Logs ─────────────────────────────────────────────────────────────────

@router.get("/{messenger_id}/logs")
async def list_messenger_logs(
    agent_id: str,
    messenger_id: str,
    level: Optional[str] = Query(None, description="Filter by level: debug, info, warning, error"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List operational logs for a messenger account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    log_svc = MessengerLogService(db)
    logs = await log_svc.get_by_messenger(messenger_id, limit=limit, skip=offset, level=level)
    return [
        {
            "id": log.id,
            "messenger_id": log.messenger_id,
            "agent_id": log.agent_id,
            "level": log.level,
            "event": log.event,
            "message": log.message,
            "context": log.context,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@router.delete("/{messenger_id}/logs")
async def clear_messenger_logs(
    agent_id: str,
    messenger_id: str,
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Clear all logs for a messenger account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    log_svc = MessengerLogService(db)
    deleted = await log_svc.delete_by_messenger(messenger_id)
    return {"detail": f"Deleted {deleted} log entries"}


# ── Errors (messenger-specific, also shown in global agent errors) ───────

@router.get("/{messenger_id}/errors")
async def list_messenger_errors(
    agent_id: str,
    messenger_id: str,
    resolved: Optional[bool] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    _user=Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List errors for a specific messenger account."""
    svc = MessengerAccountService(db)
    acc = await svc.get_by_id(messenger_id)
    if not acc or acc.agent_id != agent_id:
        raise HTTPException(404, "Messenger account not found")

    err_svc = AgentErrorService(db)
    filt = {
        "agent_id": agent_id,
        "source": "messenger",
        "context.messenger_id": messenger_id,
    }
    if resolved is not None:
        filt["resolved"] = resolved

    errors = await err_svc.get_all(filter=filt, skip=offset, limit=limit)
    errors.sort(key=lambda e: e.created_at, reverse=True)
    return [
        {
            "id": e.id,
            "agent_id": e.agent_id,
            "error_type": e.error_type,
            "source": e.source,
            "message": e.message,
            "context": e.context,
            "resolved": e.resolved,
            "resolution": e.resolution,
            "created_at": e.created_at.isoformat(),
        }
        for e in errors
    ]
