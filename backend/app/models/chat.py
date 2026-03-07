"""
ChatSession and ChatMessage models for persistent chat history.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func, Integer, Float, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="New Chat")
    # Chat type: 'user' (default), 'agent' (agent-initiated), 'project_task' (project/task discussion)
    chat_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    # For project_task chats: project slug
    project_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # For project_task chats: task ID
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Models used in this chat (list of model_config IDs or ollama model names)
    model_ids: Mapped[list | None] = mapped_column(ARRAY(String), default=[])
    # Agent ID if chatting with a specific agent
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    # Multiple agent IDs for multi-agent mode
    agent_ids: Mapped[list | None] = mapped_column(JSONB, default=[], server_default="'[]'::jsonb")
    # Multi-model mode
    multi_model: Mapped[bool] = mapped_column(Boolean, default=False)
    # System prompt override
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    # Protocol execution state (todo list, active child protocol, etc.)
    protocol_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Unread messages count for user
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at", lazy="selectin")
    agent = relationship("Agent", lazy="selectin")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Which model produced this message (for multi-model mode)
    model_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # For multi-model: all individual model responses before synthesis
    model_responses: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Stats
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Metadata: skill invocations, todo updates, delegation info
    msg_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
