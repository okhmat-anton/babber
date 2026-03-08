"""MongoDB model for Research Resources (trusted sources for agent research)."""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field


class MongoResearchResource(BaseModel):
    """
    A trusted resource/source that agents can use for research.

    Fields:
      - name: human-readable name of the resource (e.g. "Stack Overflow", "MDN")
      - url: base URL of the resource
      - description: what kind of information can be found here
      - trust_level: "low", "medium", "high", "highest"
        - Simple research uses medium+ trust resources
        - Deep research uses only "highest" trust resources
      - user_rating: user-assigned rating 0-10
      - agent_rating: agent-assigned rating 0-10
      - search_instructions: how agents should search on this resource
      - category: type of resource (e.g. "docs", "forum", "wiki", "news", "code", "general")
      - tags: free-form labels
      - is_active: whether this resource is currently usable
      - added_by: "user" or "agent"
      - last_used_at: when an agent last used this resource
      - use_count: how many times agents have used this resource
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    url: str
    description: str = ""
    trust_level: str = "medium"  # low, medium, high, highest
    user_rating: float = 5.0  # 0-10
    agent_rating: float = 5.0  # 0-10
    search_instructions: str = ""  # how to search on this resource
    category: str = "general"  # docs, forum, wiki, news, code, general, academic
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True
    added_by: str = "user"  # user, agent
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        if doc.get("last_used_at"):
            doc["last_used_at"] = doc["last_used_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoResearchResource":
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = doc.pop("_id")
        for field in ("created_at", "updated_at", "last_used_at"):
            if isinstance(doc.get(field), str):
                doc[field] = datetime.fromisoformat(doc[field])
        return cls(**doc)
