"""MongoDB model for Agent Events (memory events)."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class MongoAgentEvent(BaseModel):
    """
    An event stored in agent's memory.

    Events represent things that happened — conversations, observations,
    discoveries, decisions, milestones, or anything the agent wants to
    remember as a timeline entry.

    Fields:
      - event_type: category of event (conversation, observation, discovery, decision, milestone, custom)
      - title: short summary / headline
      - description: detailed event description
      - source: where the event came from (agent, user, system)
      - importance: priority level (low, medium, high, critical)
      - tags: free-form labels
      - created_by: "agent" or "user"
      - event_date: when the event actually happened (may differ from created_at)
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    event_type: str = "observation"  # conversation, observation, discovery, decision, milestone, custom
    title: str
    description: str = ""
    comment: str = ""  # outcome / comment on the event
    source: str = "agent"  # agent, user, system
    importance: str = "medium"  # low, medium, high, critical
    tags: List[str] = Field(default_factory=list)
    created_by: str = "agent"  # agent, user
    sort_order: int = 0  # manual ordering within event_type (lower = higher)
    event_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["event_date"] = doc["event_date"].isoformat()
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgentEvent":
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("event_date"), str):
            doc["event_date"] = datetime.fromisoformat(doc["event_date"])
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)
