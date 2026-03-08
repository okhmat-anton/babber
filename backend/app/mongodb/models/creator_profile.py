"""MongoDB CreatorProfile model — singleton document for creator/owner context."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MongoCreatorProfile(BaseModel):
    """Creator profile — info about the person who manages the bots."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    who: Optional[str] = None            # кто он
    goals: Optional[str] = None          # цели
    dreams: Optional[str] = None         # мечты
    skills_and_abilities: Optional[str] = None  # умения и навыки
    current_situation: Optional[str] = None     # текущая ситуация
    principles: Optional[str] = None     # принципы
    successes: Optional[str] = None      # успехи
    failures: Optional[str] = None       # неудачи
    action_history: Optional[str] = None # история попыток действий
    ideas: Optional[str] = None          # идеи

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoCreatorProfile":
        if not doc:
            return None
        doc["id"] = doc.pop("_id")
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        if isinstance(doc.get("updated_at"), str):
            doc["updated_at"] = datetime.fromisoformat(doc["updated_at"])
        return cls(**doc)

    def to_context_string(self) -> str:
        """Build a human-readable context string for LLM consumption."""
        sections = []
        if self.name:
            sections.append(f"Name: {self.name}")
        if self.who:
            sections.append(f"Who they are: {self.who}")
        if self.goals:
            sections.append(f"Goals: {self.goals}")
        if self.dreams:
            sections.append(f"Dreams: {self.dreams}")
        if self.skills_and_abilities:
            sections.append(f"Skills and abilities: {self.skills_and_abilities}")
        if self.current_situation:
            sections.append(f"Current situation: {self.current_situation}")
        if self.principles:
            sections.append(f"Principles: {self.principles}")
        if self.successes:
            sections.append(f"Successes: {self.successes}")
        if self.failures:
            sections.append(f"Failures: {self.failures}")
        if self.action_history:
            sections.append(f"Action history: {self.action_history}")
        if self.ideas:
            sections.append(f"Ideas: {self.ideas}")
        return "\n".join(sections) if sections else ""
