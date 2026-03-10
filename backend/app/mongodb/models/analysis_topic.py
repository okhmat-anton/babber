"""MongoDB model for Analysis Topics."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class MongoAnalysisTopic(BaseModel):
    """
    An analysis topic — a subject the user/agent is researching or analyzing.

    Fields:
      - title: topic name / question
      - description: detailed description of what to analyze
      - status: draft, active, completed, archived
      - agent_id: optional — if assigned to a specific agent
      - fact_ids: list of connected fact IDs
      - tags: free-form labels
      - created_by: "agent" or "user"
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    status: str = "active"  # draft, active, completed, archived
    agent_id: Optional[str] = None  # None = global, set = agent-specific
    category: Optional[str] = None  # User-defined category for grouping
    fact_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_by: str = "user"  # agent, user
    # Cross-linking
    linked_video_ids: List[str] = Field(default_factory=list)
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
    def from_mongo(cls, doc: dict) -> "MongoAnalysisTopic":
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)
