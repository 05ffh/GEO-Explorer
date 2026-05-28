from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.analyzer.evaluator import evaluate_field, Verdict
from src.schemas.ground_truth import GT_FIELD_LEVELS

SCALAR_CHECK_FIELDS = [
    "industry", "category", "positioning", "target_users", "market_position",
]
LIST_CHECK_FIELDS = ["core_scenarios", "differentiators", "tech_tags"]


async def compute_accuracy(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    if not gt:
        return {"accuracy_rate": 0.0, "mentioned_fields": 0, "correct_fields": 0,
                "error": "no active ground truth"}

    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"accuracy_rate": 0.0, "mentioned_fields": 0, "correct_fields": 0,
                "sample_size": 0}

    all_text = "\n".join(r.answer_text for r in valid)
    gt_json = gt.ground_truth_json

    evaluations = {}
    for field in SCALAR_CHECK_FIELDS + LIST_CHECK_FIELDS:
        if field not in gt_json:
            continue
        ev = evaluate_field(field, gt_json[field], all_text)
        evaluations[field] = ev

    mentioned = [e for e in evaluations.values() if e.verdict != Verdict.NOT_MENTIONED]
    correct = [e for e in mentioned if e.verdict == Verdict.CORRECT]

    return {
        "accuracy_rate": round(len(correct) / len(mentioned), 4) if mentioned else 0.0,
        "mentioned_fields": len(mentioned),
        "correct_fields": len(correct),
        "sample_size": len(valid),
        "details": {
            k: {
                "verdict": v.verdict.value, "reason": v.reason,
                "coverage_rate": v.coverage_rate,
            }
            for k, v in evaluations.items()
        },
    }
