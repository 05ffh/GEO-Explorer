"""GT Field Verifier — P0-1 high-risk field targeted search verification.

After AI collection, run targeted Tavily searches for key fields
to corroborate or challenge AI-proposed values. Only S/A/B search
results can upgrade AI evidence tier. C-tier = weak_support only.
AI evidence can never reach S-tier.
"""

import logging
import re
from urllib.parse import urlparse

from src.search.search_adapter import EnhancedSearchResult

logger = logging.getLogger(__name__)

# ── Query templates per field ─────────────────────────────────────────────────

VERIFICATION_QUERIES = {
    "official_name": [
        "{brand} 官方名称",
        "{brand} 公司简介",
        "{brand} official name",
        "{brand} 公司全称",
    ],
    "founded_year": [
        "{brand} 成立时间",
        "{brand} founded {value}",
        "{brand} company history {value}",
        "{brand} 公司历史",
    ],
    "official_domains": [
        "{brand} 官方网站",
        "{brand} 官网",
        "{brand} official website",
        "{brand} 官方网址",
    ],
    "headquarters": [
        "{brand} 总部",
        "{brand} headquarters",
        "{brand} 公司地址",
        "{brand} 总部地址",
    ],
    "core_products": [
        "{brand} 产品",
        "{brand} 核心产品",
        "{brand} products",
        "{brand} 产品列表",
    ],
}


async def verify_high_risk_fields(
    brand_name: str,
    ai_field_values: dict[str, str],
    search_adapter,
    fields_to_verify: list[str] | None = None,
) -> dict[str, dict]:
    """Verify AI-proposed values for high-risk fields via Tavily search.

    Args:
        brand_name: brand name for query generation
        ai_field_values: {field_name: ai_proposed_value}
        search_adapter: TavilySearchAdapter instance
        fields_to_verify: specific fields to verify (default: all P0 from FIELD_POLICIES)

    Returns:
        {field_name: {validated_tier, validation_status, matched_sources,
                       match_score, upgrade_reason, original_tier}}
    """
    from src.gt.field_policy import FIELD_POLICIES

    if fields_to_verify is None:
        fields_to_verify = [
            f for f, p in FIELD_POLICIES.items()
            if p.get("priority") == "P0" and p.get("requires_search_verification")
        ]

    result = {}
    for field in fields_to_verify:
        ai_value = ai_field_values.get(field, "")
        try:
            result[field] = await _verify_one_field(
                brand_name, field, ai_value, search_adapter,
            )
        except Exception as e:
            logger.warning("Field verification failed for %s: %s", field, e)
            result[field] = {
                "validated_tier": "C",
                "validation_status": "unconfirmed",
                "matched_sources": [],
                "match_score": 0.0,
                "upgrade_reason": f"Verification error: {e}",
                "original_tier": "C",
            }

    return result


async def _verify_one_field(
    brand_name: str, field_name: str, ai_value: str, adapter,
) -> dict:
    """Verify a single field."""
    queries = _build_verification_queries(brand_name, field_name, ai_value)
    all_results = []
    for q in queries[:3]:
        try:
            items = await adapter.search(q, limit=5)
            all_results.extend(items)
        except Exception:
            continue

    if not all_results:
        return {
            "validated_tier": "C",
            "validation_status": "unconfirmed",
            "matched_sources": [],
            "match_score": 0.0,
            "upgrade_reason": "No search results found",
            "original_tier": "C",
        }

    matches, contradictions = _evaluate_results(field_name, ai_value, all_results)

    return _determine_result(field_name, ai_value, matches, contradictions)


def _build_verification_queries(brand: str, field: str, value: str) -> list[str]:
    templates = VERIFICATION_QUERIES.get(field, ["{brand} {field}"])
    return [t.format(brand=brand, field=field, value=value) for t in templates]


