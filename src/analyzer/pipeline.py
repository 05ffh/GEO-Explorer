import logging
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.metrics_snapshot import MetricsSnapshot
from src.analyzer.sov import compute_sov
from src.analyzer.first_rec import compute_first_rec
from src.analyzer.accuracy import compute_accuracy
from src.analyzer.completeness import compute_completeness
from src.analyzer.citation import compute_citation_rate
from src.analyzer.scenario_recall import compute_scenario_recall
from src.analyzer.semantic_stability import compute_semantic_stability
from src.analyzer.differentiation import compute_differentiation
from src.analyzer.cross_platform_consistency import compute_cross_platform_consistency
from src.analyzer.recommendation_quality import compute_recommendation_quality

logger = logging.getLogger(__name__)


async def compute_and_save_metrics(
    brand_id: str, org_id: str, collection_run_id: str, db: AsyncSession,
) -> MetricsSnapshot:
    sov = await compute_sov(brand_id, collection_run_id, db)
    frr = await compute_first_rec(brand_id, collection_run_id, db)
    acc = await compute_accuracy(brand_id, collection_run_id, db)
    comp = await compute_completeness(brand_id, collection_run_id, db)
    cit = await compute_citation_rate(brand_id, collection_run_id, db)

    sr = await compute_scenario_recall(brand_id, collection_run_id, db)
    ss = await compute_semantic_stability(brand_id, collection_run_id, db)
    df = await compute_differentiation(brand_id, collection_run_id, db)
    cpc = await compute_cross_platform_consistency(brand_id, collection_run_id, db)
    rq = await compute_recommendation_quality(brand_id, collection_run_id, db)

    snapshot = MetricsSnapshot(
        brand_id=brand_id, organization_id=org_id,
        collection_run_id=collection_run_id,
        week_start=date.today(),
        sov=sov["sov"],
        first_rec_rate=frr["first_rec_rate"],
        accuracy_rate=acc["accuracy_rate"],
        completeness_rate=comp["completeness_rate"],
        citation_rate=cit["citation_rate"],
        sample_size=sov["sample_size"],
        failure_rate=sov["failure_rate"],
        details={
            "sov": sov, "frr": frr, "accuracy": acc, "completeness": comp, "citation": cit,
            "extended_kpis": {
                "scenario_recall": sr,
                "semantic_stability": ss,
                "differentiation": df,
                "cross_platform_consistency": cpc,
                "recommendation_quality": rq,
            },
        },
    )
    db.add(snapshot)
    await db.commit()

    from src.analyzer.insights import generate_insights
    try:
        await generate_insights(collection_run_id, brand_id, org_id, db)
    except Exception:
        logger.exception("Insight generation failed for collection %s", collection_run_id)

    return snapshot
