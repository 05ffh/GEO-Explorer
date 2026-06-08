from collections import defaultdict

from src.analyzer.gt_confidence import compute_field_confidence
from src.analyzer.gt_conflict_detector import detect_conflicts
from src.analyzer.gt_cross_validator import (
    SourceEvidence, cross_validate_ai_with_search,
)


def aggregate_all_fields(ai_results: list[dict], search_results: list[dict]) -> dict:
    # Build SourceEvidence for AI results
    ai_evidence: dict[str, list[SourceEvidence]] = defaultdict(list)
    for r in ai_results:
        tier = r.get("source_tier", "C")
        for field in r.get("target_fields", []):
            ai_evidence[field].append(SourceEvidence(
                field_name=field,
                value=r["answer"][:500],
                source_type="ai_platform",
                source_tier=tier,
                source_quality="medium",
                provider=r["platform"],
                original_source_tier=tier,
            ))

    # Build SourceEvidence for search results
    search_evidence: dict[str, list[SourceEvidence]] = defaultdict(list)
    for r in search_results:
        tier = r.get("source_tier", "C")
        for field in _infer_fields_from_search(r.get("snippet", "")):
            search_evidence[field].append(SourceEvidence(
                field_name=field,
                value=r.get("snippet", "")[:300],
                source_type=r.get("source_type", "search_result"),
                source_tier=tier,
                source_quality=r.get("source_quality", "low"),
                provider=r.get("platform", ""),
                url=r.get("url", ""),
            ))

    # Cross-validate: upgrade AI tiers based on search evidence
    for field in list(ai_evidence.keys()):
        if field in search_evidence:
            ai_evidence[field] = cross_validate_ai_with_search(
                ai_evidence[field], search_evidence[field],
            )

    # Merge back into field_sources dict for downstream compatibility
    field_sources: dict[str, list[dict]] = defaultdict(list)

    for field, ev_list in ai_evidence.items():
        for ev in ev_list:
            src = {
                "value": ev.value,
                "source_type": ev.source_type,
                "source_quality": ev.source_quality,
                "source_tier": ev.source_tier,
                "platform": ev.provider,
                "original_source_tier": ev.original_source_tier,
                "validation_status": ev.validation_status,
                "upgrade_reason": ev.upgrade_reason,
                "match_score": ev.match_score,
                "matched_search_sources": ev.matched_search_sources,
            }
            field_sources[field].append(src)

    for field, ev_list in search_evidence.items():
        for ev in ev_list:
            src = {
                "value": ev.value,
                "source_type": ev.source_type,
                "source_quality": ev.source_quality,
                "source_tier": ev.source_tier,
                "platform": ev.provider,
                "url": ev.url,
            }
            field_sources[field].append(src)

    result = {}
    for field, sources in field_sources.items():
        confidence = compute_field_confidence(sources)
        conflict = detect_conflicts(sources)
        values = [s["value"] for s in sources if s.get("value")]
        best_value = values[0] if values else ""
        result[field] = {
            "value": best_value,
            "confidence": confidence,
            "evidence_count": len(sources),
            "official_source_count": sum(1 for s in sources if s.get("source_quality") == "high"),
            "ai_platform_agreement": len(
                set(s["value"][:100] for s in sources if s["source_type"] == "ai_platform")
            ),
            "conflict_count": conflict["conflict_count"],
            "sources": sources,
        }
    return result


def _infer_fields_from_search(snippet: str) -> list[str]:
    fields = []
    if any(kw in snippet for kw in ["公司", "企业", "品牌", "平台"]):
        fields.extend(["official_name", "positioning"])
    if any(kw in snippet for kw in ["产品", "服务", "功能", "提供"]):
        fields.append("core_products")
    if any(kw in snippet for kw in ["官网", "官方", "http"]):
        fields.append("official_domains")
    return fields or ["positioning"]
