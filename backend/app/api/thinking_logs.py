"""
Thinking Logs API — view detailed agent reasoning traces.

Endpoints:
  GET  /api/agents/{agent_id}/thinking-logs           — list thinking logs for an agent
  GET  /api/agents/{agent_id}/thinking-logs/{log_id}  — get single thinking log with all steps
  GET  /api/chat/sessions/{session_id}/thinking-logs   — list thinking logs for a chat session
  GET  /api/chat/thinking-logs/{log_id}                — get thinking log by ID with all steps
  DELETE /api/agents/{agent_id}/thinking-logs          — clear all thinking logs for an agent
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_mongodb
from app.core.dependencies import get_current_user
from app.mongodb.models import MongoUser, MongoAgent, MongoThinkingLog, MongoThinkingStep
from app.mongodb.services import AgentService, ThinkingLogService, ThinkingStepService
from app.schemas.thinking_log import ThinkingLogResponse, ThinkingLogSummaryResponse

# --- Agent-scoped routes ---
agent_thinking_router = APIRouter(prefix="/api/agents/{agent_id}/thinking-logs", tags=["thinking-logs"])


@agent_thinking_router.get("", response_model=list[ThinkingLogSummaryResponse])
async def list_agent_thinking_logs(
    agent_id: UUID,
    status: str | None = Query(None, description="Filter by status: started, completed, error"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List thinking log summaries for an agent, newest first."""
    agent_service = AgentService(db)
    if not await agent_service.get_by_id(str(agent_id)):
        raise HTTPException(status_code=404, detail="Agent not found")

    thinking_log_service = ThinkingLogService(db)
    thinking_step_service = ThinkingStepService(db)
    
    # Build filter
    filter_dict = {"agent_id": str(agent_id)}
    if status:
        filter_dict["status"] = status
    
    # Get logs and sort client-side (MongoDB returns unsorted by default)
    logs = await thinking_log_service.get_all(filter=filter_dict, skip=offset, limit=limit)
    logs = sorted(logs, key=lambda x: x.created_at, reverse=True)

    # Build summaries with steps_count
    summaries = []
    for log in logs:
        summary = ThinkingLogSummaryResponse.model_validate(log)
        # Count steps from ThinkingStepService
        steps = await thinking_step_service.get_all(filter={"thinking_log_id": log.id}, limit=1000)
        summary.steps_count = len(steps)
        summaries.append(summary)
    return summaries


@agent_thinking_router.get("/{log_id}", response_model=ThinkingLogResponse)
async def get_thinking_log(
    agent_id: UUID,
    log_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a single thinking log with all steps."""
    thinking_log_service = ThinkingLogService(db)
    thinking_step_service = ThinkingStepService(db)
    
    log = await thinking_log_service.get_by_id(str(log_id))
    if not log or log.agent_id != str(agent_id):
        raise HTTPException(status_code=404, detail="Thinking log not found")
    
    # Load steps for the response model
    steps = await thinking_step_service.get_all(filter={"thinking_log_id": log.id}, limit=1000)
    # Attach steps to log object if response model expects it
    log_dict = log.model_dump()
    log_dict["steps"] = [s.model_dump() for s in steps]
    return log_dict


@agent_thinking_router.delete("")
async def clear_agent_thinking_logs(
    agent_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Clear all thinking logs for an agent."""
    agent_service = AgentService(db)
    if not await agent_service.get_by_id(str(agent_id)):
        raise HTTPException(status_code=404, detail="Agent not found")

    thinking_log_service = ThinkingLogService(db)
    thinking_step_service = ThinkingStepService(db)
    
    # Get all thinking logs for this agent
    logs = await thinking_log_service.get_all(filter={"agent_id": str(agent_id)}, limit=10000)
    
    # Delete all steps for these logs
    for log in logs:
        steps = await thinking_step_service.get_all(filter={"thinking_log_id": log.id}, limit=10000)
        for step in steps:
            await thinking_step_service.delete(step.id)
    
    # Delete all logs
    for log in logs:
        await thinking_log_service.delete(log.id)
    
    return {"message": "Thinking logs cleared"}


# --- Session-scoped routes ---
session_thinking_router = APIRouter(prefix="/api/chat/sessions/{session_id}/thinking-logs", tags=["thinking-logs"])


@session_thinking_router.get("", response_model=list[ThinkingLogSummaryResponse])
async def list_session_thinking_logs(
    session_id: UUID,
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """List thinking logs for a chat session, ordered by time."""
    thinking_log_service = ThinkingLogService(db)
    thinking_step_service = ThinkingStepService(db)
    
    logs = await thinking_log_service.get_all(
        filter={"session_id": str(session_id)},
        skip=offset,
        limit=limit
    )
    # Sort client-side by created_at desc
    logs = sorted(logs, key=lambda x: x.created_at, reverse=True)

    summaries = []
    for log in logs:
        summary = ThinkingLogSummaryResponse.model_validate(log)
        steps = await thinking_step_service.get_all(filter={"thinking_log_id": log.id}, limit=1000)
        summary.steps_count = len(steps)
        summaries.append(summary)
    return summaries


# --- Direct thinking log access by ID (used by chat messages with thinking_log_id) ---
chat_thinking_router = APIRouter(prefix="/api/chat/thinking-logs", tags=["thinking-logs"])


@chat_thinking_router.get("/{log_id}", response_model=ThinkingLogResponse)
async def get_thinking_log_by_id(
    log_id: UUID,
    _user: MongoUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_mongodb),
):
    """Get a thinking log with all steps by log ID. Used by chat UI to load thinking details."""
    thinking_log_service = ThinkingLogService(db)
    thinking_step_service = ThinkingStepService(db)

    log = await thinking_log_service.get_by_id(str(log_id))
    if not log:
        raise HTTPException(status_code=404, detail="Thinking log not found")

    steps = await thinking_step_service.get_all(filter={"thinking_log_id": log.id}, limit=1000)
    steps.sort(key=lambda s: s.step_order)
    log_dict = log.model_dump()
    log_dict["steps"] = [s.model_dump() for s in steps]
    return log_dict
