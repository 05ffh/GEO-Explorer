import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.competitor_set import CompetitorSet
from src.models.metrics_snapshot import MetricsSnapshot

METRICS = ["sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"]


async def build_competitor_matrix(brand_id: str, db: AsyncSession) -> dict:
    active_set = (await db.execute(
        select(CompetitorSet).where(
            CompetitorSet.brand_id == brand_id, CompetitorSet.is_active == True,  # noqa: E712
        )
    )).scalars().first()
    if not active_set:
        return {"matrix": [], "metric_names": METRICS}

    brand_ids = [uuid.UUID(brand_id)] + [
        uuid.UUID(cid) for cid in active_set.competitor_brand_ids
    ]
    latest = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id.in_(brand_ids),
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(
            MetricsSnapshot.brand_id, MetricsSnapshot.week_start.desc(),
        )
    )).scalars().all()

    seen = {}
    for s in latest:
        if s.brand_id not in seen:
            seen[s.brand_id] = s

    return {
        "matrix": [
            {
                "brand_id": str(bid),
                **{m: getattr(s, m) for m in METRICS},
                "sample_size": s.sample_size,
            }
            for bid, s in seen.items()
        ],
        "metric_names": METRICS,
    }
