"""P2-3: TemplateValidationService — validate templates before save/publish."""

import logging
from dataclasses import dataclass, field

from src.schemas.gt_field_registry import GT_FIELD_REGISTRY

logger = logging.getLogger(__name__)

# Known GT variable → field name mapping (from collector engine)
_GT_VAR_MAP = {
    "品牌": "official_name",
    "行业": "industry",
    "品类": "category",
    "竞品": "target_competitors",
    "场景": "core_scenarios",
    "目标用户": "target_users",
    "产品": "core_products",
    "功能": "core_features",
    "定位": "positioning",
    "域名": "official_domains",
}

# Question type → recommended/allowed/blocked KPIs
_QTYPE_KPI_MATRIX = {
    "brand_definition": {
        "recommended": ["information_accuracy", "completeness_rate"],
        "allowed": ["citation_rate", "brand_mention_rate"],
        "blocked": ["sov", "first_rec_rate"],
    },
    "brand_attribute": {
        "recommended": ["information_accuracy", "completeness_rate"],
        "allowed": ["citation_rate", "hallucination_rate"],
        "blocked": ["sov", "first_rec_rate"],
    },
    "brand_comparison": {
        "recommended": ["sov", "competitor_accuracy"],
        "allowed": ["information_accuracy", "first_rec_rate"],
        "blocked": ["completeness_rate"],
    },
    "brand_trust": {
        "recommended": ["citation_rate", "trust_risk_rate"],
        "allowed": ["information_accuracy", "hallucination_rate"],
        "blocked": ["sov"],
    },
    "category_recommendation": {
        "recommended": ["sov", "first_rec_rate"],
        "allowed": ["brand_mention_rate"],
        "blocked": ["information_accuracy", "completeness_rate"],
    },
    "scenario_solution": {
        "recommended": ["scenario_coverage"],
        "allowed": ["sov", "brand_mention_rate"],
        "blocked": ["information_accuracy", "completeness_rate"],
    },
    "user_recommendation": {
        "recommended": ["sov", "brand_mention_rate"],
        "allowed": ["first_rec_rate"],
        "blocked": ["information_accuracy", "completeness_rate"],
    },
    "generic_advice": {
        "recommended": [],
        "allowed": ["brand_mention_rate"],
        "blocked": ["information_accuracy", "completeness_rate", "sov", "citation_rate"],
    },
}

VALID_QUESTION_TYPES = {
    "brand_definition", "brand_attribute", "brand_comparison", "brand_trust",
    "category_recommendation", "scenario_solution", "user_recommendation", "generic_advice",
}
VALID_TEMPLATE_LEVELS = {"critical", "important", "optional"}
VALID_QUESTION_SCOPES = {"brand_directed", "brand_adjacent", "category_directed", "scenario_directed", "generic"}
VALID_BRAND_DIRECTED = {0, 0.25, 0.5, 0.75, 1.0}
MAX_TEMPLATE_TEXT_LENGTH = 2000


@dataclass
class ValidationIssue:
    code: str
    field: str
    message: str
    severity: str = "error"  # error / warning


@dataclass
class ValidationReport:
    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    extracted_variables: list[str] = field(default_factory=list)
    required_gt_fields: list[str] = field(default_factory=list)

    @property
    def publishable(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "publishable": self.publishable,
            "errors": [{"code": e.code, "field": e.field, "message": e.message} for e in self.errors],
            "warnings": [{"code": w.code, "field": w.field, "message": w.message} for w in self.warnings],
            "extracted_variables": self.extracted_variables,
            "required_gt_fields": self.required_gt_fields,
        }


@dataclass
class RenderPreview:
    rendered_question: str
    used_variables: dict[str, str]
    missing_variables: list[str]
    fallback_used: bool
    warnings: list[str] = field(default_factory=list)
    valid: bool = True


