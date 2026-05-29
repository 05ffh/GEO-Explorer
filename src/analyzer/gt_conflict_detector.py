def normalize_field_value(field_name: str, value) -> str:
    """Normalize value based on field type for comparison."""
    val = str(value).strip()
    if field_name in ("official_domains",):
        return val.lower().replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]
    if field_name in ("official_name",):
        return val.lower().replace("（", "(").replace("）", ")")
    if field_name in ("pricing", "certifications", "awards", "funding"):
        return val.lower().strip()
    return val[:200].strip()


def detect_conflicts(sources: list[dict]) -> dict:
    """Basic conflict detection based on value comparison (legacy interface)."""
    values = [s.get("value", "")[:100] for s in sources if s.get("value")]
    unique = set(values)
    return {
        "conflict_count": len(unique) - 1 if len(unique) > 1 else 0,
        "has_conflict": len(unique) > 1,
    }


def detect_field_conflict(field_name: str, sources: list[dict]) -> dict:
    """Field-type-aware conflict detection.

    Different fields use different normalization strategies:
    - official_name: case-insensitive, paren-normalized
    - official_domains: domain extraction
    - pricing/certifications: exact match after normalization
    """
    normalized = []
    for s in sources:
        v = s.get("value", "")
        if isinstance(v, list):
            normalized.append(",".join(sorted(str(x).strip().lower() for x in v)))
        else:
            nv = normalize_field_value(field_name, v)
            if nv:
                normalized.append(nv)

    if len(normalized) <= 1:
        return {"has_conflict": False, "conflict_type": "none",
                "normalized_values": normalized, "explanation": "Too few values to compare"}

    unique = set(normalized)
    has_conflict = len(unique) > 1

    if not has_conflict:
        return {"has_conflict": False, "conflict_type": "none",
                "normalized_values": list(unique), "explanation": "All sources agree"}

    if field_name in ("official_name", "official_domains"):
        ctype, exp = "identity_conflict", "Sources disagree on brand identity"
    elif field_name in ("category", "industry", "positioning"):
        ctype, exp = "classification_conflict", "Sources classify the brand differently"
    elif field_name in ("pricing", "certifications", "awards", "funding"):
        ctype, exp = "factual_conflict", "Sources disagree on verifiable facts"
    else:
        ctype, exp = "value_mismatch", f"{len(unique)} distinct values found"

    return {
        "has_conflict": True, "conflict_type": ctype,
        "normalized_values": list(unique)[:5], "explanation": exp,
    }
