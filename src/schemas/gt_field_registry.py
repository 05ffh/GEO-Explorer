"""Field Registry — single source of truth for all GT field definitions."""
from typing import Literal
from pydantic import BaseModel


class GtFieldDefinition(BaseModel):
    key: str
    label: str
    field_type: Literal["string", "list", "number", "object", "boolean"]
    required: bool = False
    multi_value: bool = False
    allow_multiple_primary: bool = False
    category: Literal[
        "identity", "taxonomy", "offering", "market",
        "positioning", "evidence", "industry_specific",
    ]
    applicable_industries: list[str] = []
    aliases: list[str] = []
    template_variables: list[str] = []
    description: str = ""


# ── Complete registry covering Phase A 18 fields ─────────────────────────

GT_FIELD_REGISTRY: dict[str, GtFieldDefinition] = {
    # ── Identity ──
    "official_name": GtFieldDefinition(
        key="official_name", label="官方名称", field_type="string",
        required=True, category="identity",
        description="品牌官方全称",
    ),
    "aliases": GtFieldDefinition(
        key="aliases", label="品牌别名", field_type="list",
        required=False, multi_value=True, allow_multiple_primary=True,
        category="identity",
        description="品牌其他称呼/简称",
    ),

    # ── Taxonomy ──
    "industry": GtFieldDefinition(
        key="industry", label="所属行业", field_type="string",
        required=True, category="taxonomy",
        description="品牌所属行业分类",
    ),
    "category": GtFieldDefinition(
        key="category", label="品类", field_type="string",
        required=True, category="taxonomy",
        description="品牌所在品类",
    ),
    "subcategory": GtFieldDefinition(
        key="subcategory", label="子品类", field_type="string",
        category="taxonomy",
        description="更细分的品类",
    ),

    # ── Positioning ──
    "positioning": GtFieldDefinition(
        key="positioning", label="品牌定位", field_type="string",
        required=True, category="positioning",
        description="品牌核心定位描述",
    ),
    "key_differentiators": GtFieldDefinition(
        key="key_differentiators", label="核心差异化", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="positioning",
        description="与竞品的核心差异点",
    ),
    "forbidden_claims": GtFieldDefinition(
        key="forbidden_claims", label="禁用声明", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="positioning",
        description="品牌禁止使用的夸大/虚假声明",
    ),

    # ── Offering ──
    "core_products": GtFieldDefinition(
        key="core_products", label="核心产品", field_type="list",
        required=True, multi_value=True, allow_multiple_primary=True,
        category="offering",
        description="品牌核心产品/服务列表",
    ),
    "core_features": GtFieldDefinition(
        key="core_features", label="核心功能", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="offering",
        description="品牌核心功能/特性列表",
    ),

    # ── Market ──
    "target_users": GtFieldDefinition(
        key="target_users", label="目标用户", field_type="string",
        category="market",
        description="目标用户群体描述",
    ),
    "target_competitors": GtFieldDefinition(
        key="target_competitors", label="主要竞品", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="market",
        description="主要竞品列表",
    ),
    "core_scenarios": GtFieldDefinition(
        key="core_scenarios", label="核心使用场景", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="market",
        template_variables=["{场景}"],
        description="品牌核心使用场景",
    ),
    "best_fit_users": GtFieldDefinition(
        key="best_fit_users", label="最佳匹配用户", field_type="string",
        category="market",
        description="最适合使用该品牌产品的用户画像",
    ),
    "preferred_recommendation_reasons": GtFieldDefinition(
        key="preferred_recommendation_reasons", label="首选推荐理由", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="market",
        description="推荐该品牌的首选理由",
    ),

    # ── Evidence ──
    "official_domains": GtFieldDefinition(
        key="official_domains", label="官方域名", field_type="list",
        required=True, multi_value=True, allow_multiple_primary=True,
        category="evidence",
        description="品牌官方域名列表",
    ),
    "official_docs": GtFieldDefinition(
        key="official_docs", label="官方文档链接", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="evidence",
        description="官方文档/白皮书/报告链接",
    ),
    "official_channels": GtFieldDefinition(
        key="official_channels", label="官方渠道", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="evidence",
        description="官方社交媒体/客服渠道",
    ),
    "scenario_keywords": GtFieldDefinition(
        key="scenario_keywords", label="场景关键词", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="evidence",
        description="与品牌相关的场景搜索关键词",
    ),
    "source_of_truth_by_field": GtFieldDefinition(
        key="source_of_truth_by_field", label="字段事实来源", field_type="object",
        category="evidence",
        description="每个字段对应的事实来源出处",
    ),
    "alternative_solutions": GtFieldDefinition(
        key="alternative_solutions", label="替代方案", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="market",
        description="替代该品牌的竞争方案",
    ),
    "common_misconceptions": GtFieldDefinition(
        key="common_misconceptions", label="常见误解", field_type="list",
        multi_value=True, allow_multiple_primary=True, category="positioning",
        description="关于品牌的常见错误认知",
    ),
}


def get_registry_field(key: str) -> GtFieldDefinition | None:
    return GT_FIELD_REGISTRY.get(key)


def get_required_fields(industry: str | None = None) -> list[str]:
    fields = []
    for key, defn in GT_FIELD_REGISTRY.items():
        if not defn.required:
            continue
        if defn.applicable_industries and industry and industry not in defn.applicable_industries:
            continue
        fields.append(key)
    return fields


def validate_field_name(field_name: str) -> tuple[bool, str]:
    """Check if a field name is registered. Returns (valid, reason)."""
    if field_name in GT_FIELD_REGISTRY:
        return True, ""
    # Fuzzy match against aliases
    for key, defn in GT_FIELD_REGISTRY.items():
        if field_name in defn.aliases:
            return True, f"matched alias of '{key}'"
    return False, f"unknown field '{field_name}'"
