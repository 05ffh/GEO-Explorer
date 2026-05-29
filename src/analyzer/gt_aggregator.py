from collections import defaultdict

from src.analyzer.gt_confidence import compute_field_confidence
from src.analyzer.gt_conflict_detector import detect_conflicts


def aggregate_all_fields(ai_results: list[dict], search_results: list[dict]) -> dict:
    field_sources: dict[str, list[dict]] = defaultdict(list)

    for r in ai_results:
        for field in r.get("target_fields", []):
            field_sources[field].append({
                "value": r["answer"][:500],
                "source_type": "ai_platform",
                "source_quality": "medium",
                "platform": r["platform"],
            })

    for r in search_results:
        for field in _infer_fields_from_search(r.get("snippet", "")):
            field_sources[field].append({
                "value": r["snippet"][:300],
                "source_type": r["source_type"],
                "source_quality": r.get("source_quality", "low"),
                "url": r.get("url", ""),
                "platform": r["platform"],
            })

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
