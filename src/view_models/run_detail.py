"""Collection Run Detail ViewModel — live status, progress, KPI, hallucinations."""
from sqlalchemy import select, func, case
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.hallucination import HallucinationResult
from src.models.metrics_snapshot import MetricsSnapshot


async def build_run_detail_vm(run_id: str, brand, user, db) -> dict:
    """Build view model for /brands/{brand_id}/runs/{run_id} page."""
    run = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.id == run_id,
            CollectionRun.brand_id == brand.id,
        )
    )).scalar_one_or_none()

    if not run:
        return {"error": "Run not found"}

    # Progress by platform
    platform_rows = (await db.execute(
        select(QueryResult.platform, func.count().label("total"),
               func.sum(case((QueryResult.status == "success", 1), else_=0)).label("success"))
        .where(QueryResult.collection_run_id == run_id)
        .group_by(QueryResult.platform)
    )).fetchall()

    platforms = []
    for plat, total, success in platform_rows:
        platforms.append({
            "platform": plat,
            "total": total,
            "success": success or 0,
            "failed": total - (success or 0),
        })

    # Hallucination summary
    hall_counts = (await db.execute(
        select(HallucinationResult.severity, func.count().label("cnt"))
        .where(HallucinationResult.collection_run_id == run_id)
        .group_by(HallucinationResult.severity)
    )).fetchall()

    hallucination = {"P0": 0, "P1": 0, "P2": 0, "Info": 0, "total": 0}
    for sev, cnt in hall_counts:
        hallucination[sev or "Info"] = cnt
        hallucination["total"] += cnt

    # Latest metrics
    metrics = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.collection_run_id == run_id,
        ).order_by(MetricsSnapshot.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    kpi = {}
    if metrics:
        kpi = {
            "sov": round(metrics.sov, 2) if metrics.sov else None,
            "accuracy": round(metrics.accuracy_rate, 2) if metrics.accuracy_rate else None,
            "completeness": round(metrics.completeness_rate, 2) if metrics.completeness_rate else None,
            "citation": round(metrics.citation_rate, 2) if metrics.citation_rate else None,
            "first_rec": round(metrics.first_rec_rate, 2) if metrics.first_rec_rate else None,
        }

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "run": {
            "id": str(run.id),
            "status": run.collection_status,
            "analysis_status": run.analysis_status if hasattr(run, "analysis_status") else "",
            "total_queries": run.total_queries or 0,
            "success_count": run.success_count or 0,
            "failure_count": run.failure_count or 0,
            "started_at": str(run.started_at)[:19] if run.started_at else "",
            "completed_at": str(run.collection_completed_at)[:19] if run.collection_completed_at else "",
        },
        "platforms": platforms,
        "hallucination": hallucination,
        "kpi": kpi,
        "has_metrics": metrics is not None,
    }
