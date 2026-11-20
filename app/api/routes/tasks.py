import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session, get_redis
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.task import TaskCreate, TaskList, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


def cache_key(owner_id: uuid.UUID, task_id: uuid.UUID) -> str:
    return f"task:{owner_id}:{task_id}"


async def owned_task(session: AsyncSession, task_id: uuid.UUID, owner_id: uuid.UUID) -> Task:
    task = await session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> Task:
    task = Task(**payload.model_dump(), owner_id=current_user.id)
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=TaskList)
async def list_tasks(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> TaskList:
    condition = Task.owner_id == current_user.id
    if task_status is not None:
        condition = condition & (Task.status == task_status)
    total = await session.scalar(select(func.count()).select_from(Task).where(condition))
    rows = await session.scalars(
        select(Task).where(condition).order_by(Task.created_at.desc()).offset(skip).limit(limit)
    )
    return TaskList(items=list(rows), total=total or 0)


@router.get("/{task_id}", response_model=TaskRead)
async def read_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    key = cache_key(current_user.id, task_id)
    cached = await redis.get(key)
    if cached:
        return TaskRead.model_validate_json(cached)
    task = await owned_task(session, task_id, current_user.id)
    result = TaskRead.model_validate(task)
    await redis.set(key, result.model_dump_json(), ex=300)
    return result


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> Task:
    task = await owned_task(session, task_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    await redis.delete(cache_key(current_user.id, task_id))
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    current_user: User = Depends(get_current_user),
) -> Response:
    task = await owned_task(session, task_id, current_user.id)
    await session.delete(task)
    await session.commit()
    await redis.delete(cache_key(current_user.id, task_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
