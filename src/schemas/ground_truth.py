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

# --- Phase 11: Source Tier System ---

SOURCE_TIERS = {
    "S": {"label": "官方/权威来源", "score": 1.0,
          "examples": ["官网", "官方文档", "政府/工商/交易所"]},
    "A": {"label": "权威第三方", "score": 0.7,
          "examples": ["权威媒体", "行业数据库", "专业评测"]},
    "B": {"label": "线索来源", "score": 0.4,
          "examples": ["搜索摘要", "百科", "聚合页"]},
    "C": {"label": "AI 候选", "score": 0.2,
          "examples": ["AI 平台回答"]},
    "D": {"label": "不可信", "score": 0.0,
          "examples": ["论坛", "自媒体", "未知站点"],
          "usage": "不进入正式 GT"},
}

FIELD_EVIDENCE_REQUIREMENTS = {
    "official_name": {"min_tier": "S", "min_sources": 1},
    "category": {"min_tier": "A", "min_sources": 1},
    "positioning": {"min_tier": "S", "min_sources": 1},
    "core_products": {"min_tier": "A", "min_sources": 1},
    "target_users": {"min_tier": "A", "min_sources": 1},
    "core_scenarios": {"min_tier": "B", "min_sources": 1},
    "key_differentiators": {"min_tier": "B", "min_sources": 1},
    "target_competitors": {"min_tier": "B", "min_sources": 2},
    "official_domains": {"min_tier": "S", "min_sources": 1},
    "pricing": {"min_tier": "S", "min_sources": 1},
    "certifications": {"min_tier": "S", "min_sources": 1},
    "awards": {"min_tier": "S", "min_sources": 1},
    "customer_cases": {"min_tier": "A", "min_sources": 1},
    "funding": {"min_tier": "S", "min_sources": 1},
    "proof_points": {"min_tier": "A", "min_sources": 1},
}

HIGH_RISK_FIELD_TIER_REQUIREMENTS = {
    "official_name": "S",
    "positioning": "S",
    "pricing": "S",
    "certifications": "S",
    "funding": "S",
    "customer_cases": "A",
    "proof_points": "A",
}

FIELD_RISK_LEVELS = {
    "low": ["aliases", "subcategory", "scenario_keywords", "alternative_solutions",
            "common_misconceptions", "official_docs", "official_channels"],
    "medium": ["industry", "core_products", "core_features", "target_users",
               "core_scenarios", "best_fit_users", "preferred_recommendation_reasons"],
    "high": ["official_name", "category", "positioning", "target_competitors",
             "key_differentiators", "forbidden_claims", "source_of_truth_by_field",
             "proof_points", "pricing", "certifications", "customers", "awards", "funding"],
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

