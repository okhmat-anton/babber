"""MongoDB services for all entities."""
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.mongodb.service_base import BaseMongoService
from app.mongodb.models import (
    MongoUser,
    MongoAgent,
    MongoAgentModel,
    MongoAgentProtocol,
    MongoThinkingProtocol,
    MongoAgentError,
    MongoModelConfig,
    MongoModelRoleAssignment,
    MongoApiKey,
    MongoChatSession,
    MongoChatMessage,
    MongoTask,
    MongoAutonomousRun,
    MongoThinkingLog,
    MongoThinkingStep,
    MongoSystemSetting,
    MongoSkill,
    MongoAgentSkill,
    MongoAgentLog,
    MongoMemory,
    MongoMemoryLink,
    MongoCreatorProfile,
)
from app.mongodb.models.messenger import MongoMessengerAccount, MongoMessengerMessage, MongoMessengerLog
from app.mongodb.models.agent_fact import MongoAgentFact
from app.mongodb.models.research_resource import MongoResearchResource
from app.mongodb.models.watched_video import MongoWatchedVideo


class UserService(BaseMongoService[MongoUser]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "users", MongoUser)
    
    async def get_by_username(self, username: str):
        return await self.find_one({"username": username})


class AgentService(BaseMongoService[MongoAgent]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agents", MongoAgent)

    async def get_by_name(self, name: str):
        return await self.find_one({"name": name})


class AgentModelService(BaseMongoService[MongoAgentModel]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agent_models", MongoAgentModel)

    async def get_by_agent(self, agent_id: str):
        return await self.get_all(filter={"agent_id": agent_id}, limit=100)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class AgentProtocolService(BaseMongoService[MongoAgentProtocol]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agent_protocols", MongoAgentProtocol)

    async def get_by_agent(self, agent_id: str):
        return await self.get_all(filter={"agent_id": agent_id}, limit=100)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class AgentErrorService(BaseMongoService[MongoAgentError]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agent_errors", MongoAgentError)

    async def get_by_agent(self, agent_id: str, limit: int = 100, skip: int = 0):
        return await self.get_all(filter={"agent_id": agent_id}, skip=skip, limit=limit)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class ThinkingProtocolService(BaseMongoService[MongoThinkingProtocol]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "thinking_protocols", MongoThinkingProtocol)


class ModelConfigService(BaseMongoService[MongoModelConfig]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "model_configs", MongoModelConfig)


class ModelRoleAssignmentService(BaseMongoService[MongoModelRoleAssignment]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "model_role_assignments", MongoModelRoleAssignment)


class ApiKeyService(BaseMongoService[MongoApiKey]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "api_keys", MongoApiKey)
    
    async def get_by_key(self, key: str):
        return await self.find_one({"key": key})


class ChatSessionService(BaseMongoService[MongoChatSession]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "chat_sessions", MongoChatSession)

    async def get_by_user(self, user_id: str, filter_extra: dict = None,
                          limit: int = 50, skip: int = 0):
        flt = {"user_id": user_id}
        if filter_extra:
            flt.update(filter_extra)
        return await self.get_all(filter=flt, skip=skip, limit=limit)


class ChatMessageService(BaseMongoService[MongoChatMessage]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "chat_messages", MongoChatMessage)

    async def get_by_session(self, session_id: str, limit: int = 10000):
        return await self.get_all(filter={"session_id": session_id}, limit=limit)

    async def delete_by_session(self, session_id: str):
        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count


class TaskService(BaseMongoService[MongoTask]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "tasks", MongoTask)


class AutonomousRunService(BaseMongoService[MongoAutonomousRun]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "autonomous_runs", MongoAutonomousRun)


class ThinkingLogService(BaseMongoService[MongoThinkingLog]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "thinking_logs", MongoThinkingLog)


class ThinkingStepService(BaseMongoService[MongoThinkingStep]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "thinking_steps", MongoThinkingStep)


class SystemSettingService(BaseMongoService[MongoSystemSetting]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "system_settings", MongoSystemSetting)
    
    async def get_by_key(self, key: str):
        return await self.find_one({"key": key})


class SkillService(BaseMongoService[MongoSkill]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "skills", MongoSkill)
    
    async def get_by_name(self, name: str):
        return await self.find_one({"name": name})


class AgentSkillService(BaseMongoService[MongoAgentSkill]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agent_skills", MongoAgentSkill)
    
    async def get_by_agent(self, agent_id: str):
        """Get all skills for an agent."""
        filter_dict = {"agent_id": agent_id}
        all_skills = await self.get_all(filter=filter_dict, skip=0, limit=1000)
        return all_skills
    
    async def get_by_agent_and_skill(self, agent_id: str, skill_id: str):
        """Get specific agent-skill relationship."""
        return await self.find_one({"agent_id": agent_id, "skill_id": skill_id})


class AgentLogService(BaseMongoService[MongoAgentLog]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agent_logs", MongoAgentLog)

    async def get_by_agent(self, agent_id: str, limit: int = 100, skip: int = 0):
        return await self.get_all(filter={"agent_id": agent_id}, skip=skip, limit=limit)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class MemoryService(BaseMongoService[MongoMemory]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "memories", MongoMemory)

    async def get_by_agent(self, agent_id: str, limit: int = 100, skip: int = 0):
        return await self.get_all(filter={"agent_id": agent_id}, skip=skip, limit=limit)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class MessengerAccountService(BaseMongoService[MongoMessengerAccount]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "messenger_accounts", MongoMessengerAccount)

    async def get_by_agent(self, agent_id: str, limit: int = 50, skip: int = 0):
        return await self.get_all(filter={"agent_id": agent_id}, skip=skip, limit=limit)

    async def get_active(self, platform: str = None):
        filt = {"is_active": True, "is_authenticated": True}
        if platform:
            filt["platform"] = platform
        return await self.get_all(filter=filt, limit=500)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class MessengerMessageService(BaseMongoService[MongoMessengerMessage]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "messenger_messages", MongoMessengerMessage)

    async def get_by_messenger(self, messenger_id: str, limit: int = 100, skip: int = 0):
        cursor = self.collection.find({"messenger_id": messenger_id}).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def get_by_chat(self, messenger_id: str, chat_id: str, limit: int = 50):
        cursor = self.collection.find({"messenger_id": messenger_id, "chat_id": chat_id}).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def count_today(self, messenger_id: str) -> int:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return await self.collection.count_documents({
            "messenger_id": messenger_id,
            "direction": "outgoing",
            "created_at": {"$gte": today.isoformat()}
        })


class MessengerLogService(BaseMongoService[MongoMessengerLog]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "messenger_logs", MongoMessengerLog)

    async def get_by_messenger(self, messenger_id: str, limit: int = 200, skip: int = 0, level: str = None):
        filt = {"messenger_id": messenger_id}
        if level:
            filt["level"] = level
        cursor = self.collection.find(filt).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def get_by_agent(self, agent_id: str, limit: int = 200, skip: int = 0, level: str = None):
        filt = {"agent_id": agent_id}
        if level:
            filt["level"] = level
        cursor = self.collection.find(filt).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def delete_by_messenger(self, messenger_id: str):
        result = await self.collection.delete_many({"messenger_id": messenger_id})
        return result.deleted_count


class MemoryLinkService(BaseMongoService[MongoMemoryLink]):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "memory_links", MongoMemoryLink)

    async def get_by_agent(self, agent_id: str, limit: int = 500, skip: int = 0):
        return await self.get_all(filter={"agent_id": agent_id}, skip=skip, limit=limit)

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class CreatorProfileService(BaseMongoService[MongoCreatorProfile]):
    """Singleton creator profile — one document per system."""
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "creator_profile", MongoCreatorProfile)

    async def get_profile(self) -> MongoCreatorProfile | None:
        """Get the single creator profile (or None)."""
        docs = await self.get_all(limit=1)
        return docs[0] if docs else None

    async def upsert(self, data: dict) -> MongoCreatorProfile:
        """Create or update the creator profile."""
        from datetime import datetime
        existing = await self.get_profile()
        if existing:
            data["updated_at"] = datetime.utcnow().isoformat()
            return await self.update(existing.id, data)
        else:
            profile = MongoCreatorProfile(**data)
            return await self.create(profile)


class AgentFactService(BaseMongoService[MongoAgentFact]):
    """CRUD service for agent facts & hypotheses."""
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "agent_facts", MongoAgentFact)

    async def get_by_agent(self, agent_id: str, fact_type: str = None,
                           verified: bool = None, limit: int = 200, skip: int = 0):
        """Get facts/hypotheses for an agent with optional filters."""
        filt = {"agent_id": agent_id}
        if fact_type:
            filt["type"] = fact_type
        if verified is not None:
            filt["verified"] = verified
        cursor = self.collection.find(filt).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def search_by_text(self, agent_id: str, query: str, limit: int = 20):
        """Simple text search on content field."""
        filt = {
            "agent_id": agent_id,
            "content": {"$regex": query, "$options": "i"},
        }
        cursor = self.collection.find(filt).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def delete_by_agent(self, agent_id: str):
        result = await self.collection.delete_many({"agent_id": agent_id})
        return result.deleted_count


class ResearchResourceService(BaseMongoService[MongoResearchResource]):
    """CRUD service for trusted research resources."""
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "research_resources", MongoResearchResource)

    async def get_by_trust_level(self, min_level: str = "medium", limit: int = 100) -> list:
        """Get active resources with minimum trust level."""
        level_order = {"low": 0, "medium": 1, "high": 2, "highest": 3}
        min_val = level_order.get(min_level, 1)
        allowed = [k for k, v in level_order.items() if v >= min_val]
        filt = {"is_active": True, "trust_level": {"$in": allowed}}
        cursor = self.collection.find(filt).sort("agent_rating", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def get_active(self, category: str = None, limit: int = 100, skip: int = 0) -> list:
        """Get all active resources with optional category filter."""
        filt = {"is_active": True}
        if category:
            filt["category"] = category
        cursor = self.collection.find(filt).sort("user_rating", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def search(self, query: str, limit: int = 50) -> list:
        """Search resources by name, url, or description."""
        filt = {
            "$or": [
                {"name": {"$regex": query, "$options": "i"}},
                {"url": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}},
            ]
        }
        cursor = self.collection.find(filt).sort("user_rating", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def increment_use(self, resource_id: str):
        """Increment use count and set last_used_at."""
        from datetime import datetime, timezone
        await self.collection.update_one(
            {"_id": resource_id},
            {"$inc": {"use_count": 1}, "$set": {"last_used_at": datetime.now(timezone.utc).isoformat()}}
        )


class WatchedVideoService(BaseMongoService[MongoWatchedVideo]):
    """CRUD service for watched video transcripts."""
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db, "watched_videos", MongoWatchedVideo)

    async def get_by_url(self, url: str) -> MongoWatchedVideo | None:
        """Find a watched video by its original URL."""
        return await self.find_one({"url": url})

    async def get_by_platform(self, platform: str, limit: int = 100, skip: int = 0):
        """Get all watched videos for a specific platform."""
        cursor = self.collection.find({"platform": platform}).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def get_by_agent(self, agent_id: str, limit: int = 100, skip: int = 0):
        """Get all watched videos requested by a specific agent."""
        cursor = self.collection.find({"agent_id": agent_id}).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

    async def search(self, query: str, limit: int = 50):
        """Search watched videos by URL, title, or transcript text."""
        filt = {
            "$or": [
                {"url": {"$regex": query, "$options": "i"}},
                {"title": {"$regex": query, "$options": "i"}},
                {"transcript": {"$regex": query, "$options": "i"}},
            ]
        }
        cursor = self.collection.find(filt).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self.model_class.from_mongo(doc) for doc in docs]

