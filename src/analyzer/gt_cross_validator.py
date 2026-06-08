"""GT Cross Validator — upgrade AI source tiers via search evidence corroboration.

P0-1~10: Cross-validates AI platform evidence against search results.
- AI source_type stays ai_platform (P0-1)
- Only S/A/B search sources can trigger A/B upgrade (P0-2)
- validation_status tracks confirmation level (P0-3)
- Field-specific matchers prevent false positives (P0-4)
- Full trace with match_score and upgrade_reason (P0-5)
- Search source tier never modified (P0-7)
- AI consensus without search stays C (P0-9)
"""

import re
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CROSS_VALIDATION_VERSION = "v1"


@dataclass
class SourceEvidence:
    """Unified evidence structure for aggregate_all_fields input/output (P0-8)."""
    field_name: str
    value: str
    source_type: str           # "ai_platform" | "search_result"
    source_tier: str           # S/A/B/C/D
    source_quality: str        # high/medium/low
    provider: str
    url: str = ""
    excerpt: str = ""
    # AI-only (populated by cross validator)
    original_source_tier: str | None = None
    validation_status: str | None = None
    matched_search_sources: list = field(default_factory=list)
    match_score: float | None = None
    upgrade_reason: str | None = None
    # Time-sensitive
    published_at: str | None = None
    value_as_of_date: str | None = None
    staleness_status: str | None = None


def cross_validate_ai_with_search(
    ai_sources: list[SourceEvidence],
    search_sources: list[SourceEvidence],
) -> list[SourceEvidence]:
    """Cross-validate AI platform evidence against search evidence.

    Returns: updated list of AI SourceEvidence with validation fields populated.
    Search sources are NOT modified (P0-7).
    """
    # Group search sources by field
    search_by_field: dict[str, list[SourceEvidence]] = {}
    for s in search_sources:
        search_by_field.setdefault(s.field_name, []).append(s)

    validated = []
    for ai in ai_sources:
        field_searches = search_by_field.get(ai.field_name, [])
        if not field_searches:
            ai.validation_status = "unconfirmed"
            ai.source_tier = "C"
            validated.append(ai)
            continue

        # Find matching search sources for this AI value
        matches, contradictions = _match_against_search(ai, field_searches)

        if contradictions and _should_downgrade(contradictions):
            ai.source_tier = "D"
            ai.validation_status = "contradicted"
            ai.matched_search_sources = contradictions
            ai.upgrade_reason = (
                f"AI value '{ai.value[:80]}' contradicted by "
                f"{len(contradictions)} search sources"
            )
        elif matches:
            ai = _apply_upgrade(ai, matches)
        elif not matches and not contradictions:
            ai.validation_status = "unconfirmed"
            ai.source_tier = "C"
        else:
            ai.validation_status = "ambiguous"
            ai.source_tier = "C"

        validated.append(ai)

    return validated


def _match_against_search(
    ai: SourceEvidence, search_sources: list[SourceEvidence],
) -> tuple[list[dict], list[dict]]:
    """Compare AI value against search sources. Returns (matches, contradictions)."""
    matches = []
    contradictions = []

    for s in search_sources:
        if s.source_tier == "D":
            continue  # P0-2: D-tier never used for validation

        match_result = _field_match(ai.field_name, ai.value, s)

        if match_result["is_match"]:
            matches.append({
                "provider": s.provider,
                "url": s.url,
                "source_tier": s.source_tier,
                "matched_text": match_result.get("matched_text", ""),
                "match_type": match_result.get("match_type", "unknown"),
                "match_score": match_result.get("match_score", 0.5),
            })
        elif match_result.get("is_contradiction"):
            contradictions.append({
                "provider": s.provider,
                "url": s.url,
                "source_tier": s.source_tier,
                "search_value": s.value[:200],
                "match_type": match_result.get("match_type", "unknown"),
            })

    return matches, contradictions


def _should_downgrade(contradictions: list[dict]) -> bool:
    """P0-3: Downgrade to D only with strong contradiction.

    Requirements: 1 S-tier contradiction, or >= 2 A/B contradictions.
    Single B-tier contradiction does NOT trigger downgrade.
    """
    s_contradictions = [c for c in contradictions if c["source_tier"] == "S"]
    if s_contradictions:
        return True
    ab_contradictions = [c for c in contradictions if c["source_tier"] in ("A", "B")]
    return len(ab_contradictions) >= 2


