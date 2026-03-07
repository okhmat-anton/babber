"""MongoDB Messenger models — agent messenger accounts and messages."""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MongoMessengerAccount(BaseModel):
    """Messenger account linked to an agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    platform: str = "telegram"  # telegram, whatsapp, discord, vk, slack
    name: str = ""  # display name / username

    # Credentials (encrypted JSON string in DB)
    credentials: Dict[str, Any] = Field(default_factory=dict)
    # For Telegram: { api_id, api_hash, phone, session_name }

    # Trusted users (whitelist) — can issue full commands
    trusted_users: List[str] = Field(default_factory=list)

    # Permissions for regular users
    public_permissions: List[str] = Field(default_factory=lambda: [
        "answer_questions", "web_search"
    ])

    # Behaviour config
    config: Dict[str, Any] = Field(default_factory=lambda: {
        "response_delay_min": 2,
        "response_delay_max": 8,
        "typing_indicator": True,
        "humanize_responses": True,
        "casual_tone": True,
        "respond_to_mentions": True,
        "respond_in_groups": False,
        "max_daily_messages": 100,
        "autonomous_mode": True,
        "context_messages_limit": None,  # None = use agent default
    })

    is_active: bool = False
    is_authenticated: bool = False  # completed 2FA / login
    last_active_at: Optional[datetime] = None

    # Stats
    stats: Dict[str, Any] = Field(default_factory=lambda: {
        "messages_today": 0,
        "messages_total": 0,
        "last_reset_date": None,
    })

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        if doc.get("last_active_at"):
            doc["last_active_at"] = doc["last_active_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoMessengerAccount":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        for dt_field in ("created_at", "updated_at", "last_active_at"):
            if isinstance(doc.get(dt_field), str):
                doc[dt_field] = datetime.fromisoformat(doc[dt_field])
        return cls(**doc)


class MongoMessengerLog(BaseModel):
    """Operational log entry for messenger activity."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messenger_id: str
    agent_id: str
    level: str = "info"  # debug, info, warning, error
    event: str = ""  # listener_started, listener_stopped, message_received, message_sent, auth_started, auth_completed, test_sent, test_received, error, etc.
    message: str = ""
    context: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoMessengerLog":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)


class MongoMessengerMessage(BaseModel):
    """Individual message logged from a messenger."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messenger_id: str  # FK to MongoMessengerAccount
    agent_id: str

    platform_message_id: str = ""  # native message ID
    chat_id: str = ""  # native chat/dialog ID
    user_id: str = ""  # native user ID
    username: str = ""
    display_name: str = ""

    direction: str = "incoming"  # incoming / outgoing
    content: str = ""
    is_command: bool = False  # from trusted user as command?
    is_trusted_user: bool = False

    # If we produced a response, link it
    response_id: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoMessengerMessage":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)
