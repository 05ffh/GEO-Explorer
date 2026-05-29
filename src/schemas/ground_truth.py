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

# Chinese display names for all KPIs
KPI_DISPLAY_NAMES = {
    # 基础 KPI
    "sov": "声量份额 (SOV)",
    "first_rec_rate": "首次推荐率",
    "accuracy_rate": "准确率",
    "completeness_rate": "完备性",
    "citation_rate": "引用率",
    # 扩展 KPI
    "scenario_recall": "场景联想率",
    "semantic_stability": "语义锚点稳定度",
    "differentiation": "差异化程度",
    "cross_platform_consistency": "跨平台一致性",
    "recommendation_quality": "推荐理由质量",
    # 统计
    "sample_size": "样本量",
    "failure_rate": "失败率",
}

