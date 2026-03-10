"""MongoDB model for Watched Videos — tracks video transcripts fetched via ScrapeCreators."""
import uuid
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class MongoWatchedVideo(BaseModel):
    """Stores a record of a video whose transcript was fetched via ScrapeCreators API."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str  # Original video URL
    platform: str  # youtube, tiktok, instagram, facebook, twitter
    video_id: Optional[str] = None  # Platform-specific video ID
    title: Optional[str] = None
    transcript: Optional[str] = None  # Plain text transcript
    transcript_segments: Optional[List[Dict[str, Any]]] = None  # Timestamped segments (YouTube)
    language: Optional[str] = None
    duration_seconds: Optional[int] = None
    author: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)  # Extra platform-specific data
    agent_id: Optional[str] = None  # Which agent requested the transcript
    category: Optional[str] = None  # User-defined category for grouping
    credits_used: int = 1
    error: Optional[str] = None  # Error message if fetch failed
    # Cross-linking
    linked_fact_ids: List[str] = Field(default_factory=list)
    linked_analysis_ids: List[str] = Field(default_factory=list)
    linked_idea_ids: List[str] = Field(default_factory=list)
    linked_chat_session_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_mongo(self) -> dict:
        """Convert to MongoDB document."""
        doc = self.model_dump()
        doc["_id"] = doc.pop("id")
        doc["created_at"] = doc["created_at"].isoformat()
        return doc

    @classmethod
    def from_mongo(cls, doc: dict) -> "MongoWatchedVideo":
        """Create from MongoDB document."""
        if not doc:
            return None
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("created_at"), str):
            doc["created_at"] = datetime.fromisoformat(doc["created_at"])
        return cls(**doc)
