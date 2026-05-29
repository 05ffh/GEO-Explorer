from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand


async def compute_cross_platform_consistency(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    """Cross-Platform Consistency: how similar are key claims about the brand across AI platforms."""
    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"value": 0.0, "numerator": 0, "denominator": 0, "sample_size": 0, "confidence": "low"}

    platforms = set(r.platform for r in valid)
    if len(platforms) < 2:
        return {"value": 1.0, "numerator": 1, "denominator": 1, "sample_size": len(valid), "confidence": "low"}

    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    brand_name = brand.name

    # Count answers that mention the brand name consistently
    platform_mentions = {}
    for platform in platforms:
        platform_answers = [r for r in valid if r.platform == platform]
        platform_mentions[platform] = sum(1 for a in platform_answers if brand_name in a.answer_text)

    # Consistency = 1 - variance of mention rates
    rates = [platform_mentions[p] / max(1, len([r for r in valid if r.platform == p])) for p in platforms]
    mean_rate = sum(rates) / len(rates)
    variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
    value = round(1.0 - min(variance, 1.0), 4)

    confidence = "high" if len(valid) >= 12 else "medium" if len(valid) >= 6 else "low"
    return {"value": value, "numerator": len(platforms), "denominator": len(platforms),
            "sample_size": len(valid), "confidence": confidence}
