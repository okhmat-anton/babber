"""MongoDB model for Ideas — user and agent ideas."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class MongoIdea(BaseModel):
    """
    An idea from a user or agent.

    Fields:
      - title: short idea name
      - description: detailed description
      - source: "user" or "agent"
      - agent_id: optional — if created by/for a specific agent
      - category: optional grouping category
      - priority: low, medium, high
      - status: new, in_progress, done, archived
      - tags: free-form labels
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    source: str = "user"  # "user" or "agent"
    agent_id: Optional[str] = None  # None = global user idea, set = agent idea
    category: Optional[str] = None  # User-defined category for grouping
    priority: str = "medium"  # low, medium, high
    status: str = "new"  # new, in_progress, done, archived
    tags: List[str] = Field(default_factory=list)
    created_by: str = "user"  # user, agent
    # Cross-linking
    linked_video_ids: List[str] = Field(default_factory=list)
    linked_fact_ids: List[str] = Field(default_factory=list)
    linked_analysis_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoIdea":
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)