def _evaluate_results(
    field_name: str, ai_value: str, results: list[EnhancedSearchResult],
) -> tuple[list[dict], list[dict]]:
    """Evaluate search results against AI value using field-specific matching."""
    matches = []
    contradictions = []

    for r in results:
        if r.source_tier == "D":
            continue

        match_result = _field_match(field_name, ai_value, r)

        if match_result.get("is_match"):
            if r.source_tier in ("S", "A", "B"):
                matches.append({
                    "provider": r.provider,
                    "url": r.url,
                    "source_tier": r.source_tier,
                    "matched_text": match_result.get("matched_text", ""),
                    "match_type": match_result.get("match_type", ""),
                    "match_score": match_result.get("match_score", 0.5),
                })
            elif r.source_tier == "C":
                matches.append({
                    "provider": r.provider,
                    "url": r.url,
                    "source_tier": "C",
                    "matched_text": match_result.get("matched_text", ""),
                    "match_type": "weak_match",
                    "match_score": match_result.get("match_score", 0.3),
                })
        elif match_result.get("is_contradiction"):
            contradictions.append({
                "provider": r.provider,
                "url": r.url,
                "source_tier": r.source_tier,
                "search_value": r.snippet[:200],
            })

    return matches, contradictions


def _determine_result(
    field_name: str, ai_value: str, matches: list[dict], contradictions: list[dict],
) -> dict:
    """Determine final validated tier based on matches and contradictions."""
    base = {
        "validated_tier": "C",
        "validation_status": "unconfirmed",
        "matched_sources": [],
        "match_score": 0.0,
        "upgrade_reason": "",
        "original_tier": "C",
    }

    # Check for contradictions first (P0-3: downgrade)
    s_contra = [c for c in contradictions if c["source_tier"] == "S"]
    ab_contra = [c for c in contradictions if c["source_tier"] in ("A", "B")]
    if s_contra or len(ab_contra) >= 2:
        base["validated_tier"] = "D"
        base["validation_status"] = "contradicted"
        base["upgrade_reason"] = (
            f"AI value '{ai_value[:80]}' contradicted by "
            f"{len(s_contra) + len(ab_contra)} high-tier sources"
        )
        return base

    if not matches:
        return base

    # Separate S/A/B matches from C-tier matches
    sab_matches = [m for m in matches if m["source_tier"] in ("S", "A", "B")]
    c_matches = [m for m in matches if m["source_tier"] == "C"]

    if sab_matches:
        tiers = [m["source_tier"] for m in sab_matches]
        has_s = "S" in tiers
        has_a = "A" in tiers
        ab_count = sum(1 for t in tiers if t in ("A", "B"))

        if has_s:
            base["validated_tier"] = "A"
            base["validation_status"] = "confirmed_strong"
        elif has_a and ab_count >= 2:
            base["validated_tier"] = "B"
            base["validation_status"] = "confirmed_multi"
        elif has_a:
            base["validated_tier"] = "B"
            base["validation_status"] = "confirmed_strong"
        elif ab_count >= 2:
            base["validated_tier"] = "B"
            base["validation_status"] = "confirmed_multi"
        elif ab_count == 1:
            base["validated_tier"] = "B"
            base["validation_status"] = "confirmed_single"

        base["matched_sources"] = sab_matches[:5]
        scores = [m.get("match_score", 0.5) for m in sab_matches]
        base["match_score"] = round(sum(scores) / len(scores), 3)
        base["upgrade_reason"] = (
            f"AI {field_name}='{ai_value[:80]}' {base['validation_status']} "
            f"by {len(sab_matches)} source(s) (tiers: {','.join(tiers[:3])})"
        )
    elif c_matches:
        base["validated_tier"] = "C"
        base["validation_status"] = "weak_support"
        base["matched_sources"] = c_matches[:3]
        base["upgrade_reason"] = (
            f"AI {field_name}='{ai_value[:80]}' has weak C-tier support only"
        )

    return base


# ── Field-specific matchers ──────────────────────────────────────────────────


def _field_match(field_name: str, ai_value: str, result: EnhancedSearchResult) -> dict:
    sv = result.snippet
    if not sv:
        return {"is_match": False, "is_contradiction": False}

    if field_name == "founded_year":
        return _match_founded_year(ai_value, sv)
    elif field_name == "official_domains":
        return _match_domain(ai_value, result.url)
    elif field_name == "headquarters":
        return _match_headquarters(ai_value, sv)
    elif field_name == "core_products":
        return _match_product_list(ai_value, sv)
    elif field_name == "official_name":
        return _match_official_name(ai_value, sv)
    else:
        return _match_generic(ai_value, sv)


def _extract_year(text: str) -> int | None:
    m = re.search(r'\b(\d{4})\b', str(text))
    return int(m.group(1)) if m else None


