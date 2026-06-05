"""View model for collection run list page."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.models.user import User
from src.models.brand import Brand
from src.models.collection_run import CollectionRun


async def build_run_list_vm(
    brand: Brand,
    user: User,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Build view model for /brands/{id}/runs list page."""
    org_id = user.organization_id

    base_q = select(CollectionRun).where(
        CollectionRun.brand_id == brand.id,
        CollectionRun.organization_id == org_id,
    )

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    rows = (await db.execute(
        base_q.order_by(CollectionRun.created_at.desc()).offset(offset).limit(page_size)
    )).scalars().all()

    run_cards = []
    for run in rows:
        pct = round(run.success_count / run.total_queries * 100) if run.total_queries else 0
        run_cards.append({
            "id": str(run.id),
            "status": run.collection_status,
            "trigger_type": run.trigger_type or "manual",
            "total_queries": run.total_queries or 0,
            "success_count": run.success_count or 0,
            "failure_count": run.failure_count or 0,
            "progress_pct": pct,
            "started_at": str(run.started_at)[:19] if run.started_at else "",
            "completed_at": str(run.collection_completed_at)[:19] if run.collection_completed_at else "",
            "is_running": run.collection_status in ("running", "pending", "queued"),
            "is_terminal": run.collection_status in ("completed", "failed", "partial", "cancelled"),
        })

    total_pages = max(1, (total + page_size - 1) // page_size)

    return {
        "runs": run_cards,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_runs": total > 0,
    }
