from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand


async def compute_sov(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    aliases = [brand.name] + (brand.aliases or [])

    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    failed = len(results) - len(valid)

    mentioned = sum(
        1 for r in valid
        if any(a.lower() in r.answer_text.lower() for a in aliases)
    )
    return {
        "sov": round(mentioned / len(valid), 4) if valid else 0.0,
        "mentioned": mentioned,
        "total_valid": len(valid),
        "total_attempted": len(results),
        "sample_size": len(valid),
        "failure_rate": round(failed / len(results), 4) if results else 0.0,
    }
