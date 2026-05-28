GT_FIELD_LEVELS = {
    "official_name": "P0",
    "aliases": "P0",
    "industry": "P0",
    "category": "P0",
    "positioning": "P0",
    "official_domains": "P0",
    "competitors": "P0",
    "target_users": "P1",
    "core_scenarios": "P1",
    "differentiators": "P1",
    "trusted_sources": "P1",
    "forbidden_claims": "P1",
    "tech_tags": "P2",
    "market_position": "P2",
}

GT_LIST_FIELDS = {
    "aliases", "core_scenarios", "differentiators", "tech_tags",
    "trusted_sources", "forbidden_claims", "official_domains", "competitors",
}

GT_REQUIRED_FOR_COMPLETENESS = {
    k for k in GT_FIELD_LEVELS if k != "forbidden_claims"
}
