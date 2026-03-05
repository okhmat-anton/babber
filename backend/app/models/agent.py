import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func, Text, Float, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_configs.id"), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="idle")  # idle, running, paused, error, stopped

    # Generation parameters
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    top_p: Mapped[float] = mapped_column(Float, default=0.9)
    top_k: Mapped[int] = mapped_column(Integer, default=40)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    num_ctx: Mapped[int] = mapped_column(Integer, default=32768)
    repeat_penalty: Mapped[float] = mapped_column(Float, default=1.1)
    num_predict: Mapped[int] = mapped_column(Integer, default=-1)
    stop: Mapped[list | None] = mapped_column(ARRAY(String), default=[])
    num_thread: Mapped[int] = mapped_column(Integer, default=8)
    num_gpu: Mapped[int] = mapped_column(Integer, default=1)

    # Thinking protocol
    thinking_protocol_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("thinking_protocols.id", ondelete="SET NULL"), nullable=True)

    # Meta
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    model_config_rel = relationship("ModelConfig", lazy="selectin")
    thinking_protocol = relationship("ThinkingProtocol", lazy="selectin")
    agent_models = relationship("AgentModel", back_populates="agent", cascade="all, delete-orphan", lazy="selectin", order_by="AgentModel.priority")
    tasks = relationship("Task", back_populates="agent", cascade="all, delete-orphan")
    logs = relationship("AgentLog", back_populates="agent", cascade="all, delete-orphan")
    agent_skills = relationship("AgentSkill", back_populates="agent", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="agent", cascade="all, delete-orphan")
