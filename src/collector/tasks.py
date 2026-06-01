"""Celery tasks with full lifecycle — manual retry, DLQ, idempotency, circuit breaker."""
import asyncio
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select
from celery import signals

from src.celery_app import app
from src.config import settings
from src.collector.engine import run_collection
from src.collector.gt_collector import collect_gt_candidate
from src.models.brand import Brand
from src.models.task_state import TaskState
from src.queue.retry import classify_error, get_retry_delay
from src.queue.lifecycle import TaskLifecycle
from src.queue.idempotency import release as idem_release
from src.queue.control import check_cancel_signal, clear_cancel_signal
from src.queue.circuit_breaker import check as circuit_check, record_success, record_failure

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def _load_task_state(db, celery_task_id: str) -> TaskState | None:
    result = await db.execute(
        select(TaskState).where(TaskState.celery_task_id == celery_task_id)
    )
    return result.scalar_one_or_none()


async def _create_collection_run(db, brand_id: str, org_id: str, trigger_type: str):
    """Get or create a CollectionRun for this task."""
    from src.models.collection_run import CollectionRun
    cr = CollectionRun(
        organization_id=uuid.UUID(org_id),
        brand_id=uuid.UUID(brand_id),
        trigger_type=trigger_type,
        collection_status="running",
        started_at=datetime.now(timezone.utc),
    )
    db.add(cr)
    await db.flush()
    return cr


# ── collect_brand_task ──────────────────────────────────────────────────────

@app.task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True,
          soft_time_limit=900, time_limit=1200)
def collect_brand_task(self, brand_id: str, org_id: str,
                        operation_type: str = "full_collect",
                        trigger_type: str = "manual",
                        force: bool = False):
    async def _run():
        async with SessionLocal() as db:
            lc = TaskLifecycle(db)
            ts = await _load_task_state(db, self.request.id)

            if not ts:
                logger.error(f"TaskState not found for {self.request.id}")
                return {"status": "error", "detail": "TaskState not found"}

            worker_id = self.request.hostname or "unknown"

            # 1. Cancel check (before we do anything expensive)
            if await check_cancel_signal(self.request.id):
                await lc.transition(ts, "cancelled", "任务在启动前被取消")
                return {"status": "cancelled"}

            # 2. Execution lock
            if not await lc.acquire_execution_lock(ts, worker_id):
                logger.warning(f"Execution lock failed for {self.request.id}")
                # If force, try to take stale lock
                await lc.transition(ts, "duplicate", "任务已在其他 worker 执行中")
                return {"status": "duplicate"}

            # 3. Start
            await lc.transition(ts, "running", f"Worker {worker_id} 开始执行")

            # 4. CollectionRun
            if not ts.collection_run_id:
                cr = await _create_collection_run(db, brand_id, org_id, trigger_type)
                ts.collection_run_id = cr.id
                await db.commit()

            try:
                # 5. Progress callback
                async def progress_cb(pct: float, msg: str):
                    await lc.update_progress(ts, pct, msg)
                    # Heartbeat on each progress update
                    await lc.heartbeat(ts)

                # 6. Run collection — engine handles V2 via COLLECTOR_V2_ENABLED
                result = await run_collection(
                    uuid.UUID(brand_id), uuid.UUID(org_id), db,
                    trigger_type=trigger_type,
                )

                # 7. Success
                await lc.transition(ts, "completed", "采集完成",
                                     metadata={"collection_run_id": str(result.id) if result else None})
                await lc.release_execution_lock(ts)
                await clear_cancel_signal(self.request.id)
                if ts.idempotency_key:
                    await idem_release(ts.idempotency_key)
                await db.commit()

                # Record platform successes
                for platform in ["deepseek", "kimi", "doubao", "wenxin"]:
                    await record_success(platform, org_id)

                return {"status": "completed", "collection_run_id": str(result.id) if result else None}

            except Exception as exc:
                from billiard.exceptions import SoftTimeLimitExceeded
                if isinstance(exc, SoftTimeLimitExceeded):
                    ts.error_type = "soft_timeout"
                    ts.error_message = "Celery soft time limit exceeded — partial results saved"
                    await lc.transition(ts, "timeout", "Soft time limit exceeded")
                    await db.commit()
                    raise

                error_type, retry_policy = classify_error(exc)
                ts.error_type = error_type
                ts.error_message = str(exc)[:2000]
                ts.retry_count = self.request.retries

                # Record circuit breaker failure
                await record_failure(
                    _guess_platform_from_error(str(exc)), error_type, org_id,
                )

                if retry_policy == "retry" and self.request.retries < self.max_retries:
                    delay = get_retry_delay(self.request.retries)
                    ts.next_retry_at = datetime.fromtimestamp(
                        datetime.now(timezone.utc).timestamp() + delay, tz=timezone.utc,
                    )
                    await lc.transition(ts, "retrying",
                                         f"重试 {self.request.retries + 1}/{self.max_retries}: {error_type}")
                    await db.commit()
                    raise self.retry(exc=exc, countdown=delay)

                # DLQ
                await lc.transition(ts, "failed", f"{error_type}: {str(exc)[:500]}")
                from src.queue.dlq import move_to_dlq
                await move_to_dlq(ts, error_type, str(exc)[:500])
                await lc.release_execution_lock(ts)
                await clear_cancel_signal(self.request.id)
                if ts.idempotency_key:
                    await idem_release(ts.idempotency_key)
                await db.commit()
                raise

    return asyncio.run(_run())


