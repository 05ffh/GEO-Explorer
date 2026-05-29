from src.schemas.ground_truth import SOURCE_TIERS


def compute_field_confidence(sources: list[dict], field_name: str = "") -> str:
    """Tier-weighted confidence scoring using S/A/B/C/D source tiers.

    S-tier sources carry the most weight. Conflict detection is
    field-type-aware through gt_conflict_detector.
    """
    if not sources:
        return "low"

    tiers = [s.get("source_tier", "C") for s in sources]
    scores = [SOURCE_TIERS.get(t, {}).get("score", 0.2) for t in tiers]
    avg_score = sum(scores) / len(scores)

    has_s = any(t == "S" for t in tiers)
    has_a_or_s = any(t in ("S", "A") for t in tiers)

    from src.analyzer.gt_conflict_detector import detect_field_conflict
    conflict = detect_field_conflict(field_name, sources)

    if has_s and not conflict["has_conflict"] and avg_score >= 0.8:
        return "high"
    if has_a_or_s and not conflict["has_conflict"] and avg_score >= 0.5:
        return "medium"
    if avg_score >= 0.3 and not conflict["has_conflict"]:
        return "low"
    if len(sources) >= 2 and not conflict["has_conflict"]:
        return "low"
    if conflict["has_conflict"]:
        return "uncertain"
    return "low"
