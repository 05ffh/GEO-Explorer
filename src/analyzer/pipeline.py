import logging
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.ground_truth import GroundTruthVersion
from src.models.query_result import QueryResult
from src.models.action_plan import ActionPlan
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

    # Hallucination detection + Action plans
    try:
        await _run_hallucination_detection(brand_id, collection_run_id, org_id, db)
    except Exception:
        logger.exception("Hallucination detection failed for collection %s", collection_run_id)

    from src.analyzer.insights import generate_insights
    try:
        await generate_insights(collection_run_id, brand_id, org_id, db)
    except Exception:
        logger.exception("Insight generation failed for collection %s", collection_run_id)

    return snapshot


async def _run_hallucination_detection(
    brand_id: str, collection_run_id: str, org_id: str, db: AsyncSession,
) -> None:
    """Run hallucination detection on all query results and generate action plans."""
    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    if not gt:
        logger.info("No active GT for brand %s, skipping hallucination detection", brand_id)
        return

    query_results = (await db.execute(
        select(QueryResult).where(
            QueryResult.collection_run_id == collection_run_id,
            QueryResult.status == "success",
        )
    )).scalars().all()

    if not query_results:
        return

    from src.analyzer.hallucination import HallucinationDetector
    detector = HallucinationDetector()
    all_hallucinations = []

    for qr in query_results:
        try:
            results = await detector.detect(qr, gt, db)
            for h in results:
                db.add(h)
            all_hallucinations.extend(results)
        except Exception:
            logger.warning("Hallucination detection failed for query %s", qr.id)

    await db.flush()

    # Generate action plans from hallucinations
    incorrect_hallucinations = [h for h in all_hallucinations if h.verdict == "incorrect"]
    if incorrect_hallucinations:
        TRIGGER_MAP = {
            "P0": {"action_type": "definition_correction", "content_type": "FAQ"},
            "P1": {"action_type": "authority_building", "content_type": "Q&A"},
            "P2": {"action_type": "content_enrichment", "content_type": "Tutorial"},
        }
        for h in incorrect_hallucinations:
            trigger = TRIGGER_MAP.get(h.severity, TRIGGER_MAP["P2"])
            plan = ActionPlan(
                brand_id=brand_id,
                organization_id=org_id,
                trigger_type=f"field_{h.field_name}_error",
                action_type=trigger["action_type"],
                priority=h.severity,
                evidence_hallucination_ids=[str(h.id)],
                ai_wrong_claims={"claim": h.ai_claim},
                correct_ground_truth={"field": h.field_name, "value": str(h.ground_truth_value)},
                suggested_content_type=trigger["content_type"],
                acceptance_criteria=(
                    f"Field '{h.field_name}' hallucination resolved: "
                    f"AI should state '{str(h.ground_truth_value)[:100]}'"
                ),
                status="pending",
            )
            db.add(plan)

    await db.commit()
    logger.info("Hallucination detection complete: %d claims, %d incorrect, %d action plans",
                len(all_hallucinations), len(incorrect_hallucinations),
                len(incorrect_hallucinations))
