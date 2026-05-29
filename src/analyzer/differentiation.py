from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult


async def compute_differentiation(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    """Differentiation Rate: proportion of answers that mention unique differentiators (vs generic descriptions)."""
    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"value": 0.0, "numerator": 0, "denominator": 0, "sample_size": 0, "confidence": "low"}

    # Differentiators: specific terms suggesting unique attributes
    diff_keywords = ["独特", "唯一", "专有", "专利", "特色", "差异化", "不同于", "区别", "优势", "独创"]
    differentiated = sum(
        1 for r in valid
        if any(kw in r.answer_text for kw in diff_keywords)
    )

    value = round(differentiated / len(valid), 4)
    confidence = "high" if len(valid) >= 10 else "medium" if len(valid) >= 5 else "low"
    return {"value": value, "numerator": differentiated, "denominator": len(valid),
            "sample_size": len(valid), "confidence": confidence}
