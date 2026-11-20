import asyncio
import csv
import io
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.task import Task
from app.workers.celery_app import celery_app


async def build_csv(user_id: uuid.UUID) -> str:
    async with SessionLocal() as session:
        tasks = list(
            await session.scalars(select(Task).where(Task.owner_id == user_id).order_by(Task.created_at))
        )
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "title", "description", "status", "created_at"])
    for task in tasks:
        writer.writerow([task.id, task.title, task.description or "", task.status, task.created_at.isoformat()])
    return output.getvalue()


@celery_app.task(name="app.workers.export_tasks.export_user_tasks", bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def export_user_tasks(self, user_id: str) -> str:
    return asyncio.run(build_csv(uuid.UUID(user_id)))
