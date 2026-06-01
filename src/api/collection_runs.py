import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database import get_db, async_session
from src.api.deps import get_current_user, get_user_or_api_key, get_org_brand_or_404
from src.models.user import User
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult

logger = logging.getLogger(__name__)
router = APIRouter(tags=["collections"])


@router.post("/api/brands/{brand_id}/collections", status_code=202)
async def trigger_collection(
    brand_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
    force: bool = Query(False),
):
    from src.collector.tasks import collect_brand_task
    from src.queue.lifecycle import TaskLifecycle
    from src.queue.idempotency import (
        build_idempotency_key, build_payload_hash, build_time_bucket, try_acquire,
    )

    brand = await get_org_brand_or_404(brand_id, user, db)

    # Build idempotency
    payload_hash = build_payload_hash([brand_id, str(user.organization_id)], {"trigger_type": "manual"})
    idem_key = build_idempotency_key(
        org_id=str(user.organization_id),
        task_name="collect_brand_task",
        operation_type="full_collect",
        payload_hash=payload_hash,
        time_bucket=build_time_bucket(),
    )

    if not force and not await try_acquire(idem_key):
        # Check if there's an existing task
        from src.models.task_state import TaskState
        existing = (await db.execute(
            select(TaskState).where(
                TaskState.idempotency_key == idem_key,
                TaskState.status.in_(["queued", "running", "retrying"]),
            )
        )).scalar_one_or_none()
        if existing:
            return {
                "task_id": existing.celery_task_id,
                "status": "duplicate",
                "message": "已有相同任务正在执行中",
                "can_force": True,
            }

    # Create TaskState BEFORE apply_async
    celery_task_id = f"collect_{brand_id}_{int(datetime.now(timezone.utc).timestamp())}"
    timeout_at = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + 1200, tz=timezone.utc,
    )

    lc = TaskLifecycle(db)
    ts = await lc.create(
        celery_task_id=celery_task_id,
        task_name="src.collector.tasks.collect_brand_task",
        organization_id=user.organization_id,
        brand_id=uuid.UUID(brand_id),
        operation_type="full_collect",
        trigger_type="manual",
        args=[brand_id, str(user.organization_id)],
        kwargs={"operation_type": "full_collect", "trigger_type": "manual"},
        idempotency_key=idem_key,
        timeout_at=timeout_at,
    )
    await db.commit()

    # Now enqueue — use same celery_task_id
    try:
        task = collect_brand_task.apply_async(
            args=[brand_id, str(user.organization_id)],
            kwargs={"operation_type": "full_collect", "trigger_type": "manual", "force": force},
            task_id=celery_task_id,
        )
        return {
            "task_id": task.id,
            "brand_id": brand_id,
            "status": "queued",
        }
    except Exception as exc:
        logger.error(f"apply_async failed: {exc}")
        # Mark as enqueue_failed
        async with async_session() as s:
            from src.models.task_state import TaskState
            stmt = (await s.execute(select(TaskState).where(TaskState.celery_task_id == celery_task_id))).scalar_one_or_none()
            if stmt:
                stmt.status = "enqueue_failed"
                await s.commit()
        return {"task_id": celery_task_id, "status": "enqueue_failed", "error": str(exc)}


@router.get("/api/brands/{brand_id}/collections")
async def list_collections(
    brand_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    q = select(CollectionRun).where(
        CollectionRun.brand_id == brand_id,
        CollectionRun.organization_id == user.organization_id,
    ).order_by(desc(CollectionRun.created_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}


@router.get("/api/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    run = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.id == collection_id,
            CollectionRun.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not run:
        return {"detail": "Not found"}, 404
    return {"collection": run}
