"""Task lifecycle manager — create, transition, lock, heartbeat, progress, sync."""
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import text, update, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models.task_state import TaskState, TaskEvent, TASK_STATUS_TRANSITIONS

logger = logging.getLogger(__name__)

EXECUTION_LOCK_TTL = 600    # 10 min
HEARTBEAT_INTERVAL = 60     # 1 min
PROGRESS_MIN_DELTA = 0.05   # 5%
PROGRESS_MIN_INTERVAL = 5   # seconds


class TaskLifecycle:
    """Centralized lifecycle operations with conditional updates and throttling."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -- create ---------------------------------------------------------------

    async def create(self, *, celery_task_id: str, task_name: str,
                     organization_id: uuid.UUID, brand_id: uuid.UUID | None = None,
                     collection_run_id: uuid.UUID | None = None,
                     operation_type: str = "", trigger_type: str = "manual",
                     args: list | None = None, kwargs: dict | None = None,
                     queue_name: str = "geo_default", routing_key: str = "default",
                     priority: int = 5, max_retries: int = 3,
                     idempotency_key: str | None = None,
                     root_task_id: str | None = None,
                     parent_task_state_id: uuid.UUID | None = None,
                     timeout_at: datetime | None = None) -> TaskState:
        ts = TaskState(
            celery_task_id=celery_task_id,
            root_task_id=root_task_id or celery_task_id,
            parent_task_state_id=parent_task_state_id,
            task_name=task_name,
            queue_name=queue_name,
            routing_key=routing_key,
            priority=priority,
            organization_id=organization_id,
            brand_id=brand_id,
            collection_run_id=collection_run_id,
            operation_type=operation_type,
            trigger_type=trigger_type,
            args_json=args or [],
            kwargs_json=kwargs or {},
            payload_hash="",
            idempotency_key=idempotency_key,
            status="queued",
            max_retries=max_retries,
            queued_at=datetime.now(timezone.utc),
            timeout_at=timeout_at,
        )
        self.db.add(ts)
        await self.db.flush()
        return ts

    # -- transition -----------------------------------------------------------

    async def transition(self, ts: TaskState, new_status: str, message: str = "",
                         metadata: dict | None = None,
                         created_by: uuid.UUID | None = None) -> bool:
        """Conditional UPDATE: only succeeds if ts.status is in allowed from-states."""
        allowed = TASK_STATUS_TRANSITIONS.get(ts.status, set())
        if new_status not in allowed:
            logger.warning(
                f"Invalid transition: {ts.status} -> {new_status} "
                f"(task {ts.celery_task_id})"
            )
            return False

        old_status = ts.status
        now = datetime.now(timezone.utc)

        # Conditional update — verify no race by checking old status exists
        verify = await self.db.execute(
            select(TaskState.id).where(TaskState.id == ts.id, TaskState.status == old_status)
        )
        if not verify.scalar_one_or_none():
            logger.warning(
                f"Transition race: {ts.celery_task_id} status already changed from {old_status}"
            )
            return False

        stmt = (
            update(TaskState)
            .where(TaskState.id == ts.id, TaskState.status == old_status)
            .values(status=new_status, version=TaskState.version + 1)
        )
        await self.db.execute(stmt)

        # Update timing fields
        ts.status = new_status
        ts.version += 1
        if new_status == "running" and not ts.started_at:
            ts.started_at = now
        elif new_status == "completed":
            ts.completed_at = now
            ts.progress = 1.0

        # Write event
        await self._write_event(ts, "status_changed", old_status, new_status, message,
                                metadata, created_by)

        # Sync CollectionRun
        await self._sync_collection_run(ts)

        logger.info(f"Task {ts.celery_task_id}: {old_status} -> {new_status}")
        return True

    # -- execution lock -------------------------------------------------------

    async def acquire_execution_lock(self, ts: TaskState, worker_id: str) -> bool:
        """Try to acquire DB-level execution lock. Returns False if already locked."""
        now = datetime.now(timezone.utc)
        expiry = datetime.fromtimestamp(now.timestamp() + EXECUTION_LOCK_TTL, tz=timezone.utc)

        stmt = (
            update(TaskState)
            .where(
                TaskState.id == ts.id,
                TaskState.status == "queued",
                TaskState.execution_lock_owner.is_(None),
            )
            .values(
                execution_lock_owner=worker_id,
                execution_lock_acquired_at=now,
                execution_lock_expires_at=expiry,
                heartbeat_at=now,
            )
        )
        result = await self.db.execute(stmt)
        if result.rowcount:
            ts.execution_lock_owner = worker_id
            ts.execution_lock_acquired_at = now
            ts.execution_lock_expires_at = expiry
            ts.heartbeat_at = now
            return True

        # Check if lock is stale (expired)
        stale = await self.db.execute(
            select(TaskState).where(
                TaskState.id == ts.id,
                TaskState.execution_lock_expires_at < now,
            )
        )
        stale_ts = stale.scalar_one_or_none()
        if stale_ts:
            logger.warning(f"Recovering stale lock for {ts.celery_task_id}")
            ts.execution_lock_owner = worker_id
            ts.execution_lock_acquired_at = now
            ts.execution_lock_expires_at = expiry
            ts.heartbeat_at = now
            return True
        return False

    async def release_execution_lock(self, ts: TaskState):
        ts.execution_lock_owner = None
        ts.execution_lock_acquired_at = None
        ts.execution_lock_expires_at = None
        ts.heartbeat_at = None

    async def heartbeat(self, ts: TaskState):
        now = datetime.now(timezone.utc)
        ts.heartbeat_at = now
        ts.execution_lock_expires_at = datetime.fromtimestamp(
            now.timestamp() + EXECUTION_LOCK_TTL, tz=timezone.utc,
        )

    # -- progress -------------------------------------------------------------

    async def update_progress(self, ts: TaskState, pct: float, message: str = ""):
        """Throttled progress update: >=5% delta or >5s since last write."""
        now = datetime.now(timezone.utc)
        last = ts.last_progress_update_at
        delta = abs(pct - ts.progress)

        if delta < PROGRESS_MIN_DELTA and last and (now - last).total_seconds() < PROGRESS_MIN_INTERVAL:
            return  # skip

        ts.progress = max(0.0, min(1.0, pct))
        ts.progress_message = message
        ts.last_progress_update_at = now

    # -- events ---------------------------------------------------------------

    async def _write_event(self, ts: TaskState, event_type: str,
                           old_status: str | None, new_status: str | None,
                           message: str, metadata: dict | None = None,
                           created_by: uuid.UUID | None = None):
        evt = TaskEvent(
            task_state_id=ts.id,
            organization_id=ts.organization_id,
            event_type=event_type,
            old_status=old_status,
            new_status=new_status,
            message=message,
            metadata_json=metadata or {},
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(evt)

    # -- CollectionRun sync ---------------------------------------------------

    async def _sync_collection_run(self, ts: TaskState):
        if not ts.collection_run_id:
            return
        status_map = {
            "queued": "pending",
            "running": "running",
            "retrying": "running",
            "completed": "completed",
            "failed": "failed",
            "dead_lettered": "failed",
            "cancelled": "cancelled",
            "blocked": "pending",
            "enqueue_failed": "failed",
        }
        cr_status = status_map.get(ts.status, "pending")
        await self.db.execute(
            text("UPDATE collection_runs SET collection_status=:s, updated_at=now() WHERE id=:id"),
            {"s": cr_status, "id": ts.collection_run_id},
        )
