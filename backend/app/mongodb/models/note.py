"""MongoDB model for Notes — user notes and thoughts."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class MongoNote(BaseModel):
    """
    A note from the user.

    Fields:
      - title: short note title
      - content: note body text (supports markdown)
      - category: optional grouping category
      - priority: low, medium, high
      - status: active, archived, completed
      - tags: free-form labels
      - in_context: whether to include in agent context
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    content: str = ""
    category: Optional[str] = None
    priority: str = "medium"  # low, medium, high
    status: str = "active"  # active, completed, archived
    tags: List[str] = Field(default_factory=list)
    in_context: bool = True  # included in agent context
    sort_order: int = 0  # manual ordering within category (lower = higher)
    # Cross-linking
    linked_idea_ids: List[str] = Field(default_factory=list)
    linked_fact_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoNote":
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)
