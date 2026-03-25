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
    priority: int = 1                          # 0=high, 1=medium, 2=low
    scale: str = "medium"                      # big, medium, micro — helps agent understand scope
    completed: bool = False                    # marked as done
    in_context: bool = True                    # included in agent context
    children: List["GoalItem"] = Field(default_factory=list)  # sub-goals


class DreamItem(BaseModel):
    """A single dream."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    priority: int = 1                          # 0=high, 1=medium, 2=low
    completed: bool = False
    in_context: bool = True


class IdeaItem(BaseModel):
    """A single idea."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    priority: int = 1                          # 0=high, 1=medium, 2=low
    completed: bool = False
    in_context: bool = True


class CityItem(BaseModel):
    """A city the creator visits or is interested in (used for weather, travel, etc.)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""           # city name (e.g. "Berlin")
    country: str = ""        # country name or code (e.g. "Germany" or "DE")
    state: str = ""          # state / region (e.g. "Texas", "Bavaria")
    zip_code: str = ""       # zip / postal code
    type: str = "interest"   # home, frequent, interest
    in_context: bool = True


class NoteItem(BaseModel):
    """A single note."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    content: str = ""
    completed: bool = False
    in_context: bool = True
    created_at: Optional[str] = None  # ISO datetime string


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
    notes: List[NoteItem] = Field(default_factory=list)          # notes
    cities: List[CityItem] = Field(default_factory=list)         # cities of interest (weather, travel)

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
        # Backward compat: old string fields or null → empty lists
        for field in ("goals", "dreams", "ideas", "notes", "cities"):
            if not isinstance(doc.get(field), list):
                doc[field] = []
        return cls(**doc)

    def to_context_string(self) -> str:
        """Build a human-readable context string for LLM consumption."""
        priority_labels = {0: "HIGH", 1: "MEDIUM", 2: "LOW"}
        sections = []
        if self.name:
            sections.append(f"Name: {self.name}")
        if self.who:
            sections.append(f"Who they are: {self.who}")
        scale_labels = {"big": "BIG", "medium": "MEDIUM", "micro": "MICRO"}
        if self.goals:
            active_goals = [g for g in self.goals if getattr(g, 'in_context', True) and not getattr(g, 'completed', False)]
            if active_goals:
                lines = ["Goals:"]
                for g in active_goals:
                    date_part = f" (target: {g.target_date})" if g.target_date else ""
                    prio = f" [{priority_labels.get(g.priority, 'MEDIUM')}]"
                    scale = f" ({scale_labels.get(getattr(g, 'scale', 'medium'), 'MEDIUM')} goal)"
                    lines.append(f"  - {g.title}{prio}{scale}{date_part}")
                    if g.description:
                        lines.append(f"    {g.description}")
                    for sub in g.children:
                        if getattr(sub, 'completed', False) or not getattr(sub, 'in_context', True):
                            continue
                        sd = f" (target: {sub.target_date})" if sub.target_date else ""
                        sub_prio = f" [{priority_labels.get(getattr(sub, 'priority', 1), 'MEDIUM')}]"
                        sub_scale = f" ({scale_labels.get(getattr(sub, 'scale', 'medium'), 'MEDIUM')} goal)"
                        lines.append(f"    - {sub.title}{sub_prio}{sub_scale}{sd}")
                        if sub.description:
                            lines.append(f"      {sub.description}")
                sections.append("\n".join(lines))
        if self.dreams:
            active_dreams = [d for d in self.dreams if getattr(d, 'in_context', True) and not getattr(d, 'completed', False)]
            if active_dreams:
                lines = ["Dreams:"]
                for d in active_dreams:
                    prio = f" [{priority_labels.get(d.priority, 'MEDIUM')}]"
                    lines.append(f"  - {d.title}{prio}")
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
            active_ideas = [i for i in self.ideas if getattr(i, 'in_context', True) and not getattr(i, 'completed', False)]
            if active_ideas:
                lines = ["Ideas:"]
                for i in active_ideas:
                    prio = f" [{priority_labels.get(i.priority, 'MEDIUM')}]"
                    lines.append(f"  - {i.title}{prio}")
                    if i.description:
                        lines.append(f"    {i.description}")
                sections.append("\n".join(lines))
        if self.notes:
            active_notes = [n for n in self.notes if getattr(n, 'in_context', True) and not getattr(n, 'completed', False)]
            if active_notes:
                lines = ["Notes:"]
                for n in active_notes:
                    lines.append(f"  - {n.title}")
                    if n.content:
                        lines.append(f"    {n.content}")
                sections.append("\n".join(lines))
        if self.cities:
            active_cities = [c for c in self.cities if getattr(c, 'in_context', True)]
            if active_cities:
                type_labels = {"home": "HOME", "frequent": "FREQUENT", "interest": "INTEREST"}
                lines = ["Cities of interest (for weather, travel, etc.):"]
                for c in active_cities:
                    t = f" [{type_labels.get(c.type, 'INTEREST')}]"
                    country_part = f", {c.country}" if c.country else ""
                    lines.append(f"  - {c.name}{country_part}{t}")
                sections.append("\n".join(lines))
        return "\n".join(sections) if sections else ""
