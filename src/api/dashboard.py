from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.brand import Brand
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.action_plan import ActionPlan
from src.models.hallucination import HallucinationResult
from src.models.insight_summary import InsightSummary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = user.organization_id

    brand_count = (await db.execute(
        select(func.count(Brand.id)).where(Brand.organization_id == org_id)
    )).scalar()

    # Average metrics across all brands' latest snapshots
    latest_metrics = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.organization_id == org_id,
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(
            MetricsSnapshot.brand_id, desc(MetricsSnapshot.week_start),
        ).distinct(MetricsSnapshot.brand_id)
    )).scalars().all() if brand_count else []

    avg_sov = sum(m.sov for m in latest_metrics) / len(latest_metrics) if latest_metrics else 0
    avg_first_rec = sum(m.first_rec_rate for m in latest_metrics) / len(latest_metrics) if latest_metrics else 0
    avg_accuracy = sum(m.accuracy_rate for m in latest_metrics) / len(latest_metrics) if latest_metrics else 0
    avg_completeness = sum(m.completeness_rate for m in latest_metrics) / len(latest_metrics) if latest_metrics else 0
    avg_citation = sum(m.citation_rate for m in latest_metrics) / len(latest_metrics) if latest_metrics else 0

    pending_actions = (await db.execute(
        select(func.count(ActionPlan.id)).where(
            ActionPlan.organization_id == org_id,
            ActionPlan.status == "pending",
        )
    )).scalar()

    recent_p0 = (await db.execute(
        select(func.count(HallucinationResult.id)).where(
            HallucinationResult.brand_id.in_(
                select(Brand.id).where(Brand.organization_id == org_id)
            ),
            HallucinationResult.severity == "P0",
            HallucinationResult.human_reviewed == False,  # noqa: E712
        )
    )).scalar()

    # Latest insight summary
    latest_insight = None
    if brand_count:
        insight_q = (await db.execute(
            select(InsightSummary).where(
                InsightSummary.organization_id == org_id,
            ).order_by(desc(InsightSummary.generated_at)).limit(1)
        )).scalar_one_or_none()
        if insight_q:
            latest_insight = {
                "collection_run_id": str(insight_q.collection_run_id),
                "brand_id": str(insight_q.brand_id),
                "platform_health": insight_q.platform_health_json,
                "brand_performance": insight_q.brand_performance_json,
                "key_findings": insight_q.key_findings_json,
                "data_reliability": insight_q.data_reliability_json,
                "confidence_level": insight_q.confidence_level,
                "generated_at": insight_q.generated_at.isoformat(),
            }

    return {
        "total_brands": brand_count,
        "average_metrics": {
            "sov": round(avg_sov, 4),
            "first_rec_rate": round(avg_first_rec, 4),
            "accuracy_rate": round(avg_accuracy, 4),
            "completeness_rate": round(avg_completeness, 4),
            "citation_rate": round(avg_citation, 4),
        },
        "pending_action_plans": pending_actions,
        "unreviewed_p0_hallucinations": recent_p0,
        "latest_insight": latest_insight,
    }
