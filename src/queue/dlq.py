"""Dead Letter Queue — policy-based requeue with backoff."""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from src.celery_app import app
from src.config import settings
from src.models.task_state import TaskState
from src.database import async_session_factory

logger = logging.getLogger(__name__)

DLQ_BACKOFF_SCHEDULE = [300, 900, 1800]  # 5min, 15min, 30min
MAX_DLQ_AGE_HOURS = 24


def get_dlq_retry_policy(error_type: str) -> str:
    """Map error type to DLQ policy."""
    from src.queue.retry import RETRYABLE_ERRORS, NON_RETRYABLE_ERRORS
    if error_type in RETRYABLE_ERRORS:
        return "auto"
    if error_type in NON_RETRYABLE_ERRORS:
        return "never"
    return "manual"


def get_dlq_backoff(requeue_count: int) -> int:
    """Get backoff seconds for the Nth requeue."""
    if requeue_count < len(DLQ_BACKOFF_SCHEDULE):
        return DLQ_BACKOFF_SCHEDULE[requeue_count]
    return DLQ_BACKOFF_SCHEDULE[-1]


async def move_to_dlq(ts: TaskState, error_type: str, reason: str):
    """Move a failed task to DLQ with policy assignment."""
    policy = get_dlq_retry_policy(error_type)
    now = datetime.now(timezone.utc)
    backoff = get_dlq_backoff(ts.dlq_requeue_count)

    ts.status = "dead_lettered"
    ts.dlq_reason = reason
    ts.dlq_at = now
    ts.dlq_retry_policy = policy
    ts.dlq_backoff_seconds = backoff
    ts.next_requeue_at = now + timedelta(seconds=backoff) if policy == "auto" else None

    # Audit log
    from src.services.audit import add_audit_log
    await add_audit_log(
        None, None,
        action="task_dead_lettered",
        target_type="task_state",
        target_id=str(ts.id),
        reason=f"DLQ[{policy}]: {reason} (task: {ts.celery_task_id})",
    )


async def requeue_dlq_task(ts: TaskState) -> TaskState | None:
    """Requeue a DLQ task — creates a NEW TaskState with parent linking.

    Returns the new TaskState, or None if the task type is unknown.
    """
    task = app.tasks.get(ts.task_name)
    if not task:
        logger.error(f"Unknown task type for DLQ requeue: {ts.task_name}")
        return None

    from src.queue.lifecycle import TaskLifecycle

    async with async_session_factory() as db:
        lc = TaskLifecycle(db)

        now = datetime.now(timezone.utc)
        new_celery_id = f"{ts.celery_task_id}_r{ts.dlq_requeue_count + 1}"

        new_ts = await lc.create(
            celery_task_id=new_celery_id,
            task_name=ts.task_name,
            organization_id=ts.organization_id,
            brand_id=ts.brand_id,
            collection_run_id=ts.collection_run_id,
            operation_type=ts.operation_type,
            trigger_type="retry",
            args=ts.args_json,
            kwargs=ts.kwargs_json,
            queue_name=ts.queue_name,
            routing_key=ts.routing_key,
            priority=ts.priority + 1,  # slightly lower
            max_retries=ts.max_retries,
            root_task_id=ts.root_task_id,
            parent_task_state_id=ts.id,
        )
        new_ts.dlq_requeue_count = ts.dlq_requeue_count + 1
        new_ts.dlq_max_requeues = ts.dlq_max_requeues

        # Mark original as requeued
        ts.status = "requeued"

        await db.commit()

        # Enqueue
        task.apply_async(
            args=ts.args_json or [],
            kwargs=ts.kwargs_json or {},
            task_id=new_celery_id,
            queue=ts.queue_name or "geo_default",
            routing_key=ts.routing_key or "default",
            priority=ts.priority + 1,
        )

        logger.info(f"DLQ requeued: {ts.celery_task_id} -> {new_celery_id}")
        return new_ts


async def mark_dlq_terminal(ts: TaskState):
    """Mark a DLQ task as permanently failed."""
    ts.dlq_retry_policy = "never"
    ts.dlq_max_requeues = 0


# -- Celery Beat task ---------------------------------------------------------

@app.task(bind=True, max_retries=0)
def dlq_monitor_task(self):
    """Periodic: scan DLQ for auto-retriable tasks and requeue them."""
    import asyncio

    async def _run():
        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(hours=MAX_DLQ_AGE_HOURS)

            stmt = select(TaskState).where(
                TaskState.status == "dead_lettered",
                TaskState.dlq_retry_policy == "auto",
                TaskState.dlq_requeue_count < TaskState.dlq_max_requeues,
                TaskState.next_requeue_at <= now,
                TaskState.dlq_at > cutoff,
            ).limit(50)

            results = (await db.execute(stmt)).scalars().all()
            requeued = 0
            for ts in results:
                new_ts = await requeue_dlq_task(ts)
                if new_ts:
                    requeued += 1

            if requeued:
                logger.info(f"DLQ monitor: {requeued} tasks auto-requeued")
            return {"requeued": requeued}

    return asyncio.run(_run())