def _match_founded_year(ai_value: str, search_text: str) -> dict:
    ai_year = _extract_year(ai_value)
    sv_year = _extract_year(search_text)
    if ai_year is None or sv_year is None:
        return {"is_match": False, "is_contradiction": False}

    sv_lower = search_text.lower()
    founded_kw = ["founded", "found", "established", "成立", "创始"]
    non_founded_kw = ["list", "ipo", "public", "enter", "china", "market",
                      "first store", "open"]

    is_founded = any(k in sv_lower for k in founded_kw)
    is_other = any(k in sv_lower for k in non_founded_kw)

    if is_other and not is_founded:
        return {"is_match": False, "is_contradiction": False,
                "match_type": "year_scope_mismatch"}

    if ai_year == sv_year:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "number_exact", "match_score": 1.0,
                "matched_text": search_text[:100]}

    if is_founded and not is_other:
        return {"is_match": False, "is_contradiction": True,
                "match_type": "year_mismatch"}

    return {"is_match": False, "is_contradiction": False}


def _match_domain(ai_value: str, url: str) -> dict:
    def norm(d):
        return str(d).lower().replace("https://", "").replace("http://", "").lstrip("www.").rstrip("/").split("/")[0]

    ai_d = norm(ai_value)
    sv_d = norm(urlparse(url).netloc or url)
    if not ai_d or not sv_d:
        return {"is_match": False, "is_contradiction": False}
    if ai_d == sv_d or ai_d.endswith("." + sv_d) or sv_d.endswith("." + ai_d):
        return {"is_match": True, "is_contradiction": False,
                "match_type": "domain_match", "match_score": 0.95,
                "matched_text": url[:100]}
    return {"is_match": False, "is_contradiction": False}


def _match_headquarters(ai_value: str, search_text: str) -> dict:
    ai_l = str(ai_value).lower()
    sv_l = search_text.lower()
    # Detect scope: China vs global
    china_kw = ["china", "中国", "shanghai", "beijing", "上海", "北京"]
    global_kw = ["seattle", "new york", "西雅图", "纽约"]
    ai_is_china = any(k in ai_l for k in china_kw)
    sv_is_china = any(k in sv_l for k in china_kw)
    if ai_is_china != sv_is_china:
        return {"is_match": False, "is_contradiction": False,
                "match_type": "scope_mismatch"}
    return _match_generic(ai_value, search_text)


def _match_product_list(ai_value: str, search_text: str) -> dict:
    ai_t = set(re.findall(r'[\w一-鿿]+', str(ai_value).lower()))
    sv_t = set(re.findall(r'[\w一-鿿]+', search_text.lower()))
    if not ai_t or not sv_t:
        return {"is_match": False, "is_contradiction": False}
    overlap = len(ai_t & sv_t) / max(len(ai_t), 1)
    if overlap >= 0.4:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "partial_overlap" if overlap < 0.7 else "token_overlap",
                "match_score": round(overlap, 3), "matched_text": search_text[:100]}
    return {"is_match": False, "is_contradiction": False}


def _match_official_name(ai_value: str, search_text: str) -> dict:
    ai_l = str(ai_value).lower().strip()
    sv_l = search_text.lower()
    if ai_l and ai_l in sv_l:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "substring_match", "match_score": 0.9,
                "matched_text": search_text[:100]}
    return _match_generic(ai_value, search_text)


def _match_generic(ai_value: str, search_text: str) -> dict:
    ai_l = str(ai_value).lower()
    sv_l = search_text.lower()
    if ai_l and ai_l in sv_l:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "substring_match", "match_score": 0.7,
                "matched_text": search_text[:100]}
    ai_t = set(re.findall(r'[\w一-鿿]+', ai_l))
    sv_t = set(re.findall(r'[\w一-鿿]+', sv_l))
    if not ai_t or not sv_t:
        return {"is_match": False, "is_contradiction": False}
    overlap = len(ai_t & sv_t) / max(len(ai_t), 1)
    if overlap >= 0.5:
        return {"is_match": True, "is_contradiction": False,
                "match_type": "token_overlap", "match_score": round(overlap, 3),
                "matched_text": search_text[:100]}
    return {"is_match": False, "is_contradiction": False}
