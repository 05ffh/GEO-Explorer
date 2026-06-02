from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.ground_truth import GroundTruthVersion
from src.analyzer.evaluator import evaluate_field, Verdict
from src.analyzer.metric_mapping import get_kpi_eligible_results
from src.schemas.ground_truth import GT_FIELD_LEVELS, GT_LIST_FIELDS


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

    results = await get_kpi_eligible_results("information_accuracy", brand_id, collection_run_id, db)
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"accuracy_rate": 0.0, "mentioned_fields": 0, "correct_fields": 0,
                "sample_size": 0}

    all_text = "\n".join(r.answer_text for r in valid)
    gt_json = gt.get_flat_json() if hasattr(gt, "get_flat_json") else gt.ground_truth_json

    evaluations = {}
    for field in GT_FIELD_LEVELS:
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
        "numerator": len(correct),
        "denominator": len(mentioned),
        "sample_size": len(valid),
        "confidence": "high" if len(valid) >= 15 else "medium" if len(valid) >= 8 else "low",
        "details": {
            k: {
                "verdict": v.verdict.value, "reason": v.reason,
                "coverage_rate": v.coverage_rate,
            }
            for k, v in evaluations.items()
        },
    }
