"""P1-9: Industry config resolution — deep merge, validation, and version snapshot."""
import uuid
import logging
from copy import deepcopy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.industry_profiles import IndustryCode, INDUSTRY_PROFILES
from src.schemas.industry_config import (
    IndustryConfig, KpiWeightsConfig, HallucinationThresholdsConfig,
    TemplateStrategyConfig, CompetitorRulesConfig,
)
from src.models.brand import Brand
from src.models.industry_template import IndustryTemplate
from src.models.collection_run import CollectionRun

logger = logging.getLogger(__name__)

# Default industry configs
DEFAULT_CONFIGS: dict[IndustryCode, IndustryConfig] = {
    IndustryCode.DEFAULT: IndustryConfig(
        kpi_weights=KpiWeightsConfig(
            accuracy=0.30, completeness=0.15, citation=0.10, sov=0.25, first_rec=0.20,
        ),
        hallucination_thresholds=HallucinationThresholdsConfig(
            high_risk_fields=["official_name", "founding_year"],
        ),
        template_strategy=TemplateStrategyConfig(
            min_questions_per_qtype=2, max_questions_per_qtype=8,
            required_qtypes=["brand_definition", "brand_trust"],
        ),
    ),
    IndustryCode.RESTAURANT_CHAIN: IndustryConfig(
        kpi_weights=KpiWeightsConfig(
            accuracy=0.15, completeness=0.15, citation=0.40, sov=0.15, first_rec=0.15,
        ),
        hallucination_thresholds=HallucinationThresholdsConfig(
            high_risk_fields=["official_name", "core_products", "store_format"],
        ),
        template_strategy=TemplateStrategyConfig(
            min_questions_per_qtype=3, max_questions_per_qtype=8,
            required_qtypes=["brand_definition", "brand_trust"],
            recommended_qtypes=["brand_comparison", "scenario_solution"],
        ),
    ),
    IndustryCode.SAAS: IndustryConfig(
        kpi_weights=KpiWeightsConfig(
            accuracy=0.20, completeness=0.20, citation=0.10, sov=0.35, first_rec=0.15,
        ),
        hallucination_thresholds=HallucinationThresholdsConfig(
            high_risk_fields=["official_name", "core_features", "pricing_model"],
        ),
        template_strategy=TemplateStrategyConfig(
            min_questions_per_qtype=3, max_questions_per_qtype=8,
            required_qtypes=["brand_definition", "brand_attribute"],
            recommended_qtypes=["brand_comparison", "category_recommendation"],
        ),
    ),
    IndustryCode.TRAVEL_HOTEL: IndustryConfig(
        kpi_weights=KpiWeightsConfig(
            accuracy=0.20, completeness=0.10, citation=0.15, sov=0.20, first_rec=0.35,
        ),
        hallucination_thresholds=HallucinationThresholdsConfig(
            high_risk_fields=["official_name", "headquarters", "core_scenarios"],
        ),
        template_strategy=TemplateStrategyConfig(
            min_questions_per_qtype=3, max_questions_per_qtype=8,
            required_qtypes=["brand_definition", "scenario_solution"],
            recommended_qtypes=["user_recommendation", "brand_trust"],
        ),
    ),
    IndustryCode.FINANCIAL_SERVICES: IndustryConfig(
        kpi_weights=KpiWeightsConfig(
            accuracy=0.35, completeness=0.25, citation=0.20, sov=0.10, first_rec=0.10,
        ),
        hallucination_thresholds=HallucinationThresholdsConfig(
            high_risk_fields=["official_name", "license_or_regulatory_status", "founding_year", "risk_disclosures"],
        ),
        template_strategy=TemplateStrategyConfig(
            min_questions_per_qtype=4, max_questions_per_qtype=8,
            required_qtypes=["brand_definition", "brand_trust", "brand_attribute"],
        ),
    ),
}


def get_industry_default(code: IndustryCode) -> IndustryConfig:
    """Get the global default config for an industry code."""
    return DEFAULT_CONFIGS.get(code, DEFAULT_CONFIGS[IndustryCode.DEFAULT])


def get_industry_profile(code: IndustryCode) -> dict:
    """Get the display profile for an industry code."""
    return INDUSTRY_PROFILES.get(code, INDUSTRY_PROFILES[IndustryCode.DEFAULT])


