"""Unified enums for Phase A — single source of truth for all quality/health/mapping types."""

from enum import Enum


class TemplateLevel(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class QuestionType(str, Enum):
    BRAND_DEFINITION = "brand_definition"
    BRAND_ATTRIBUTE = "brand_attribute"
    BRAND_COMPARISON = "brand_comparison"
    BRAND_TRUST = "brand_trust"
    CATEGORY_RECOMMENDATION = "category_recommendation"
    SCENARIO_SOLUTION = "scenario_solution"
    USER_RECOMMENDATION = "user_recommendation"
    GENERIC_ADVICE = "generic_advice"


class QuestionScope(str, Enum):
    BRAND_DIRECTED = "brand_directed"
    BRAND_ADJACENT = "brand_adjacent"
    CATEGORY_DIRECTED = "category_directed"
    SCENARIO_DIRECTED = "scenario_directed"
    GENERIC = "generic"


class SubjectType(str, Enum):
    TARGET_BRAND = "target_brand"
    COMPETITOR = "competitor"
    CATEGORY = "category"
    GENERIC = "generic"
    UNKNOWN = "unknown"


class HallucinationVerdict(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    TEMPLATE_INVALID = "template_invalid"
    GENERIC_STATEMENT = "generic_statement"
    NOT_ABOUT_BRAND = "not_about_brand"
    GT_INSUFFICIENT = "gt_insufficient"
    NOT_CHECKABLE = "not_checkable"
    AMBIGUOUS = "ambiguous"


class ClaimNature(str, Enum):
    """声明认知性质 (epistemological nature of a claim).

    DB column is claim_type for readability but represents claim NATURE,
    not subject type or predicate domain.
    """
    FACT = "fact"              # 事实 — 可验证的客观陈述
    OPINION = "opinion"        # 观点 — 主观判断/评价
    SPECULATION = "speculation"  # 推测 — 前瞻性/未经证实的声明
    UNKNOWN = "unknown"        # 无法判定


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    INFO = "Info"


class DenominatorType(str, Enum):
    RECOMMENDATION_LIST_RESPONSES = "recommendation_list_responses"
    RANKED_RECOMMENDATION_RESPONSES = "ranked_recommendation_responses"
    BRAND_MENTION_ELIGIBLE_RESPONSES = "brand_mention_eligible_responses"
    CHECKABLE_TARGET_BRAND_CLAIMS = "checkable_target_brand_claims"
    EXPECTED_BRAND_FIELDS = "expected_brand_fields"
    SOURCE_CITATION_ELIGIBLE_RESPONSES = "source_citation_eligible_responses"
    COMPETITOR_COMPARISON_CLAIMS = "competitor_comparison_claims"
    SCENARIO_ELIGIBLE_RESPONSES = "scenario_eligible_responses"
    TRUST_RISK_ELIGIBLE_RESPONSES = "trust_risk_eligible_responses"