class TemplateValidationService:
    """Validate template correctness before save/publish."""

    def validate(
        self,
        template_text: str,
        question_type: str,
        template_level: str = "important",
        question_scope: str | None = None,
        brand_directed: float = 1.0,
        applicable_industries: list[str] | None = None,
        excluded_industries: list[str] | None = None,
        metric_eligibility: list[str] | None = None,
    ) -> ValidationReport:
        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []

        # ── Field validations ─────────────────────────────────────────
        if not template_text or not template_text.strip():
            errors.append(ValidationIssue("EMPTY_TEMPLATE", "template_text", "模板文本不能为空"))
            return ValidationReport(valid=False, errors=errors, warnings=warnings)

        if len(template_text) > MAX_TEMPLATE_TEXT_LENGTH:
            errors.append(ValidationIssue(
                "TEMPLATE_TOO_LONG", "template_text",
                f"模板文本超过{MAX_TEMPLATE_TEXT_LENGTH}字符限制"))

        if question_type not in VALID_QUESTION_TYPES:
            errors.append(ValidationIssue(
                "INVALID_QTYPE", "question_type", f"无效的 question_type: {question_type}"))

        if template_level not in VALID_TEMPLATE_LEVELS:
            errors.append(ValidationIssue(
                "INVALID_LEVEL", "template_level", f"无效的 template_level: {template_level}"))

        if question_scope and question_scope not in VALID_QUESTION_SCOPES:
            warnings.append(ValidationIssue(
                "INVALID_SCOPE", "question_scope", f"无效的 question_scope: {question_scope}"))

        if brand_directed not in VALID_BRAND_DIRECTED:
            errors.append(ValidationIssue(
                "INVALID_BRAND_DIRECTED", "brand_directed",
                f"brand_directed 必须为 0/0.25/0.5/0.75/1.0, 当前: {brand_directed}"))

        # ── Variable checks ──────────────────────────────────────────
        import re as _re
        var_pattern = _re.compile(r"\{([^{}]+)\}")
        variables = var_pattern.findall(template_text)
        unknown_vars = [v for v in variables if v not in _GT_VAR_MAP]
        for uv in unknown_vars:
            errors.append(ValidationIssue(
                "UNKNOWN_VARIABLE", "template_text",
                f"变量 {{{uv}}} 未绑定到 GT Field Registry 或已知变量映射"))

        known_vars = [v for v in variables if v in _GT_VAR_MAP]
        required_gt = [_GT_VAR_MAP[v] for v in known_vars]

        # ── Critical template must have brand variable ────────────────
        if template_level == "critical" and "品牌" not in variables:
            warnings.append(ValidationIssue(
                "CRITICAL_NO_BRAND_VAR", "template_text",
                "critical 级别模板建议包含 {品牌} 变量"))

        # ── question_scope vs brand_directed consistency ──────────────
        if question_scope == "brand_directed" and brand_directed < 0.5:
            warnings.append(ValidationIssue(
                "SCOPE_DIRECTED_MISMATCH", "brand_directed",
                "question_scope=brand_directed 但 brand_directed < 0.5，建议 ≥0.5"))

        # ── KPI binding checks ───────────────────────────────────────
        if metric_eligibility:
            qtype_rules = _QTYPE_KPI_MATRIX.get(question_type, {})
            blocked = set(qtype_rules.get("blocked", []))
            for kpi in metric_eligibility:
                if kpi in blocked:
                    errors.append(ValidationIssue(
                        "KPI_QTYPE_MISMATCH", "metric_eligibility",
                        f"{question_type} 模板不能绑定 {kpi} (允许: {qtype_rules.get('allowed', [])})"))
                elif kpi not in qtype_rules.get("recommended", []) and kpi not in qtype_rules.get("allowed", []):
                    warnings.append(ValidationIssue(
                        "KPI_NOT_RECOMMENDED", "metric_eligibility",
                        f"{question_type} 不建议绑定 {kpi} (推荐: {qtype_rules.get('recommended', [])})"))

        # ── Industry conflict check ──────────────────────────────────
        apps = set(applicable_industries or [])
        excls = set(excluded_industries or [])
        if apps and excls:
            overlap = apps & excls
            if overlap:
                errors.append(ValidationIssue(
                    "INDUSTRY_CONFLICT", "applicable_industries",
                    f"适用行业与排除行业存在交集: {overlap}"))

        valid = len(errors) == 0
        return ValidationReport(
            valid=valid,
            errors=errors,
            warnings=warnings,
            extracted_variables=variables,
            required_gt_fields=list(set(required_gt)),
        )

    def render_preview(
        self,
        template_text: str,
        brand_name: str = "示例品牌",
        industry: str = "示例行业",
        sample_values: dict | None = None,
    ) -> RenderPreview:
        """Render template with sample values and return preview."""
        values = dict(sample_values or {})
        used: dict[str, str] = {}
        missing: list[str] = []
        warnings: list[str] = []
        fallback = False

        # Default value map
        defaults = {
            "品牌": brand_name,
            "行业": industry,
            "品类": values.get("品类", "示例品类"),
            "竞品": values.get("竞品", "竞品A"),
            "场景": values.get("场景", "日常场景"),
            "目标用户": values.get("目标用户", "目标用户群"),
            "产品": values.get("产品", "核心产品"),
            "功能": values.get("功能", "主要功能"),
            "定位": values.get("定位", "品牌定位"),
            "域名": values.get("域名", "example.com"),
        }

        result = template_text
        import re as _re
        var_pattern = _re.compile(r"\{([^{}]+)\}")

        for var in var_pattern.findall(template_text):
            if var in values:
                used[var] = values[var]
                result = result.replace(f"{{{var}}}", values[var])
            elif var in defaults:
                used[var] = defaults[var]
                result = result.replace(f"{{{var}}}", defaults[var])
                if var not in values:
                    fallback = True
                    warnings.append(f"变量 {{{var}}} 使用了默认值，非实际 GT 数据")
            else:
                missing.append(var)
                warnings.append(f"变量 {{{var}}} 无法解析，将保留原文")

        # Check for unresolved braces
        remaining = var_pattern.findall(result)
        valid = len(remaining) == 0

        return RenderPreview(
            rendered_question=result,
            used_variables=used,
            missing_variables=missing,
            fallback_used=fallback,
            warnings=warnings,
            valid=valid,
        )


validation_service = TemplateValidationService()
