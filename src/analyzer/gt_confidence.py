def compute_field_confidence(sources: list[dict]) -> str:
    official_sources = [s for s in sources if s.get("source_quality") == "high"]
    ai_sources = [s for s in sources if s.get("source_type") == "ai_platform"]

    values = [s.get("value", "")[:100] for s in sources if s.get("value")]
    unique_values = set(values)
    has_conflict = len(unique_values) > 1

    if official_sources and len(set(s.get("value", "")[:100] for s in ai_sources + official_sources)) <= 1:
        return "high"
    if len(ai_sources) >= 2 and not has_conflict:
        return "medium"
    if len(sources) == 1 and sources[0].get("source_quality") in ("low", "very_low"):
        return "low"
    if has_conflict:
        return "uncertain"
    return "low"
