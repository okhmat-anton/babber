"""MongoDB models using Pydantic for document schemas."""
from app.mongodb.models.user import MongoUser
from app.mongodb.models.agent import MongoAgent, MongoAgentModel, MongoAgentProtocol, MongoThinkingProtocol, MongoAgentError
from app.mongodb.models.model_config import MongoModelConfig, MongoModelRoleAssignment  
from app.mongodb.models.api_key import MongoApiKey
from app.mongodb.models.chat import MongoChatSession, MongoChatMessage
from app.mongodb.models.task import MongoTask, MongoAutonomousRun
from app.mongodb.models.thinking_log import MongoThinkingLog, MongoThinkingStep
from app.mongodb.models.system_setting import MongoSystemSetting
from app.mongodb.models.skill import MongoSkill, MongoAgentSkill
from app.mongodb.models.log import MongoAgentLog
from app.mongodb.models.memory import MongoMemory, MongoMemoryLink
from app.mongodb.models.creator_profile import MongoCreatorProfile
from app.mongodb.models.agent_fact import MongoAgentFact
from app.mongodb.models.research_resource import MongoResearchResource

__all__ = [
    "MongoUser",
    "MongoAgent",
    "MongoAgentModel",
    "MongoAgentProtocol",
    "MongoThinkingProtocol",
    "MongoAgentError",
    "MongoModelConfig",
    "MongoModelRoleAssignment",
    "MongoApiKey",
    "MongoChatSession",
    "MongoChatMessage",
    "MongoTask",
    "MongoAutonomousRun",
    "MongoThinkingLog",
    "MongoThinkingStep",
    "MongoSystemSetting",
    "MongoSkill",
    "MongoAgentSkill",
    "MongoAgentLog",
    "MongoMemory",
    "MongoMemoryLink",
    "MongoCreatorProfile",
    "MongoAgentFact",
    "MongoResearchResource",
]