def _apply_upgrade(ai: SourceEvidence, matches: list[dict]) -> SourceEvidence:
    """Apply tier upgrade based on matching search sources (P0-2)."""
    tiers = [m["source_tier"] for m in matches]
    has_s = "S" in tiers
    has_a = "A" in tiers
    has_b = "B" in tiers

    if has_s:
        ai.source_tier = "A"
        ai.validation_status = "confirmed_strong"
    elif has_a and len([t for t in tiers if t in ("A", "B")]) >= 2:
        ai.source_tier = "B"
        ai.validation_status = "confirmed_multi"
    elif has_a:
        ai.source_tier = "B"
        ai.validation_status = "confirmed_strong"
    elif has_b and len([t for t in tiers if t == "B"]) >= 2:
        ai.source_tier = "B"
        ai.validation_status = "confirmed_multi"
    elif has_b:
        ai.source_tier = "B"
        ai.validation_status = "confirmed_single"
    else:
        # Only C-tier matches → weak support
        ai.source_tier = "C"
        ai.validation_status = "weak_support"

    ai.matched_search_sources = matches[:5]
    ai.match_score = round(sum(m.get("match_score", 0.5) for m in matches) / len(matches), 3)
    ai.upgrade_reason = (
        f"AI {ai.field_name}='{ai.value[:80]}' {ai.validation_status} "
        f"by {len(matches)} search source(s) (tiers: {','.join(tiers[:3])})"
    )
    return ai


# ── Field-specific matchers (P0-4) ───────────────────────────────────────────


def _field_match(field_name: str, ai_value: str, search: SourceEvidence) -> dict:
    """Match AI value against a search source using field-specific logic."""
    sv = search.value
    if not sv:
        return {"is_match": False, "is_contradiction": False}

    if field_name == "founded_year":
        return _match_founded_year(ai_value, sv)
    elif field_name == "official_domains":
        return _match_domain(ai_value, sv)
    elif field_name == "store_count":
        return _match_store_count(ai_value, sv)
    elif field_name in ("core_products", "core_features"):
        return _match_product_list(ai_value, sv)
    elif field_name == "headquarters":
        return _match_headquarters(ai_value, sv)
    elif field_name in ("official_name",):
        return _match_official_name(ai_value, sv)
    else:
        return _match_generic(ai_value, sv)


def _extract_number(value: str) -> int | None:
    """Extract a 4-digit number from text."""
    m = re.search(r'\b(\d{4})\b', str(value))
    return int(m.group(1)) if m else None


def _normalize_domain(value: str) -> str:
    """Normalize domain: lowercase, strip www/http/https/trailing slash."""
    v = str(value).lower().strip()
    v = v.replace("https://", "").replace("http://", "")
    v = v.lstrip("www.").rstrip("/")
    return v.split("/")[0]


def _match_founded_year(ai_value: str, search_value: str) -> dict:
    """P0-4: Match founded_year — avoid confusing with listed/entered_market years."""
    ai_year = _extract_number(ai_value)
    sv_year = _extract_number(search_value)

    result = {"is_match": False, "is_contradiction": False}

    if ai_year is None or sv_year is None:
        return result

    # Check context words to detect non-founded-year mentions
    sv_lower = search_value.lower()
    non_founded_contexts = [
        "list", "ipo", "public", "enter", "entered", "china", "market",
        "open", "first store", "launch",
    ]
    founded_contexts = ["founded", "found", "established", "成立", "创始"]

    is_search_about_founded = any(k in sv_lower for k in founded_contexts)
    is_search_about_other = any(k in sv_lower for k in non_founded_contexts)

    if is_search_about_other and not is_search_about_founded:
        # Search is talking about a different year (listed/entered) — NOT a match
        return {"is_match": False, "is_contradiction": False,
                "match_type": "year_scope_mismatch"}

    if ai_year == sv_year:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "number_exact", "match_score": 1.0,
                "matched_text": search_value[:100]}

    # Different year with founded context → contradiction
    if is_search_about_founded and not is_search_about_other:
        return {"is_match": False, "is_contradiction": True,
                "match_type": "year_mismatch"}

    return result


def _match_domain(ai_value: str, search_value: str) -> dict:
    """P0-4: Match official_domains — normalize and compare."""
    ai_domain = _normalize_domain(ai_value)
    sv_domain = _normalize_domain(search_value)

    if not ai_domain or not sv_domain:
        return {"is_match": False, "is_contradiction": False}

    if ai_domain == sv_domain:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "domain_exact", "match_score": 1.0,
                "matched_text": search_value[:100]}

    # Check if one is a subdomain of the other
    if ai_domain.endswith("." + sv_domain) or sv_domain.endswith("." + ai_domain):
        return {"is_match": True, "is_contradiction": False,
                "match_type": "domain_subdomain", "match_score": 0.9,
                "matched_text": search_value[:100]}

    return {"is_match": False, "is_contradiction": False,
            "match_type": "domain_mismatch"}


