"""MongoDB models for Skills."""
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import uuid


class MongoSkill(BaseModel):
    """MongoDB model for Skill."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # Unique index in MongoDB
    display_name: str
    description: str = ""
    description_for_agent: str = ""
    category: str = "general"  # general, web, files, code, data, custom
    version: str = "1.0.0"
    code: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    is_system: bool = False
    is_shared: bool = False
    enabled: bool = True
    author_agent_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        """Convert to MongoDB document."""
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoSkill":
        """Create from MongoDB document."""
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)


class MongoAgentSkill(BaseModel):
    """MongoDB model for Agent-Skill relationship."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    skill_id: str
    is_enabled: bool = True
    config: Optional[Dict[str, Any]] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        """Convert to MongoDB document."""
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["added_at"] = doc["added_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoAgentSkill":
        """Create from MongoDB document."""
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("added_at"), str):
            doc["added_at"] = datetime.fromisoformat(doc["added_at"])
        return cls(**doc)
