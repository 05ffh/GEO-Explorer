from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database import get_db
from src.api.deps import get_current_user, get_user_or_api_key, get_org_brand_or_404
from src.models.user import User
from src.models.metrics_snapshot import MetricsSnapshot

router = APIRouter(prefix="/api/brands/{brand_id}/metrics", tags=["metrics"])


class MetricsResponse(BaseModel):
    sov: float = 0.0
    first_rec_rate: float = 0.0
    accuracy_rate: float = 0.0
    completeness_rate: float = 0.0
    citation_rate: float = 0.0
    sample_size: int = 0
    failure_rate: float = 0.0
    details: dict = {}
    model_config = {"from_attributes": True}


@router.get("")
async def get_latest_metrics(
    brand_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    snapshot = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id == brand_id,
        ).order_by(desc(MetricsSnapshot.created_at)).limit(1)
    )).scalar_one_or_none()
    if not snapshot:
        return {"message": "No metrics yet", "metrics": None}
    return {"metrics": snapshot}


@router.get("/history")
async def get_metrics_history(
    brand_id: str,
    user: User = Depends(get_user_or_api_key),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    snapshots = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id == brand_id,
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(desc(MetricsSnapshot.week_start)).limit(52)
    )).scalars().all()
    return {"history": snapshots}
