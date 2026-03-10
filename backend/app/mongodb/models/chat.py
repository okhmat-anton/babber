"""MongoDB Chat models."""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MongoChatSession(BaseModel):
    """Chat Session model for MongoDB."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = "New Chat"
    chat_type: str = "user"  # user, agent, project_task
    project_slug: Optional[str] = None
    task_id: Optional[str] = None
    video_id: Optional[str] = None  # linked watched video
    model_ids: List[str] = Field(default_factory=list)
    agent_id: Optional[str] = None
    agent_ids: List[str] = Field(default_factory=list)
    multi_model: bool = False
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    protocol_state: Optional[Dict[str, Any]] = None
    unread_count: int = 0
    # Conversation summarization (AIS-35)
    summary: Optional[str] = None
    summary_up_to_message_id: Optional[str] = None
    summary_created_at: Optional[datetime] = None
    summary_token_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        if doc.get("summary_created_at"):
            doc["summary_created_at"] = doc["summary_created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoChatSession":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        if isinstance(doc.get("summary_created_at"), str):
            doc["summary_created_at"] = datetime.fromisoformat(doc["summary_created_at"])
        return cls(**doc)


class MongoChatMessage(BaseModel):
    """Chat Message model for MongoDB."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # user, assistant, system
    content: str = ""
    model_name: Optional[str] = None
    model_responses: Optional[Dict[str, Any]] = None
    total_tokens: int = 0
    duration_ms: int = 0
    metadata: Optional[Dict[str, Any]] = None
    audio_url: Optional[str] = None  # URL to audio file (TTS output or STT input)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoChatMessage":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)
