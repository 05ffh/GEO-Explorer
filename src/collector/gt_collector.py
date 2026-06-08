import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.brand import Brand
from src.models.gt_candidate import GroundTruthCandidate

logger = logging.getLogger(__name__)

GT_QUESTIONS = [
    ("identity", "{公司} 是一家什么样的公司？请详细描述。", ["official_name", "positioning", "industry"]),
    ("category", "{公司} 属于什么行业和什么具体品类？", ["industry", "category", "subcategory"]),
    ("products", "{公司} 的核心产品/服务有哪些？", ["core_products", "core_features"]),
    ("users", "{公司} 的目标用户是谁？主要服务什么人群？", ["target_users", "best_fit_users"]),
    ("scenarios", "{公司} 主要解决哪些用户问题或业务场景？", ["core_scenarios", "scenario_keywords"]),
    ("differentiation", "{公司} 和主要竞品相比有什么不同？有什么特点？", ["key_differentiators"]),
    ("competitors", "{公司} 的主要竞品或替代方案有哪些？", ["target_competitors", "alternative_solutions"]),
    ("misconceptions", "关于{公司}，有哪些常见误解或不能错误描述的地方？", ["forbidden_claims", "common_misconceptions"]),
    ("sources", "{公司} 有哪些官方来源可以证明它的信息？", ["source_of_truth_by_field", "official_docs", "official_channels"]),
    ("recommendation", "在什么情况下应该选择{公司}？推荐它的正确理由是什么？", ["preferred_recommendation_reasons", "best_fit_users"]),
]


async def collect_gt_candidate(
    brand_id: str, org_id: str, db: AsyncSession, company_name: str | None = None
) -> GroundTruthCandidate:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    if not brand:
        raise ValueError("Brand not found")
    company = company_name or brand.name

    ai_results = await _collect_from_ai_platforms(company)
    search_results = await _collect_from_search(company)

    from src.analyzer.gt_aggregator import aggregate_all_fields
    field_results = aggregate_all_fields(ai_results, search_results)

    candidate = GroundTruthCandidate(
        organization_id=org_id,
        brand_id=brand_id,
        candidate_json={f: r["value"] for f, r in field_results.items()},
        confidence_summary={
            f: {
                "confidence": r["confidence"],
                "evidence_count": r["evidence_count"],
                "has_official_source": r.get("official_source_count", 0) > 0,
            }
            for f, r in field_results.items()
        },
        overall_confidence=_compute_overall(field_results),
        status="pending_review",
    )
    db.add(candidate)
    await db.flush()

    # Persist evidence records with source tiers
    _persist_evidence(candidate, field_results, ai_results, search_results, db)

    await db.commit()
    return candidate


async def _collect_from_ai_platforms(company: str) -> list[dict]:
    import asyncio
    from src.adapters import get_adapter
    from src.config import settings

    results: list[dict] = []

    async def _query_platform(platform: str):
        """Query all 10 GT questions for one platform with semaphore-limited concurrency."""
        sem = asyncio.Semaphore(settings.platform_concurrency_limits.get(platform, 2))
        adapter = get_adapter(platform)

        async def _query_one(dim: str, template: str, fields: list[str]):
            async with sem:
                question = template.replace("{公司}", company)
                response = await adapter.query(question)
                return {
                    "platform": platform,
                    "dimension": dim,
                    "question": question,
                    "answer": response.answer_text,
                    "source_type": "ai_platform",
                    "source_quality": "medium",
                    "source_tier": "C",
                    "target_fields": fields,
                }

        tasks = [_query_one(dim, tmpl, flds) for dim, tmpl, flds in GT_QUESTIONS]
        platform_results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in platform_results:
            if isinstance(r, Exception):
                logger.warning("GT AI query failed for %s: %s", platform, r)
            else:
                results.append(r)

    # Run all platforms concurrently
    platform_tasks = [
        _query_platform(p) for p in ["deepseek", "kimi", "doubao", "wenxin"]
    ]
    await asyncio.gather(*platform_tasks, return_exceptions=True)

    return results


async def _collect_from_search(company: str) -> list[dict]:
    from src.config import settings
    from src.search import get_available_backends
    from src.search.source_tier import classify_source_tier

    results = []
    queries = [f"{company} 公司", f"{company} 产品", f"{company} 官网", f"{company} 怎么样"]
    backends = get_available_backends(settings)
    for backend in backends:
        for q in queries:
            try:
                items = await backend.search(q, num=3)
                for item in items:
                    tier = classify_source_tier(item.url, title=item.title)
                    results.append({
                        "platform": backend.name,
                        "query": q,
                        "title": item.title,
                        "snippet": item.snippet,
                        "url": item.url,
                        "source_type": "search_result",
                        "source_quality": item.source_quality,
                        "source_tier": tier,
                    })
            except Exception as e:
                logger.warning("Search failed for %s/%s: %s", backend.name, q, e)
    return results


def _persist_evidence(candidate, field_results, ai_results, search_results, db) -> None:
    """Persist evidence sources to gt_evidences table with source tiers."""
    from src.models.gt_evidence import GroundTruthEvidence
    from src.analyzer.gt_confidence import compute_field_confidence

    # Collect all sources per field from field_results
    for field_name, result in field_results.items():
        sources = result.get("sources", [])
        if not sources:
            # Fallback: create from field_results directly
            sources = [{
                "value": result.get("value", ""),
                "source_type": "ai_platform",
                "source_tier": "C",
                "platform": "aggregated",
            }]

        for src in sources:
            evidence = GroundTruthEvidence(
                candidate_id=candidate.id,
                field_name=field_name,
                value=src.get("value", "")[:500],
                source_type=src.get("source_type", "unknown"),
                source_name=src.get("platform", ""),
                source_url=src.get("url", ""),
                excerpt=src.get("snippet", src.get("excerpt", "")),
                source_tier=src.get("source_tier", "C"),
                source_quality=_tier_to_quality(src.get("source_tier", "C")),
                confidence=src.get("confidence", "low"),
            )
            db.add(evidence)


def _tier_to_quality(tier: str) -> str:
    mapping = {"S": "high", "A": "high", "B": "medium", "C": "low", "D": "very_low"}
    return mapping.get(tier, "low")


def _compute_overall(field_results: dict) -> str:
    if not field_results:
        return "low"
    confs = [r.get("confidence", "low") for r in field_results.values()]
    high = confs.count("high")
    if high >= len(confs) * 0.5:
        return "high"
    if high >= 1 or confs.count("medium") >= len(confs) * 0.5:
        return "medium"
    return "low"
