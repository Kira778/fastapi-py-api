from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.api.deps import get_current_user, get_redis
from app.models.user import User
from app.schemas.task import ExportQueued, ExportStatus
from app.workers.celery_app import celery_app
from app.workers.export_tasks import export_user_tasks

router = APIRouter(prefix="/exports", tags=["exports"])


def owner_key(task_id: str) -> str:
    return f"export-owner:{task_id}"


@router.post("/tasks", response_model=ExportQueued, status_code=status.HTTP_202_ACCEPTED)
async def queue_export(
    redis: Redis = Depends(get_redis), current_user: User = Depends(get_current_user)
) -> ExportQueued:
    result = export_user_tasks.delay(str(current_user.id))
    await redis.set(owner_key(result.id), str(current_user.id), ex=3600)
    return ExportQueued(task_id=result.id)


@router.get("/tasks/{task_id}", response_model=ExportStatus)
async def get_export(
    task_id: str, redis: Redis = Depends(get_redis), current_user: User = Depends(get_current_user)
) -> ExportStatus:
    owner = await redis.get(owner_key(task_id))
    if owner is None or owner.decode() != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export task not found")
    result = celery_app.AsyncResult(task_id)
    payload = result.result if result.successful() else None
    return ExportStatus(task_id=task_id, status=result.status, result=payload)
