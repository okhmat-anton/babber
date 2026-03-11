"""
Thinking Protocols API — CRUD for step-by-step agent reasoning workflows.

Protocol types:
  standard     — a regular reasoning protocol (analysis, research, etc.)
  orchestrator — a meta-protocol that selects and delegates to child protocols

Step types:
  action   — single instruction to execute
  loop     — repeat nested steps up to max_iterations
  decision — evaluate condition and optionally exit loop
  delegate — select and run a child protocol (orchestrator only)
  todo     — create a structured task list and follow it step by step
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models import MongoThinkingProtocol
from app.mongodb.services import ThinkingProtocolService
from app.services.response_styles import get_response_styles_list, RESPONSE_STYLES

router = APIRouter(prefix="/api/protocols", tags=["thinking-protocols"], dependencies=[Depends(get_current_user)])

# ---------- Schemas ----------

STEP_TYPES = ("action", "loop", "decision", "delegate", "todo")
CATEGORIES = ("analysis", "planning", "execution", "verification", "output", "other")
PROTOCOL_TYPES = ("standard", "orchestrator", "loop")


class StepBase(BaseModel):
    id: str | None = None
    type: Literal["action", "loop", "decision", "delegate", "todo"] = "action"
    name: str = ""
    instruction: str = ""
    category: str = "other"
    # loop-specific
    max_iterations: int | None = None
    exit_condition: str | None = None
    steps: list["StepBase"] = []     # nested steps for loops
    # delegate-specific
    protocol_ids: list[str] = []     # candidate child protocol IDs to choose from

StepBase.model_rebuild()


class ProtocolCreate(BaseModel):
    name: str
    description: str = ""
    type: str = "standard"  # standard, orchestrator
    steps: list[StepBase] = []
    response_style: str | None = None  # humanized, formal, casual, technical, concise, creative, academic


class ProtocolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    steps: list[StepBase] | None = None
    response_style: str | None = None


class ProtocolResponse(BaseModel):
    id: str
    name: str
    description: str
    type: str
    steps: list
    response_style: str | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- Helpers ----------

def _assign_ids(steps: list[dict], prefix: str = "s") -> list[dict]:
    """Ensure every step has a unique id."""
    for i, step in enumerate(steps):
        if not step.get("id"):
            step["id"] = f"{prefix}_{i}_{uuid.uuid4().hex[:6]}"
        if step.get("steps"):
            step["steps"] = _assign_ids(step["steps"], prefix=step["id"])
    return steps


def _to_response(p: MongoThinkingProtocol) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description or "",
        "type": p.type or "standard",
        "steps": p.steps or [],
        "response_style": p.response_style,
        "is_default": p.is_default,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


# ---------- Endpoints ----------

@router.get("/response-styles")
async def list_response_styles():
    """Return available response style presets for protocol configuration."""
    return get_response_styles_list()


@router.get("")
async def list_protocols(db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    protocol_service = ThinkingProtocolService(db)
    protos = await protocol_service.get_all(skip=0, limit=1000)
    # Sort client-side: is_default desc, then name asc
    protos = sorted(protos, key=lambda p: (not p.is_default, p.name))
    return [_to_response(p) for p in protos]


@router.get("/{protocol_id}")
async def get_protocol(protocol_id: str, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    protocol_service = ThinkingProtocolService(db)
    p = await protocol_service.get_by_id(protocol_id)
    if not p:
        raise HTTPException(404, "Protocol not found")
    return _to_response(p)


@router.post("", status_code=201)
async def create_protocol(body: ProtocolCreate, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    protocol_service = ThinkingProtocolService(db)
    steps_raw = [s.model_dump() for s in body.steps]
    steps_raw = _assign_ids(steps_raw)
    p = MongoThinkingProtocol(
        name=body.name,
        description=body.description,
        type=body.type if body.type in PROTOCOL_TYPES else "standard",
        steps=steps_raw,
        response_style=body.response_style if body.response_style in RESPONSE_STYLES else None,
    )
    created = await protocol_service.create(p)
    return _to_response(created)


@router.put("/{protocol_id}")
async def update_protocol(protocol_id: str, body: ProtocolUpdate, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    protocol_service = ThinkingProtocolService(db)
    p = await protocol_service.get_by_id(protocol_id)
    if not p:
        raise HTTPException(404, "Protocol not found")
    
    update_data = {}
    if body.name is not None:
        update_data["name"] = body.name
    if body.description is not None:
        update_data["description"] = body.description
    if body.type is not None and body.type in PROTOCOL_TYPES:
        update_data["type"] = body.type
    if body.steps is not None:
        steps_raw = [s.model_dump() for s in body.steps]
        steps_raw = _assign_ids(steps_raw)
        update_data["steps"] = steps_raw
    if body.response_style is not None:
        update_data["response_style"] = body.response_style if body.response_style in RESPONSE_STYLES else None
    
    update_data["updated_at"] = datetime.now(timezone.utc)
    updated = await protocol_service.update(protocol_id, update_data)
    return _to_response(updated)


@router.delete("/{protocol_id}", status_code=204)
async def delete_protocol(protocol_id: str, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    protocol_service = ThinkingProtocolService(db)
    p = await protocol_service.get_by_id(protocol_id)
    if not p:
        raise HTTPException(404, "Protocol not found")
    if p.is_default:
        raise HTTPException(400, "Cannot delete the default protocol")
    await protocol_service.delete(protocol_id)
    return None


@router.post("/{protocol_id}/duplicate")
async def duplicate_protocol(protocol_id: str, db: AsyncIOMotorDatabase = Depends(get_mongodb)):
    protocol_service = ThinkingProtocolService(db)
    p = await protocol_service.get_by_id(protocol_id)
    if not p:
        raise HTTPException(404, "Protocol not found")
    new = MongoThinkingProtocol(
        name=f"{p.name} (copy)",
        description=p.description,
        type=p.type,
        steps=p.steps,
        is_default=False,
    )
    created = await protocol_service.create(new)
    return _to_response(created)
