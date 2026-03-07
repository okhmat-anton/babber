from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from sqlalchemy.orm import selectinload
from app.models.task import Task
from app.models.agent import Agent
from app.schemas.task import TaskCreate, TaskUpdate, TaskResponse
from app.schemas.common import MessageResponse

router = APIRouter(tags=["tasks"])

# ------- Common Tasks -------
common_router = APIRouter(prefix="/api/tasks")


@common_router.get("", response_model=list[TaskResponse])
async def list_tasks(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Task).options(selectinload(Task.agent))
    if status:
        q = q.where(Task.status == status)
    if priority:
        q = q.where(Task.priority == priority)
    q = q.order_by(Task.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    tasks = result.scalars().all()
    return [
        TaskResponse(
            **{c.key: getattr(t, c.key) for c in Task.__table__.columns},
            agent_name=t.agent.name if t.agent else None,
        )
        for t in tasks
    ]


@common_router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    body: TaskCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = Task(**body.model_dump(), agent_id=None)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@common_router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@common_router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    body: TaskUpdate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    await db.flush()
    await db.refresh(task)
    return task


@common_router.delete("/{task_id}", response_model=MessageResponse)
async def delete_task(
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    return MessageResponse(message="Task deleted")


@common_router.post("/{task_id}/run", response_model=TaskResponse)
async def run_task(
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    from datetime import datetime, timezone
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(task)
    return task


@common_router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "cancelled"
    await db.flush()
    await db.refresh(task)
    return task


# ------- Agent Tasks -------
agent_task_router = APIRouter(prefix="/api/agents/{agent_id}/tasks")


async def _get_agent(agent_id: UUID, db: AsyncSession):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@agent_task_router.get("", response_model=list[TaskResponse])
async def list_agent_tasks(
    agent_id: UUID,
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    q = select(Task).where(Task.agent_id == agent_id)
    if status:
        q = q.where(Task.status == status)
    q = q.order_by(Task.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all()


@agent_task_router.post("", response_model=TaskResponse, status_code=201)
async def create_agent_task(
    agent_id: UUID,
    body: TaskCreate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    task = Task(**body.model_dump(), agent_id=agent_id)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


@agent_task_router.get("/{task_id}", response_model=TaskResponse)
async def get_agent_task(
    agent_id: UUID,
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@agent_task_router.put("/{task_id}", response_model=TaskResponse)
async def update_agent_task(
    agent_id: UUID,
    task_id: UUID,
    body: TaskUpdate,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    await db.flush()
    await db.refresh(task)
    return task


@agent_task_router.delete("/{task_id}", response_model=MessageResponse)
async def delete_agent_task(
    agent_id: UUID,
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.delete(task)
    return MessageResponse(message="Task deleted")


@agent_task_router.post("/{task_id}/run", response_model=TaskResponse)
async def run_agent_task(
    agent_id: UUID,
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    from datetime import datetime, timezone
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(task)
    return task


@agent_task_router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_agent_task(
    agent_id: UUID,
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "cancelled"
    await db.flush()
    await db.refresh(task)
    return task


@agent_task_router.post("/{task_id}/decompose", response_model=TaskResponse)
async def decompose_task(
    agent_id: UUID,
    task_id: UUID,
    subtasks: list[TaskCreate],
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Decompose a task into subtasks. Marks parent as decomposed and creates child tasks.
    """
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    parent_task = result.scalar_one_or_none()
    if not parent_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Mark parent as decomposed
    parent_task.is_decomposed = True
    parent_task.status = "decomposed"
    
    # Create child tasks
    for subtask_data in subtasks:
        child_task = Task(
            **subtask_data.model_dump(),
            agent_id=agent_id,
            parent_task_id=task_id
        )
        db.add(child_task)
    
    await db.flush()
    await db.refresh(parent_task)
    return parent_task


@agent_task_router.get("/{task_id}/children", response_model=list[TaskResponse])
async def get_task_children(
    agent_id: UUID,
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all child tasks of a parent task."""
    await _get_agent(agent_id, db)
    q = select(Task).where(Task.parent_task_id == task_id)
    result = await db.execute(q)
    return result.scalars().all()


@agent_task_router.post("/{task_id}/mark-ready", response_model=TaskResponse)
async def mark_task_ready(
    agent_id: UUID,
    task_id: UUID,
    _user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a task as ready to execute (after decomposition or assessment)."""
    await _get_agent(agent_id, db)
    result = await db.execute(select(Task).where(Task.id == task_id, Task.agent_id == agent_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.ready_to_execute = True
    task.status = "pending"  # Reset to pending if it was in assessment
    await db.flush()
    await db.refresh(task)
    return task
