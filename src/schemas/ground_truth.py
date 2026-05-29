GT_FIELD_LEVELS = {
    "official_name": "P0",
    "aliases": "P0",
    "industry": "P0",
    "category": "P0",
    "positioning": "P0",
    "official_domains": "P0",
    "target_competitors": "P0",
    "core_products": "P0",
    "target_users": "P1",
    "core_scenarios": "P1",
    "key_differentiators": "P1",
    "source_of_truth_by_field": "P1",
    "forbidden_claims": "P1",
    "core_features": "P1",
    "scenario_keywords": "P2",
    "subcategory": "P2",
    "best_fit_users": "P2",
    "alternative_solutions": "P2",
    "common_misconceptions": "P2",
    "official_docs": "P2",
    "official_channels": "P2",
    "preferred_recommendation_reasons": "P2",
}

GT_LIST_FIELDS = {
    "aliases", "core_scenarios", "key_differentiators", "scenario_keywords",
    "official_domains", "target_competitors", "source_of_truth_by_field",
    "forbidden_claims", "alternative_solutions", "core_features",
    "official_docs", "official_channels",
}

GT_REQUIRED_FOR_COMPLETENESS = {
    k for k in GT_FIELD_LEVELS if k != "forbidden_claims"
}
