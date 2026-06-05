"""P1-8: Reclassification API — trigger, status, progress, history, diff, cancel, retry."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.reclassification_run import (
    ReclassificationRun, STATUS_QUEUED, STATUS_COMPLETED,
)
from src.services.reclassification_service import ReclassificationService

router = APIRouter(prefix="/api", tags=["reclassifications"])


class ReclassifyRequest(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None
    dry_run: bool = True
    mode: str = "dry_run"
    gt_version_strategy: str = "latest_active"
    reason: str = Field(..., min_length=1)
    idempotency_key: str | None = None


@router.post("/brands/{brand_id}/reclassify")
async def trigger_reclassification(
    brand_id: uuid.UUID,
    body: ReclassifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # P0-8: Idempotency check
    if body.idempotency_key:
        existing = (await db.execute(
            select(ReclassificationRun).where(
                ReclassificationRun.idempotency_key == body.idempotency_key
            )
        )).scalar_one_or_none()
        if existing:
            return {"reclassification_run_id": str(existing.id), "status": existing.status, "idempotent": True}

    # P0-8: Concurrent lock check
    active = (await db.execute(
        select(ReclassificationRun).where(
            ReclassificationRun.organization_id == user.organization_id,
            ReclassificationRun.brand_id == brand_id,
            ReclassificationRun.status.in_([STATUS_QUEUED, "running"]),
        )
    )).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409, detail=f"Active reclassification exists: {active.id}")

    # P1-2: Permission — analyst can only dry_run
    if not body.dry_run and user.role not in ("admin", "owner", "system_admin", "system_owner"):
        raise HTTPException(status_code=403, detail="Only brand admin+ can run non-dry-run reclassification")

    # Create batch
    batch = await ReclassificationService.create_batch(
        db,
        organization_id=user.organization_id,
        brand_id=brand_id,
        from_date=body.from_date,
        to_date=body.to_date,
        dry_run=body.dry_run,
        mode=body.mode,
        gt_version_strategy=body.gt_version_strategy,
        reason=body.reason,
        triggered_by=user.id,
        idempotency_key=body.idempotency_key,
    )
    await db.commit()

    # P0-2: Enqueue async task (lazy import to avoid celery import at module level)
    from src.services.reclassification_task import run_reclassification
    run_reclassification.delay(str(batch.id))

    return {
        "reclassification_run_id": str(batch.id),
        "status": batch.status,
        "idempotent": False,
    }


@router.get("/reclassifications/{batch_id}")
async def get_reclassification_status(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = (await db.execute(
        select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
    )).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404)
    if batch.organization_id != user.organization_id and user.platform_role not in ("system_admin", "system_owner"):
        raise HTTPException(status_code=403)
    return _batch_to_dict(batch)


@router.get("/reclassifications/{batch_id}/progress")
async def get_reclassification_progress(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = (await db.execute(
        select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
    )).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404)
    return {
        "status": batch.status,
        "progress": batch.progress_json,
        "eligible_runs": batch.eligible_runs_count,
        "runs_processed": batch.runs_processed,
        "runs_failed": batch.runs_failed,
    }


@router.get("/reclassifications/{batch_id}/diff")
async def get_reclassification_diff(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = (await db.execute(
        select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
    )).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404)
    return {
        "classification_changes": batch.classification_changes_json,
        "sample_diffs": batch.sample_diffs_json,
        "total_query_results_processed": batch.query_results_processed,
    }


class ApplyRequest(BaseModel):
    reason: str = Field(..., min_length=1)
    idempotency_key: str | None = None


@router.post("/reclassifications/{batch_id}/apply")
async def apply_reclassification(
    batch_id: uuid.UUID,
    body: ApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply a completed dry-run reclassification — creates write batch."""
    source = (await db.execute(
        select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
    )).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=404)
    if source.organization_id != user.organization_id and user.platform_role not in ("system_admin", "system_owner"):
        raise HTTPException(status_code=403)
    if not source.dry_run:
        raise HTTPException(status_code=400, detail="Only dry-run batches can be applied")
    if source.status != STATUS_COMPLETED:
        raise HTTPException(status_code=400, detail="Dry-run must be completed before applying")
    if user.role not in ("admin", "owner") and user.platform_role not in ("system_admin", "system_owner"):
        raise HTTPException(status_code=403, detail="需要品牌管理员权限才能正式写入")

    # Check concurrent
    active = (await db.execute(
        select(ReclassificationRun).where(
            ReclassificationRun.organization_id == user.organization_id,
            ReclassificationRun.brand_id == source.brand_id,
            ReclassificationRun.status.in_([STATUS_QUEUED, "running"]),
        )
    )).scalar_one_or_none()
    if active:
        raise HTTPException(status_code=409, detail=f"已有运行中的批次: {active.id}")

    # Create apply batch from dry-run
    apply_batch = await ReclassificationService.create_batch(
        db,
        organization_id=user.organization_id,
        brand_id=source.brand_id,
        from_date=source.from_date,
        to_date=source.to_date,
        dry_run=False,
        mode="write_new_results",
        gt_version_strategy=source.gt_version_strategy,
        reason=body.reason,
        triggered_by=user.id,
        idempotency_key=body.idempotency_key,
    )
    await db.commit()

    from src.services.reclassification_task import run_reclassification
    run_reclassification.delay(str(apply_batch.id))

    return {
        "reclassification_run_id": str(apply_batch.id),
        "status": apply_batch.status,
        "source_dry_run_id": str(source.id),
    }


@router.post("/reclassifications/{batch_id}/cancel")
async def cancel_reclassification(
    batch_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batch = (await db.execute(
        select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
    )).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status_code=404)
    if batch.organization_id != user.organization_id and user.platform_role not in ("system_admin", "system_owner"):
        raise HTTPException(status_code=403)
    batch.status = "cancelled"
    batch.cancelled_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled"}


@router.get("/brands/{brand_id}/reclassifications")
async def list_reclassifications(
    brand_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    batches = (await db.execute(
        select(ReclassificationRun)
        .where(ReclassificationRun.brand_id == brand_id)
        .order_by(desc(ReclassificationRun.created_at))
        .limit(20)
    )).scalars().all()
    return {
        "brand_id": str(brand_id),
        "batches": [_batch_to_dict(b) for b in batches],
    }


def _batch_to_dict(batch: ReclassificationRun) -> dict:
    return {
        "id": str(batch.id),
        "brand_id": str(batch.brand_id),
        "status": batch.status,
        "mode": batch.mode,
        "dry_run": batch.dry_run,
        "from_date": batch.from_date.isoformat() if batch.from_date else None,
        "to_date": batch.to_date.isoformat() if batch.to_date else None,
        "eligible_runs_count": batch.eligible_runs_count,
        "runs_processed": batch.runs_processed,
        "runs_failed": batch.runs_failed,
        "query_results_processed": batch.query_results_processed,
        "hallucination_results_created": batch.hallucination_results_created,
        "classification_changes": batch.classification_changes_json,
        "is_current_for_range": batch.is_current_for_range,
        "triggered_by": str(batch.triggered_by) if batch.triggered_by else None,
        "reason": batch.reason,
        "started_at": batch.started_at.isoformat() if batch.started_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
    }
