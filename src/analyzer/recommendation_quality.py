from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand


async def compute_recommendation_quality(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    """Recommendation Quality: how substantive are the recommendation reasons provided by AI platforms."""
    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"value": 0.0, "numerator": 0, "denominator": 0, "sample_size": 0, "confidence": "low"}

    # Quality markers: specific details, numbers, comparisons, named entities
    quality_markers = ["因为", "所以", "相比", "根据", "数据", "%", "年", "案例", "例如", "具体"]
    scored = sum(
        1 for r in valid
        if sum(1 for m in quality_markers if m in r.answer_text) >= 2
    )
    value = round(scored / len(valid), 4)

    confidence = "high" if len(valid) >= 10 else "medium" if len(valid) >= 5 else "low"
    return {"value": value, "numerator": scored, "denominator": len(valid),
            "sample_size": len(valid), "confidence": confidence}
