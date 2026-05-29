from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand


async def compute_scenario_recall(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    """Scenario Recall Rate: proportion of non-branded scenario questions where brand is mentioned."""
    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"value": 0.0, "numerator": 0, "denominator": 0, "sample_size": 0, "confidence": "low"}

    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    brand_names = [brand.name] + (brand.aliases or [])

    # Non-branded questions: those NOT mentioning brand name directly
    non_branded = [
        r for r in valid
        if not any(n.lower() in r.question.lower() for n in brand_names)
    ]
    if not non_branded:
        return {"value": 0.0, "numerator": 0, "denominator": 0, "sample_size": 0, "confidence": "low"}

    recalled = sum(
        1 for r in non_branded
        if any(n.lower() in r.answer_text.lower() for n in brand_names)
    )
    value = round(recalled / len(non_branded), 4)

    confidence = "high" if len(non_branded) >= 8 else "medium" if len(non_branded) >= 3 else "low"
    return {"value": value, "numerator": recalled, "denominator": len(non_branded),
            "sample_size": len(non_branded), "confidence": confidence}