# ── collect_gt_task ─────────────────────────────────────────────────────────

@app.task(bind=True, max_retries=3, acks_late=True, reject_on_worker_lost=True,
          soft_time_limit=600, time_limit=900)
def collect_gt_task(self, brand_id: str, org_id: str, force: bool = False):
    async def _run():
        async with SessionLocal() as db:
            lc = TaskLifecycle(db)
            ts = await _load_task_state(db, self.request.id)

            if not ts:
                logger.error(f"TaskState not found for {self.request.id}")
                return {"status": "error", "detail": "TaskState not found"}

            worker_id = self.request.hostname or "unknown"

            if await check_cancel_signal(self.request.id):
                await lc.transition(ts, "cancelled", "任务在启动前被取消")
                return {"status": "cancelled"}

            if not await lc.acquire_execution_lock(ts, worker_id):
                await lc.transition(ts, "duplicate", "任务已在其他 worker 执行中")
                return {"status": "duplicate"}

            await lc.transition(ts, "running", f"Worker {worker_id} 开始执行")

            if not ts.collection_run_id:
                cr = await _create_collection_run(db, brand_id, org_id, "manual")
                ts.collection_run_id = cr.id
                await db.commit()

            try:
                candidate = await collect_gt_candidate(brand_id, org_id, db)

                await lc.transition(ts, "completed", "GT采集完成",
                                     metadata={"candidate_id": str(candidate.id),
                                               "confidence": candidate.overall_confidence})
                await lc.release_execution_lock(ts)
                await clear_cancel_signal(self.request.id)
                if ts.idempotency_key:
                    await idem_release(ts.idempotency_key)
                await db.commit()

                for platform in ["deepseek", "kimi", "doubao", "wenxin"]:
                    await record_success(platform, org_id)

                return {"candidate_id": str(candidate.id), "confidence": candidate.overall_confidence}

            except Exception as exc:
                error_type, retry_policy = classify_error(exc)
                ts.error_type = error_type
                ts.error_message = str(exc)[:2000]
                ts.retry_count = self.request.retries

                await record_failure(
                    _guess_platform_from_error(str(exc)), error_type, org_id,
                )

                if retry_policy == "retry" and self.request.retries < self.max_retries:
                    delay = get_retry_delay(self.request.retries)
                    ts.next_retry_at = datetime.fromtimestamp(
                        datetime.now(timezone.utc).timestamp() + delay, tz=timezone.utc,
                    )
                    await lc.transition(ts, "retrying",
                                         f"重试 {self.request.retries + 1}/{self.max_retries}: {error_type}")
                    await db.commit()
                    raise self.retry(exc=exc, countdown=delay)

                await lc.transition(ts, "failed", f"{error_type}: {str(exc)[:500]}")
                from src.queue.dlq import move_to_dlq
                await move_to_dlq(ts, error_type, str(exc)[:500])
                await lc.release_execution_lock(ts)
                await clear_cancel_signal(self.request.id)
                if ts.idempotency_key:
                    await idem_release(ts.idempotency_key)
                await db.commit()
                raise

    return asyncio.run(_run())


# ── weekly_collect ──────────────────────────────────────────────────────────

@app.task(bind=True, max_retries=2, acks_late=True, reject_on_worker_lost=True,
          soft_time_limit=1800, time_limit=2400)
def weekly_collect(self):
    async def _run():
        async with SessionLocal() as db:
            lc = TaskLifecycle(db)
            celery_task_id = self.request.id

            from src.models.brand import Brand
            brands = (await db.execute(select(Brand))).scalars().all()
            if not brands:
                return "no brands found"

            for brand in brands:
                try:
                    brand_celery_id = f"{celery_task_id}_{brand.id}"
                    ts = await lc.create(
                        celery_task_id=brand_celery_id,
                        task_name="src.collector.tasks.weekly_collect",
                        organization_id=brand.organization_id,
                        brand_id=brand.id,
                        operation_type="full_collect",
                        trigger_type="scheduled",
                        args=[str(brand.id), str(brand.organization_id)],
                    )
                    await db.commit()

                    await lc.transition(ts, "running", f"定时采集: {brand.name}")
                    await run_collection(
                        brand.id, brand.organization_id, db,
                        trigger_type="scheduled",
                    )
                    await lc.transition(ts, "completed", f"定时采集完成: {brand.name}")

                except Exception as exc:
                    logger.error(f"Weekly collect failed for {brand.id}: {exc}")

            return f"collected {len(brands)} brands"

    return asyncio.run(_run())


# ── helpers ─────────────────────────────────────────────────────────────────

def _guess_platform_from_error(error_str: str) -> str:
    """Rough platform guess from error message for circuit breaker."""
    lower = error_str.lower()
    if "kimi" in lower or "moonshot" in lower:
        return "kimi"
    if "deepseek" in lower:
        return "deepseek"
    if "doubao" in lower or "volces" in lower:
        return "doubao"
    if "wenxin" in lower or "baidu" in lower:
        return "wenxin"
    return "unknown"
