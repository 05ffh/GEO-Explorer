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


@router.post("/api/collections/preflight")
async def collection_preflight(
    brand_id: str = Query(...),
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Preflight check before starting a GEO diagnostic collection."""
    from src.models.brand import Brand
    from src.models.query_template import QueryTemplate
    from src.models.ground_truth import GroundTruthVersion
    from src.adapters import get_adapter
    from src.config import settings
    from src.collector.engine import _build_template_health_report

    brand = await get_org_brand_or_404(brand_id, user, db)

    has_industry = bool(brand.industry)
    brand_ok = bool(brand.name)

    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        ).order_by(GroundTruthVersion.version.desc())
    )).scalars().first()
    gt_fields = list(gt.ground_truth_json.keys()) if gt and gt.ground_truth_json else []
    required_fields = getattr(settings, 'gt_required_fields', [])
    gt_coverage = len(set(required_fields) & set(gt_fields)) / len(required_fields) if required_fields else 1.0
    gt_missing = [f for f in required_fields if f not in gt_fields]

    templates = (await db.execute(
        select(QueryTemplate).where(QueryTemplate.is_active == True)
    )).scalars().all()
    health = _build_template_health_report(templates) if templates else {"can_collect": True, "invalid_templates": 0}

    platforms = {}
    for p in getattr(settings, 'ai_platforms', ['deepseek', 'kimi', 'doubao', 'wenxin']):
        try:
            adapter = get_adapter(p)
            platforms[p] = {"available": adapter is not None}
        except Exception:
            platforms[p] = {"available": False}

    available_platforms = [p for p, s in platforms.items() if s["available"]]
    platform_count = len(available_platforms)
    template_count = len(templates)
    estimated_queries = template_count * platform_count if template_count > 0 and platform_count > 0 else 0

    blocking = []
    warnings = []
    if not brand_ok:
        blocking.append({"code": "BRAND_NAME_MISSING", "message": "品牌名称缺失"})
    if not has_industry:
        blocking.append({"code": "INDUSTRY_UNSET", "message": "行业未设置，请先确认行业"})
    if gt_coverage < 0.3:
        blocking.append({"code": "GT_COVERAGE_LOW", "message": f"GT 覆盖率仅 {gt_coverage:.0%}，建议先补充 GT"})
    if template_count == 0:
        blocking.append({"code": "NO_TEMPLATES", "message": "没有启用的查询模板"})
    if platform_count == 0:
        blocking.append({"code": "NO_PLATFORMS", "message": "没有可用的 AI 平台"})
    if not health.get("can_collect", True):
        blocking.append({"code": "TEMPLATE_UNHEALTHY"})
    if gt_coverage < 0.6:
        warnings.append({"code": "GT_COVERAGE_LOW_WARN"})
    if platform_count < 2:
        warnings.append({"code": "SINGLE_PLATFORM"})

    return {
        "brand_id": str(brand.id), "brand_name": brand.name,
        "can_start": len(blocking) == 0,
        "blocking_reasons": blocking, "warnings": warnings,
        "checks": {
            "brand_ok": brand_ok, "has_industry": has_industry,
            "industry": brand.industry or "",
            "gt_coverage": round(gt_coverage, 2), "gt_fields": len(gt_fields),
            "gt_required_fields": required_fields, "gt_missing": gt_missing,
            "template_health": health, "template_count": template_count,
            "platforms": platforms, "available_platforms": available_platforms,
            "platform_count": platform_count, "estimated_queries": estimated_queries,
        },
    }


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


@router.post("/api/collections/{collection_id}/cancel")
async def cancel_collection(
    collection_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running/queued collection run."""
    run = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.id == collection_id,
            CollectionRun.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not run:
        return {"detail": "Not found"}, 404

    if run.collection_status not in ("running", "pending", "queued"):
        return {"accepted": False, "message": f"任务状态为 {run.collection_status}，无法取消"}

    from src.queue.control import cancel_task
    from src.models.task_state import TaskState

    # Find the Celery task
    ts = (await db.execute(
        select(TaskState).where(
            TaskState.brand_id == run.brand_id,
            TaskState.operation_type.in_(["full_collect", "gt_collection"]),
            TaskState.status.in_(["queued", "running", "retrying"]),
        ).order_by(TaskState.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    if ts:
        result = await cancel_task(ts.celery_task_id, ts.status)
        ts.status = "cancelled"
    else:
        result = {"accepted": True, "mechanism": "direct", "message": "未找到 Celery 任务，直接更新状态"}

    run.collection_status = "cancelled"
    run.collection_completed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"accepted": True, "status": run.collection_status, **result}
