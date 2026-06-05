import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db, async_session
from src.api.deps import get_current_user, get_user_or_api_key, get_org_brand_or_404
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

router = APIRouter(prefix="/api/brands", tags=["brands"])


class BrandCreate(BaseModel):
    name: str
    aliases: list[str] = []
    industry: str = ""
    ground_truth: dict = {}


class BrandUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    industry: str | None = None


@router.get("")
async def list_brands(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    q = select(Brand).where(Brand.organization_id == user.organization_id)
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}


@router.post("")
async def create_brand(
    body: BrandCreate,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    brand = Brand(
        organization_id=user.organization_id,
        name=body.name, aliases=body.aliases, industry=body.industry,
        created_by=user.id,
    )
    db.add(brand)
    await db.flush()

    if body.ground_truth:
        gt = GroundTruthVersion(
            brand_id=brand.id, version=1,
            ground_truth_json=body.ground_truth, status="active",
            reviewer=user.name,
        )
        db.add(gt)

    await db.commit()
    return {"id": str(brand.id), "name": brand.name}


@router.get("/search")
async def search_brands(
    q: str = Query("", min_length=1),
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Search brands by name or alias within user's organization."""
    q = q.strip()
    brands = (await db.execute(
        select(Brand).where(
            Brand.organization_id == user.organization_id,
            Brand.name.ilike(f"%{q}%"),
        ).limit(10)
    )).scalars().all()
    return {"items": brands, "query": q}


@router.get("/{brand_id}")
async def get_brand(
    brand_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().first()
    return {"brand": brand, "active_gt": gt}


@router.put("/{brand_id}")
async def update_brand(
    brand_id: str,
    body: BrandUpdate,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    if body.name is not None:
        brand.name = body.name
    if body.aliases is not None:
        brand.aliases = body.aliases
    if body.industry is not None:
        brand.industry = body.industry
    brand.updated_by = user.id
    await db.commit()
    return {"id": str(brand.id), "name": brand.name}


@router.post("/{brand_id}/gt-collect", status_code=202)
async def trigger_gt_collection(
    brand_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
    force: bool = Query(False),
):
    """Trigger GT auto-collection for a brand (async via Celery)."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.collector.tasks import collect_gt_task
    from src.queue.lifecycle import TaskLifecycle
    from src.queue.idempotency import (
        build_idempotency_key, build_payload_hash, build_time_bucket, try_acquire,
    )

    payload_hash = build_payload_hash([str(brand.id)], {"trigger_type": "manual"})
    idem_key = build_idempotency_key(
        org_id=str(user.organization_id),
        task_name="collect_gt_task",
        operation_type="gt_collection",
        payload_hash=payload_hash,
        time_bucket=build_time_bucket(),
    )

    if not force and not await try_acquire(idem_key):
        from src.models.task_state import TaskState
        existing = (await db.execute(
            select(TaskState).where(
                TaskState.idempotency_key == idem_key,
                TaskState.status.in_(["queued", "running", "retrying"]),
            )
        )).scalar_one_or_none()
        if existing:
            return {"task_id": existing.celery_task_id, "status": "duplicate", "message": "已有相同任务在执行中"}

    celery_task_id = f"gt_{brand_id}_{int(datetime.now(timezone.utc).timestamp())}"
    timeout_at = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() + 900, tz=timezone.utc,
    )

    lc = TaskLifecycle(db)
    ts = await lc.create(
        celery_task_id=celery_task_id,
        task_name="src.collector.tasks.collect_gt_task",
        organization_id=user.organization_id,
        brand_id=uuid.UUID(brand_id),
        operation_type="gt_collection",
        trigger_type="manual",
        args=[str(brand.id), str(user.organization_id)],
        idempotency_key=idem_key,
        timeout_at=timeout_at,
    )
    await db.commit()

    try:
        task = collect_gt_task.apply_async(
            args=[str(brand.id), str(user.organization_id)],
            kwargs={"force": force},
            task_id=celery_task_id,
        )
        return {"status": "queued", "task_id": task.id, "brand_id": str(brand.id)}
    except Exception as exc:
        async with async_session() as s:
            existing_task = (await s.execute(
                select(TaskState).where(TaskState.celery_task_id == celery_task_id)
            )).scalar_one_or_none()
            if existing_task:
                existing_task.status = "enqueue_failed"
                await s.commit()
        return {"task_id": celery_task_id, "status": "enqueue_failed", "error": str(exc)}
