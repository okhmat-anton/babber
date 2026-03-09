from pydantic import BaseModel
from uuid import UUID
from datetime import datetime


class SkillCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    description_for_agent: str = ""
    category: str = "general"
    version: str = "1.0.0"
    code: str = ""
    input_schema: dict = {}
    output_schema: dict = {}
    is_shared: bool = False


class SkillUpdate(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    description_for_agent: str | None = None
    category: str | None = None
    version: str | None = None
    code: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    is_shared: bool | None = None
    enabled: bool | None = None


class SkillResponse(BaseModel):
    id: UUID
    name: str
    display_name: str
    description: str
    description_for_agent: str
    category: str
    version: str
    code: str
    input_schema: dict
    output_schema: dict
    is_system: bool
    is_shared: bool
    enabled: bool = True
    author_agent_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ----- Skill Files (filesystem) -----

class SkillFileInfo(BaseModel):
    name: str
    path: str  # relative to skill dir
    is_dir: bool
    size: int = 0
    language: str = "text"


class SkillFileContent(BaseModel):
    path: str
    content: str
    language: str = "text"


class SkillFileWrite(BaseModel):
    path: str
    content: str


class SkillFileCreate(BaseModel):
    path: str
    content: str = ""
    is_dir: bool = False


class SkillFileRename(BaseModel):
    old_path: str
    new_path: str


class AgentSkillCreate(BaseModel):
    skill_id: UUID
    config: dict | None = None


class AgentSkillResponse(BaseModel):
    skill_id: UUID
    agent_id: UUID
    is_enabled: bool
    config: dict | None
    added_at: datetime
    skill: SkillResponse | None = None

    model_config = {"from_attributes": True}