async def resolve_industry_config(
    brand: Brand,
    db: AsyncSession | None = None,
) -> dict:
    """Resolve the effective industry config for a brand.

    Priority: brand override > industry template > global default.

    Returns:
        dict with keys: merged_config (IndustryConfig dict),
            industry_code, source_layers, brand_override_applied, warnings
    """
    warnings = []
    source_layers = ["global_default"]

    # Start with global default
    merged = deepcopy(get_industry_default(IndustryCode.DEFAULT)).model_dump()

    # Determine industry code
    industry_code = IndustryCode.DEFAULT
    industry_template_id = getattr(brand, "industry_template_id", None)

    if industry_template_id and db:
        tmpl = (await db.execute(
            select(IndustryTemplate).where(IndustryTemplate.id == industry_template_id)
        )).scalar_one_or_none()
        if tmpl and tmpl.slug:
            try:
                industry_code = IndustryCode(tmpl.slug)
            except ValueError:
                warnings.append(f"Unknown industry slug: {tmpl.slug}, using default")
                industry_code = IndustryCode.DEFAULT

            # Merge industry template config
            if tmpl.kpi_weights:
                merged["kpi_weights"] = _deep_merge_dict(
                    merged["kpi_weights"], dict(tmpl.kpi_weights), "kpi_weights"
                )
            if tmpl.hallucination_thresholds:
                merged["hallucination_thresholds"] = _deep_merge_dict(
                    merged["hallucination_thresholds"], dict(tmpl.hallucination_thresholds), "hallucination"
                )
            if tmpl.template_strategy:
                merged["template_strategy"] = _deep_merge_dict(
                    merged["template_strategy"], dict(tmpl.template_strategy), "template_strategy"
                )
            if hasattr(tmpl, "competitor_rules") and tmpl.competitor_rules:
                merged["competitor_rules"] = _deep_merge_dict(
                    merged["competitor_rules"], dict(tmpl.competitor_rules), "competitor_rules"
                )

            source_layers.append(f"industry:{industry_code.value}")

    # Apply brand override
    override = getattr(brand, "industry_config_override", None)
    brand_override_applied = False
    if override and isinstance(override, dict) and override:
        brand_override_applied = True
        for section in ["kpi_weights", "hallucination_thresholds", "template_strategy", "competitor_rules"]:
            if section in override:
                if section == "kpi_weights":
                    # P0-4: complete replacement required
                    merged["kpi_weights"] = override["kpi_weights"]
                else:
                    merged[section] = _deep_merge_dict(merged.get(section, {}), override[section], section)
        source_layers.append("brand_override")

    # Validate
    try:
        validated = IndustryConfig(**merged)
        merged = validated.model_dump()
    except Exception as e:
        warnings.append(f"Config validation failed: {e}")

    return {
        "merged_config": merged,
        "industry_code": industry_code.value,
        "industry_template_id": str(industry_template_id) if industry_template_id else None,
        "source_layers": source_layers,
        "brand_override_applied": brand_override_applied,
        "warnings": warnings,
    }


def build_industry_snapshot(brand: Brand, resolved: dict) -> dict:
    """Build the snapshot to write to CollectionRun.industry_config_snapshot_json (P0-9)."""
    from datetime import datetime, timezone
    return {
        "schema_version": "industry_config_v1",
        "industry_code": resolved["industry_code"],
        "industry_template_id": resolved["industry_template_id"],
        "source_layers": resolved["source_layers"],
        "brand_override_applied": resolved["brand_override_applied"],
        "merged_config": resolved["merged_config"],
        "warnings": resolved.get("warnings", []),
        "pinned_at": datetime.now(timezone.utc).isoformat(),
    }


def _deep_merge_dict(base: dict, override: dict, section: str) -> dict:
    """Deep merge with section-specific rules (P0-5)."""
    result = deepcopy(base)
    for key, value in override.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = _deep_merge_dict(result[key], value, key)
        elif isinstance(value, list):
            result[key] = value  # arrays: replace
        elif value is None:
            result[key] = None  # null: explicit clear
        else:
            result[key] = value  # scalar: override
    return result
