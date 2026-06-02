from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.ground_truth import GroundTruthVersion
from src.analyzer.evaluator import evaluate_field, Verdict
from src.analyzer.metric_mapping import get_kpi_eligible_results
from src.schemas.ground_truth import GT_REQUIRED_FOR_COMPLETENESS


async def compute_completeness(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    if not gt:
        return {"completeness_rate": 0.0, "complete_fields": 0,
                "required_fields": 0, "error": "no active ground truth"}

    results = await get_kpi_eligible_results("completeness_rate", brand_id, collection_run_id, db)
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"completeness_rate": 0.0, "complete_fields": 0,
                "required_fields": 0, "sample_size": 0}

    all_text = "\n".join(r.answer_text for r in valid)
    gt_json = gt.ground_truth_json

    required = [f for f in GT_REQUIRED_FOR_COMPLETENESS if f in gt_json]
    if not required:
        return {"completeness_rate": 0.0, "complete_fields": 0,
                "required_fields": 0, "sample_size": len(valid)}

    complete = 0
    details = {}
    for field in required:
        ev = evaluate_field(field, gt_json[field], all_text)
        details[field] = {"verdict": ev.verdict.value, "coverage_rate": ev.coverage_rate}
        if ev.verdict == Verdict.CORRECT:
            complete += 1

    return {
        "completeness_rate": round(complete / len(required), 4),
        "complete_fields": complete,
        "required_fields": len(required),
        "numerator": complete,
        "denominator": len(required),
        "sample_size": len(valid),
        "confidence": "high" if len(valid) >= 15 else "medium" if len(valid) >= 8 else "low",
        "details": details,
    }
