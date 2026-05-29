def detect_conflicts(sources: list[dict]) -> dict:
    values = [s.get("value", "")[:100] for s in sources if s.get("value")]
    unique = set(values)
    return {
        "conflict_count": len(unique) - 1 if len(unique) > 1 else 0,
        "has_conflict": len(unique) > 1,
    }
