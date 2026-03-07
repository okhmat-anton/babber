from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    type: str = "one_time"  # one_time, recurring, trigger
    priority: str = "normal"
    schedule: str | None = None
    execute_at: datetime | None = None  # For scheduled one-time tasks
    trigger_type: str | None = None  # For trigger-based tasks
    trigger_config: dict | None = None  # Configuration for triggers
    max_retries: int = 3
    timeout: int = 300
    parent_task_id: UUID | None = None  # For subtasks
    ready_to_execute: bool = True  # False if needs decomposition


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    type: str | None = None
    priority: str | None = None
    schedule: str | None = None
    execute_at: datetime | None = None
    trigger_type: str | None = None
    trigger_config: dict | None = None
    max_retries: int | None = None
    timeout: int | None = None
    status: str | None = None  # Allow status updates
    is_decomposed: bool | None = None
    ready_to_execute: bool | None = None


class TaskResponse(BaseModel):
    id: UUID
    agent_id: UUID | None
    agent_name: str | None = None
    title: str
    description: str
    type: str
    status: str
    priority: str
    schedule: str | None
    next_run_at: datetime | None
    execute_at: datetime | None
    trigger_type: str | None
    trigger_config: dict | None
    max_retries: int
    retry_count: int
    timeout: int
    parent_task_id: UUID | None
    is_decomposed: bool
    ready_to_execute: bool
    result: dict | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
