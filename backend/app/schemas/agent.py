from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


# ---------- Agent Model sub-schemas ----------

class AgentModelEntry(BaseModel):
    """One model assignment for an agent."""
    model_config_id: UUID
    task_type: str = "general"  # e.g. "code generation", "text analysis"
    tags: list[str] = []       # e.g. ["code", "fast", "large-context"]
    priority: int = 0          # 0 = primary / default


class AgentModelResponse(BaseModel):
    id: UUID
    model_config_id: UUID
    model_name: str | None = None  # resolved from relationship
    model_display_name: str | None = None
    task_type: str
    tags: list[str] | None = []
    priority: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- Agent schemas ----------

class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    mission: str = ""
    system_prompt: str = ""
    temperature: float = 0.7
    top_p: float = 0.9
    top_k: int = 40
    max_tokens: int = 2048
    num_ctx: int = 32768
    repeat_penalty: float = 1.1
    num_predict: int = -1
    stop: list[str] = []
    num_thread: int = 8
    num_gpu: int = 1
    # Permissions
    filesystem_access: bool = False
    system_access: bool = False
    # Self-thinking mode
    self_thinking: bool = False
    # Multi-model support
    models: list[AgentModelEntry] = []
    # Thinking protocols (multi-protocol)
    thinking_protocol_id: str | None = None      # main (orchestrator) protocol
    protocol_ids: list[str] = []                  # all available protocols for the agent


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    mission: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_tokens: int | None = None
    num_ctx: int | None = None
    repeat_penalty: float | None = None
    num_predict: int | None = None
    stop: list[str] | None = None
    num_thread: int | None = None
    num_gpu: int | None = None
    # Permissions
    filesystem_access: bool | None = None
    system_access: bool | None = None
    # Self-thinking mode
    self_thinking: bool | None = None
    # Multi-model support (if provided, replaces all)
    models: list[AgentModelEntry] | None = None
    # Thinking protocols (multi-protocol)
    thinking_protocol_id: str | None = None      # main (orchestrator) protocol
    protocol_ids: list[str] | None = None         # if provided, replaces all agent_protocols


class AgentResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    mission: str = ""
    model_id: UUID | None = None      # legacy, may be null
    model_name: str | None = None     # legacy, may be null
    system_prompt: str
    status: str
    temperature: float
    top_p: float
    top_k: int
    max_tokens: int
    num_ctx: int
    repeat_penalty: float
    num_predict: int
    stop: list[str] | None
    num_thread: int
    num_gpu: int
    filesystem_access: bool = False
    system_access: bool = False
    self_thinking: bool = False
    beliefs: dict = {}                 # from beliefs.json (filesystem)
    aspirations: dict = {}             # from aspirations.json (filesystem)
    thinking_protocol_id: str | None = None
    thinking_protocol: dict | None = None  # expanded main protocol data
    protocols: list[dict] = []               # all assigned protocols with is_main flag
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None
    # Multi-model
    agent_models: list[AgentModelResponse] = []

    model_config = {"from_attributes": True}


class AgentStatsResponse(BaseModel):
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_logs: int = 0
    total_memories: int = 0
    total_skills: int = 0
