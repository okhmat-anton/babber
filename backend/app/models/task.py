import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, Text, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(20), default="one_time")  # one_time, recurring, trigger
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, paused, completed, failed, cancelled
    priority: Mapped[str] = mapped_column(String(20), default="normal")  # low, normal, high, critical
    schedule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execute_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # For scheduled one-time tasks
    trigger_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # event_name for trigger-based tasks
    trigger_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # Configuration for triggers
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout: Mapped[int] = mapped_column(Integer, default=300)
    
    # Task decomposition fields
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    is_decomposed: Mapped[bool] = mapped_column(Boolean, default=False)  # True if task has been decomposed into subtasks
    ready_to_execute: Mapped[bool] = mapped_column(Boolean, default=True)  # False if needs decomposition first
    
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent = relationship("Agent", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], backref="children")
