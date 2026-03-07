"""
MongoDB models using plain dictionaries with validation.
Motor doesn't require ORM - we use Pydantic for validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class MongoTask(BaseModel):
    """Task model for MongoDB storage."""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    agent_id: Optional[UUID] = None
    title: str
    description: str = ""
    type: str = "one_time"  # one_time, recurring, cron
    status: str = "pending"  # pending, running, paused, completed, failed, cancelled
    priority: str = "normal"  # low, normal, high, critical
    schedule: Optional[str] = None
    next_run_at: Optional[datetime] = None  
    max_retries: int = 3
    retry_count: int = 0
    timeout: int = 300
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True  # Allow using both 'id' and '_id'
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }

    def to_mongo(self) -> dict:
        """Convert to MongoDB document format."""
        data = self.model_dump(by_alias=True, exclude_none=False)
        # Convert UUIDs to strings for MongoDB
        if data.get('_id'):
            data['_id'] = str(data['_id'])
        if data.get('agent_id'):
            data['agent_id'] = str(data['agent_id'])
        return data

    @classmethod
    def from_mongo(cls, data: dict) -> "MongoTask":
        """Create instance from MongoDB document."""
        if not data:
            return None
        # Convert string IDs back to UUIDs
        if '_id' in data and isinstance(data['_id'], str):
            data['_id'] = UUID(data['_id'])
        if 'agent_id' in data and isinstance(data['agent_id'], str) and data['agent_id']:
            data['agent_id'] = UUID(data['agent_id'])
        return cls(**data)
