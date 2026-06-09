"""Field-level collection strategies (P0 — expert review).

Different GT fields need different collection approaches:
- registration fields: search_first, skip AI when possible
- description fields: ai_plus_search, AI fill is acceptable
- enumeration fields: search_plus_ai, structured from search results
- constraint fields: search_first, must have human review
"""

FIELD_POLICIES = {
    "official_name": {
        "category": "registration",
        "strategy": "search_first",
        "requires_search_verification": True,
        "allow_ai_fill": False,
        "requires_human_review": True,
        "priority": "P0",
    },
    "founded_year": {
        "category": "registration",
        "strategy": "search_first",
        "requires_search_verification": True,
        "allow_ai_fill": False,
        "requires_human_review": True,
        "priority": "P0",
    },
    "official_domains": {
        "category": "registration",
        "strategy": "search_first",
        "requires_search_verification": True,
        "allow_ai_fill": False,
        "requires_human_review": True,
        "priority": "P0",
    },
    "headquarters": {
        "category": "registration",
        "strategy": "search_verify",
        "requires_search_verification": True,
        "allow_ai_fill": True,
        "requires_human_review": True,
        "priority": "P0",
    },
    "core_products": {
        "category": "enumeration",
        "strategy": "search_plus_ai",
        "requires_search_verification": True,
        "allow_ai_fill": True,
        "requires_human_review": True,
        "priority": "P0",
    },
    "positioning": {
        "category": "description",
        "strategy": "ai_plus_search",
        "requires_search_verification": False,
        "allow_ai_fill": True,
        "requires_human_review": False,
        "priority": "P1",
    },
    "key_differentiators": {
        "category": "description",
        "strategy": "ai_plus_search",
        "requires_search_verification": False,
        "allow_ai_fill": True,
        "requires_human_review": False,
        "priority": "P1",
    },
    "industry": {
        "category": "classification",
        "strategy": "search_plus_ai",
        "requires_search_verification": True,
        "allow_ai_fill": True,
        "requires_human_review": False,
        "priority": "P1",
    },
    "category": {
        "category": "classification",
        "strategy": "search_plus_ai",
        "requires_search_verification": True,
        "allow_ai_fill": True,
        "requires_human_review": False,
        "priority": "P1",
    },
    "target_users": {
        "category": "description",
        "strategy": "ai_plus_search",
        "requires_search_verification": False,
        "allow_ai_fill": True,
        "requires_human_review": False,
        "priority": "P1",
    },
    "core_scenarios": {
        "category": "description",
        "strategy": "ai_plus_search",
        "requires_search_verification": False,
        "allow_ai_fill": True,
        "requires_human_review": False,
        "priority": "P1",
    },
    "target_competitors": {
        "category": "relation",
        "strategy": "ai_plus_search",
        "requires_search_verification": True,
        "allow_ai_fill": True,
        "requires_human_review": True,
        "priority": "P1",
    },
    "forbidden_claims": {
        "category": "constraint",
        "strategy": "search_first",
        "requires_search_verification": True,
        "allow_ai_fill": False,
        "requires_human_review": True,
        "priority": "P0",
    },
}


def get_high_priority_fields(priority: str = "P0") -> list[str]:
    """Return field names with the given priority level."""
    return [k for k, v in FIELD_POLICIES.items() if v.get("priority") == priority]


def get_fields_by_strategy(strategy: str) -> list[str]:
    """Return field names using the given collection strategy."""
    return [k for k, v in FIELD_POLICIES.items() if v.get("strategy") == strategy]
