from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult


async def compute_semantic_stability(
    brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> dict:
    """Semantic Stability: how consistently the brand is described across platforms (Jaccard similarity of key terms)."""
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

    # Tokenize each platform's aggregated answers into word sets
    platform_tokens = {}
    for platform in platforms:
        text = " ".join(r.answer_text for r in valid if r.platform == platform)
        tokens = set(text.lower().split())
        platform_tokens[platform] = tokens

    # Pairwise Jaccard similarity
    similarities = []
    plats = list(platform_tokens.keys())
    for i in range(len(plats)):
        for j in range(i + 1, len(plats)):
            set_a = platform_tokens[plats[i]]
            set_b = platform_tokens[plats[j]]
            if not set_a and not set_b:
                continue
            jaccard = len(set_a & set_b) / len(set_a | set_b) if (set_a | set_b) else 1.0
            similarities.append(jaccard)

    value = round(sum(similarities) / len(similarities), 4) if similarities else 1.0
    confidence = "high" if len(similarities) >= 3 else "medium"
    return {"value": value, "numerator": len(similarities), "denominator": len(platforms),
            "sample_size": len(valid), "confidence": confidence}
