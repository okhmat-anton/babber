"""MongoDB model for Agent Facts & Hypotheses."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class MongoAgentFact(BaseModel):
    """
    A fact or hypothesis stored by an agent.

    Fields:
      - type: "fact" or "hypothesis"
      - content: the actual text
      - source: where the fact/hypothesis came from (e.g. "conversation", "web", "analysis")
      - verified: whether this has been verified (for hypotheses)
      - confidence: how confident the agent is (0.0-1.0)
      - tags: free-form labels
      - created_by: "agent" or "user"
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    type: str = "fact"  # "fact" or "hypothesis"
    content: str
    source: str = "conversation"  # conversation, web, analysis, observation, user
    verified: bool = False
    confidence: float = 0.8
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None  # User-defined category for grouping
    created_by: str = "agent"  # agent, user
    # Cross-linking
    linked_video_ids: List[str] = Field(default_factory=list)
    linked_analysis_ids: List[str] = Field(default_factory=list)
    linked_idea_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgentFact":
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)
