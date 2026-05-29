import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.query_template import QueryTemplate

FIRST_REC_PATTERNS = [
    r'(?:首选|最推荐|优先考虑|强烈推荐|最值得|第一名)[^。\n]{0,20}({brand})',
    r'({brand})[^。\n]{0,10}(?:最好|最佳|最合适|首选|推荐)',
]


async def compute_first_rec(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()

    rec_template_ids = (await db.execute(
        select(QueryTemplate.id).where(QueryTemplate.dimension == "场景推荐")
    )).scalars().all()

    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id,
        QueryResult.status == "success",
        QueryResult.template_id.in_(rec_template_ids),
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]

    first_count = 0
    for r in valid:
        text = r.answer_text
        list_match = re.findall(
            r'(?:^|\n)\s*(?:\d+[\.\)、]|[-*])\s*([^\n]{0,80})', text,
        )
        if list_match and brand.name in list_match[0]:
            first_count += 1
            continue
        for pattern in FIRST_REC_PATTERNS:
            if re.search(pattern.replace("{brand}", re.escape(brand.name)), text):
                first_count += 1
                break

    return {
        "first_rec_rate": round(first_count / len(valid), 4) if valid else 0.0,
        "numerator": first_count,
        "denominator": len(valid),
        "first_count": first_count,
        "total_rec_answers": len(valid),
        "sample_size": len(valid),
        "confidence": "high" if len(valid) >= 15 else "medium" if len(valid) >= 8 else "low",
    }
