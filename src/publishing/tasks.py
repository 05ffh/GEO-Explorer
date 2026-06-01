"""Publishing Celery tasks — async webhook delivery with TaskState integration (P2-4)."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.celery_app import app as celery_app
from src.config import settings
from src.models.task_state import TaskState

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@celery_app.task(bind=True, max_retries=1, acks_late=True, soft_time_limit=120, time_limit=180)
def publish_delivery_task(self, publish_request_id: str, publish_batch_id: str,
                           webhook_secret: str = ""):
    """Async task: deliver a PublishRequest to its webhook target."""

    async def _run():
        async with SessionLocal() as db:
            # Check TaskState
            task_state_id = None
            existing_ts = (await db.execute(
                select(TaskState).where(TaskState.celery_task_id == self.request.id)
            )).scalar_one_or_none()

            if existing_ts:
                task_state_id = str(existing_ts.id)
                existing_ts.status = "running"
                existing_ts.started_at = datetime.now(timezone.utc)
            else:
                # Create TaskState
                ts = TaskState(
                    celery_task_id=self.request.id,
                    task_name="publish_delivery",
                    queue_name="geo_default",
                    routing_key="publish",
                    operation_type="webhook_delivery",
                    trigger_type="auto",
                    organization_id=uuid.uuid4(),  # populated from request
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(ts)
                await db.flush()
                task_state_id = str(ts.id)

            # Link TaskState to PublishRequest
            await db.execute(text(
                "UPDATE publish_requests SET task_state_id = :tsid WHERE id = :rid"
            ), {"tsid": task_state_id, "rid": uuid.UUID(publish_request_id)})

            # Execute delivery
            from src.publishing.delivery import execute_publish_request
            result = await execute_publish_request(
                db, uuid.UUID(publish_request_id),
                webhook_secret=webhook_secret,
                task_state_id=task_state_id,
            )

            # Update TaskState
            if result.get("status") == "error":
                existing_ts = await db.get(TaskState, uuid.UUID(task_state_id)) if task_state_id else None
                if existing_ts:
                    existing_ts.status = "failed"
                    existing_ts.completed_at = datetime.now(timezone.utc)
            elif result.get("attempt", {}).get("status") == "success":
                existing_ts = await db.get(TaskState, uuid.UUID(task_state_id)) if task_state_id else None
                if existing_ts:
                    existing_ts.status = "completed"
                    existing_ts.completed_at = datetime.now(timezone.utc)

            await db.commit()
            return result

    return asyncio.run(_run())


def enqueue_publish_request(publish_request_id: str, publish_batch_id: str,
                             webhook_secret: str = "") -> dict:
    """Enqueue a PublishRequest for async delivery. Returns task info."""
    task = publish_delivery_task.delay(
        publish_request_id=str(publish_request_id),
        publish_batch_id=str(publish_batch_id),
        webhook_secret=webhook_secret,
    )
    return {"task_id": task.id, "status": "queued"}