def _match_store_count(ai_value: str, search_value: str) -> dict:
    """P0-4: Match store_count — must consider region and date scope."""
    ai_nums = re.findall(r'\d[\d,]*', str(ai_value))
    sv_nums = re.findall(r'\d[\d,]*', str(search_value))

    if not ai_nums or not sv_nums:
        return {"is_match": False, "is_contradiction": False}

    # Check scope context
    sv_lower = search_value.lower()
    ai_lower = str(ai_value).lower()

    # Scope mismatch detection
    ai_global = any(k in ai_lower for k in ("global", "全球", "worldwide"))
    sv_china = any(k in sv_lower for k in ("china", "中国", "china market"))
    sv_global = any(k in sv_lower for k in ("global", "全球", "worldwide"))

    if ai_global and sv_china:
        return {"is_match": False, "is_contradiction": False,
                "match_type": "scope_mismatch"}

    # Compare largest number found
    ai_num = int(ai_nums[0].replace(",", ""))
    sv_num = int(sv_nums[0].replace(",", ""))

    if ai_num == sv_num:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "number_exact", "match_score": 0.9,
                "matched_text": search_value[:100]}

    # Different numbers → potential contradiction but check scope first
    if ai_global == sv_global:
        return {"is_match": False, "is_contradiction": True,
                "match_type": "count_mismatch"}

    return {"is_match": False, "is_contradiction": False,
            "match_type": "scope_mismatch"}


def _match_product_list(ai_value: str, search_value: str) -> dict:
    """P0-4: Match core_products — token overlap, partial support OK."""
    ai_tokens = set(re.findall(r'[\w一-鿿]+', str(ai_value).lower()))
    sv_tokens = set(re.findall(r'[\w一-鿿]+', str(search_value).lower()))

    if not ai_tokens or not sv_tokens:
        return {"is_match": False, "is_contradiction": False}

    overlap = ai_tokens & sv_tokens
    if not overlap:
        return {"is_match": False, "is_contradiction": False,
                "match_type": "no_overlap"}

    overlap_ratio = len(overlap) / len(ai_tokens)
    score = round(overlap_ratio, 3)

    if overlap_ratio >= 0.5:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "token_overlap", "match_score": score,
                "matched_text": search_value[:100]}
    elif overlap_ratio >= 0.2:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "partial_overlap", "match_score": score,
                "matched_text": search_value[:100]}

    return {"is_match": False, "is_contradiction": False,
            "match_type": "weak_overlap"}


def _match_headquarters(ai_value: str, search_value: str) -> dict:
    """P0-4: Match headquarters — city/country layered matching."""
    ai_lower = str(ai_value).lower()
    sv_lower = search_value.lower()

    # Check for scope mismatch: global vs regional
    ai_has_china = any(k in ai_lower for k in ("china", "中国", "shanghai", "beijing"))
    sv_has_china = any(k in sv_lower for k in ("china", "中国", "shanghai", "beijing"))

    if ai_has_china != sv_has_china:
        return {"is_match": False, "is_contradiction": False,
                "match_type": "scope_mismatch"}

    # City/country name matching
    cities = ["seattle", "new york", "london", "tokyo", "首尔", "东京",
              "西雅图", "纽约", "伦敦", "shanghai", "beijing", "上海", "北京"]
    ai_cities = [c for c in cities if c in ai_lower]
    sv_cities = [c for c in cities if c in sv_lower]

    if ai_cities and sv_cities:
        if any(c in sv_cities for c in ai_cities):
            return {"is_match": True, "is_contradiction": False,
                    "match_type": "city_match", "match_score": 0.9,
                    "matched_text": search_value[:100]}
        else:
            return {"is_match": False, "is_contradiction": True,
                    "match_type": "city_mismatch"}

    return _match_generic(ai_value, search_value)


def _match_official_name(ai_value: str, search_value: str) -> dict:
    """P0-4: Match official_name — entity + alias matching."""
    ai_lower = str(ai_value).lower().strip()
    sv_lower = search_value.lower()

    if ai_lower in sv_lower or sv_lower in ai_lower:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "substring_match", "match_score": 0.95,
                "matched_text": search_value[:100]}

    # Token overlap for multi-word names
    ai_tokens = set(ai_lower.split())
    sv_tokens = set(sv_lower.split())
    if ai_tokens and sv_tokens:
        overlap = len(ai_tokens & sv_tokens) / max(len(ai_tokens), 1)
        if overlap >= 0.5:
            return {"is_match": True, "is_contradiction": False,
                    "match_type": "token_overlap", "match_score": overlap,
                    "matched_text": search_value[:100]}

    return {"is_match": False, "is_contradiction": False,
            "match_type": "no_match"}


def _match_generic(ai_value: str, search_value: str) -> dict:
    """Default matcher — keyword overlap."""
    ai_lower = str(ai_value).lower()
    sv_lower = search_value.lower()

    # Direct substring
    if ai_lower in sv_lower or sv_lower in ai_lower:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "substring_match", "match_score": 0.7,
                "matched_text": search_value[:100]}

    # Token overlap
    ai_tokens = set(re.findall(r'[\w一-鿿]+', ai_lower))
    sv_tokens = set(re.findall(r'[\w一-鿿]+', sv_lower))

    if not ai_tokens or not sv_tokens:
        return {"is_match": False, "is_contradiction": False}

    overlap = len(ai_tokens & sv_tokens) / max(len(ai_tokens), 1)
    if overlap >= 0.5:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "token_overlap", "match_score": round(overlap, 3),
                "matched_text": search_value[:100]}

    return {"is_match": False, "is_contradiction": False,
            "match_type": "no_match"}
