import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion


async def compute_citation_rate(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    aliases = [brand.name] + (brand.aliases or [])

    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    domains = gt.ground_truth_json.get("official_domains", []) if gt else []

    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]

    mentioned = 0
    cited = 0
    for r in valid:
        if not any(a.lower() in r.answer_text.lower() for a in aliases):
            continue
        mentioned += 1
        found_urls = re.findall(r'https?://[^\s\)\]】]+', r.answer_text)
        if any(any(d in u for d in domains) for u in found_urls):
            cited += 1

    return {
        "citation_rate": round(cited / mentioned, 4) if mentioned else 0.0,
        "cited_contexts": cited,
        "mentioned_contexts": mentioned,
        "sample_size": len(valid),
    }
