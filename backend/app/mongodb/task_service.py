"""Task service for MongoDB operations."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from motor.motor_asyncio import AsyncIOMotorCollection
from app.database import get_mongodb
from app.mongodb.models import MongoTask


def get_tasks_collection() -> AsyncIOMotorCollection:
    """Get MongoDB tasks collection."""
    db = get_mongodb()
    return db.tasks


async def create_task(task: MongoTask) -> MongoTask:
    """Create a new task in MongoDB."""
    collection = get_tasks_collection()
    task_dict = task.to_mongo()
    await collection.insert_one(task_dict)
    return task


async def get_task_by_id(task_id: UUID) -> Optional[MongoTask]:
    """Get task by ID from MongoDB."""
    collection = get_tasks_collection()
    task_dict = await collection.find_one({"_id": str(task_id)})
    return MongoTask.from_mongo(task_dict) if task_dict else None


async def list_tasks(
    agent_id: Optional[UUID] = None,
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = 100,
    skip: int = 0
) -> list[MongoTask]:
    """List tasks with optional filters."""
    collection = get_tasks_collection()
    
    # Build query
    query = {}
    if agent_id:
        query["agent_id"] = str(agent_id)
    if status:
        query["status"] = status
    if type:
        query["type"] = type
    
    # Execute query
    cursor = collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
    tasks = []
    async for task_dict in cursor:
        task = MongoTask.from_mongo(task_dict)
        if task:
            tasks.append(task)
    return tasks


async def update_task(task_id: UUID, updates: dict) -> Optional[MongoTask]:
    """Update task in MongoDB."""
    collection = get_tasks_collection()
    
    # Add updated_at timestamp
    updates["updated_at"] = datetime.utcnow()
    
    # Convert UUID fields to strings if present
    if "agent_id" in updates and isinstance(updates["agent_id"], UUID):
        updates["agent_id"] = str(updates["agent_id"])
    
    result = await collection.find_one_and_update(
        {"_id": str(task_id)},
        {"$set": updates},
        return_document=True
    )
    return MongoTask.from_mongo(result) if result else None


async def delete_task(task_id: UUID) -> bool:
    """Delete task from MongoDB."""
    collection = get_tasks_collection()
    result = await collection.delete_one({"_id": str(task_id)})
    return result.deleted_count > 0


async def count_tasks(agent_id: Optional[UUID] = None, status: Optional[str] = None) -> int:
    """Count tasks with optional filters."""
    collection = get_tasks_collection()
    
    query = {}
    if agent_id:
        query["agent_id"] = str(agent_id)
    if status:
        query["status"] = status
    
    return await collection.count_documents(query)
