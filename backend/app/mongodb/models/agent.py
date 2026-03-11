"""MongoDB Agent models."""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class MongoAgent(BaseModel):
    """Agent model for MongoDB."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    system_prompt: str = ""
    status: str = "idle"  # idle, running, paused, error, stopped
    enabled: bool = True  # Whether agent is available for chat selection

    # Generation parameters
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 2048
    num_ctx: int = 32768
    repeat_penalty: float = 1.1
    num_predict: int = -1
    stop: List[str] = Field(default_factory=list)
    num_thread: int = 8
    num_gpu: int = 1

    # Permissions
    filesystem_access: bool = False
    system_access: bool = False

    # Chat interaction settings
    max_messages_before_response: int = 5

    # Messenger context — default number of recent messages for messenger LLM context
    messenger_context_limit: int = 10

    # Avatar
    avatar_url: Optional[str] = None

    # TTS voice
    voice: Optional[str] = None

    # Self-thinking mode
    self_thinking: bool = False

    # Whether to include creator/owner context in agent responses
    use_creator_context: bool = True

    # Expert questions — top questions other agents can ask this agent
    expert_questions: List[str] = Field(default_factory=list)

    # Thinking protocol
    thinking_protocol_id: Optional[str] = None

    # Runtime
    last_run_at: Optional[datetime] = None

    # Meta
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        """Convert to MongoDB document."""
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        if doc.get("last_run_at"):
            doc["last_run_at"] = doc["last_run_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgent":
        """Create from MongoDB document."""
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        if isinstance(doc.get("last_run_at"), str):
            doc["last_run_at"] = datetime.fromisoformat(doc["last_run_at"])
        return cls(**doc)


class MongoAgentModel(BaseModel):
    """AgentModel association for MongoDB — links agent to model config."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    model_config_id: str
    task_type: str = "general"
    tags: List[str] = Field(default_factory=list)
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgentModel":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)


class MongoAgentProtocol(BaseModel):
    """AgentProtocol join table for MongoDB — links agent to thinking protocol."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    protocol_id: str
    is_main: bool = False
    priority: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgentProtocol":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)


class MongoAgentError(BaseModel):
    """Agent error tracking for MongoDB."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    error_type: str  # skill_not_found, skill_exec_error, llm_error, unknown
    source: str = "autonomous"  # autonomous, chat, skill
    message: str
    context: Optional[Dict[str, Any]] = None
    resolved: bool = False
    resolution: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgentError":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)


class MongoThinkingProtocol(BaseModel):
    """Thinking Protocol for MongoDB — step-by-step reasoning workflows."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    type: str = "standard"  # standard, orchestrator, loop
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    response_style: Optional[str] = None  # humanized, formal, casual, technical, concise, creative, academic
    is_default: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoThinkingProtocol":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)
