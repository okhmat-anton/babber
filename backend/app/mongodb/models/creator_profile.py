"""MongoDB CreatorProfile model — singleton document for creator/owner context."""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class GoalItem(BaseModel):
    """A single goal with optional sub-goals."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    target_date: Optional[str] = None          # target date (ISO or free-form text)
    children: List["GoalItem"] = Field(default_factory=list)  # sub-goals


class DreamItem(BaseModel):
    """A single dream."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""


class IdeaItem(BaseModel):
    """A single idea."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""


class MongoCreatorProfile(BaseModel):
    """Creator profile — info about the person who manages the bots."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None
    who: Optional[str] = None            # who they are
    goals: List[GoalItem] = Field(default_factory=list)          # goals
    dreams: List[DreamItem] = Field(default_factory=list)        # dreams
    skills_and_abilities: Optional[str] = None  # skills and abilities
    current_situation: Optional[str] = None     # current situation
    principles: Optional[str] = None     # principles
    successes: Optional[str] = None      # successes
    failures: Optional[str] = None       # failures
    action_history: Optional[str] = None # action attempt history
    ideas: List[IdeaItem] = Field(default_factory=list)          # ideas

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
        # Backward compat: old string fields → empty lists
        for field in ("goals", "dreams", "ideas"):
            if isinstance(doc.get(field), str):
                doc[field] = []
        return cls(**doc)

    def to_context_string(self) -> str:
        """Build a human-readable context string for LLM consumption."""
        sections = []
        if self.name:
            sections.append(f"Name: {self.name}")
        if self.who:
            sections.append(f"Who they are: {self.who}")
        if self.goals:
            lines = ["Goals:"]
            for g in self.goals:
                date_part = f" (target: {g.target_date})" if g.target_date else ""
                lines.append(f"  - {g.title}{date_part}")
                if g.description:
                    lines.append(f"    {g.description}")
                for sub in g.children:
                    sd = f" (target: {sub.target_date})" if sub.target_date else ""
                    lines.append(f"    - {sub.title}{sd}")
                    if sub.description:
                        lines.append(f"      {sub.description}")
            sections.append("\n".join(lines))
        if self.dreams:
            lines = ["Dreams:"]
            for d in self.dreams:
                lines.append(f"  - {d.title}")
                if d.description:
                    lines.append(f"    {d.description}")
            sections.append("\n".join(lines))
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
            lines = ["Ideas:"]
            for i in self.ideas:
                lines.append(f"  - {i.title}")
                if i.description:
                    lines.append(f"    {i.description}")
            sections.append("\n".join(lines))
        return "\n".join(sections) if sections else ""
