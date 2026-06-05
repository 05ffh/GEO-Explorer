"""P1-9: IndustryConfig Pydantic schemas with validation (P0-3)."""
from pydantic import BaseModel, Field, model_validator


class KpiWeightsConfig(BaseModel):
    accuracy: float = Field(default=0.30, ge=0, le=1)
    completeness: float = Field(default=0.15, ge=0, le=1)
    citation: float = Field(default=0.10, ge=0, le=1)
    sov: float = Field(default=0.25, ge=0, le=1)
    first_rec: float = Field(default=0.20, ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "KpiWeightsConfig":
        total = self.accuracy + self.completeness + self.citation + self.sov + self.first_rec
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"KPI weights sum must be 1.0, got {total:.4f}")
        return self


class HallucinationThresholdsConfig(BaseModel):
    n_gram_similarity_min: float = Field(default=0.05, ge=0, le=1)
    n_gram_similarity_max: float = Field(default=0.35, ge=0, le=1)
    llm_fallback_enabled: bool = True
    high_risk_fields: list[str] = Field(default_factory=list)
    field_signal_overrides: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ranges(self) -> "HallucinationThresholdsConfig":
        if self.n_gram_similarity_min >= self.n_gram_similarity_max:
            raise ValueError("n_gram_similarity_min must be < n_gram_similarity_max")
        return self


class TemplateStrategyConfig(BaseModel):
    min_questions_per_qtype: int = Field(default=1, ge=1)
    max_questions_per_qtype: int = Field(default=8, ge=1)
    required_qtypes: list[str] = Field(default_factory=list)
    recommended_qtypes: list[str] = Field(default_factory=list)
    brand_directed_min: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_qtypes(self) -> "TemplateStrategyConfig":
        if self.min_questions_per_qtype > self.max_questions_per_qtype:
            raise ValueError("min_questions_per_qtype must be <= max_questions_per_qtype")
        valid = {"brand_definition", "brand_attribute", "brand_comparison", "brand_trust",
                 "category_recommendation", "scenario_solution", "user_recommendation", "generic_advice"}
        for qt in self.required_qtypes:
            if qt not in valid:
                raise ValueError(f"Unknown question_type: {qt}")
        for qt in self.recommended_qtypes:
            if qt not in valid:
                raise ValueError(f"Unknown question_type: {qt}")
        return self


class CompetitorRulesConfig(BaseModel):
    min_competitors: int = Field(default=1, ge=0)
    max_competitors: int = Field(default=5, ge=1)
    require_same_category: bool = True
    allow_cross_category: bool = False
    competitor_source_priority: list[str] = Field(default=["gt", "industry_default", "manual"])
    competitor_types: list[str] = Field(default=["direct", "substitute"])
    exclude_self_brands: bool = True


class ClaimNatureThresholdsConfig(BaseModel):
    """P2-1: Per-industry thresholds for claim nature distribution."""
    max_unknown_ratio: float = Field(default=0.20, ge=0, le=1)
    max_speculation_ratio: float = Field(default=0.30, ge=0, le=1)
    speculation_block_threshold: float = Field(default=0.50, ge=0, le=1)
    max_opinion_ratio: float = Field(default=0.60, ge=0, le=1)
    block_speculation_for_predicates: list[str] = Field(default_factory=list)
    warning_speculation_for_predicates: list[str] = Field(default_factory=list)
    regulated_industry_mode: bool = False
    industry_high_risk_terms: list[str] = Field(default_factory=list)
    high_risk_industries: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ClaimNatureThresholdsConfig":
        if self.max_speculation_ratio > self.speculation_block_threshold:
            raise ValueError(
                f"max_speculation_ratio ({self.max_speculation_ratio}) must be <= "
                f"speculation_block_threshold ({self.speculation_block_threshold})"
            )
        return self


class IndustryConfig(BaseModel):
    schema_version: str = "industry_config_v1"
    kpi_weights: KpiWeightsConfig = Field(default_factory=KpiWeightsConfig)
    hallucination_thresholds: HallucinationThresholdsConfig = Field(
        default_factory=HallucinationThresholdsConfig
    )
    template_strategy: TemplateStrategyConfig = Field(default_factory=TemplateStrategyConfig)
    competitor_rules: CompetitorRulesConfig = Field(default_factory=CompetitorRulesConfig)
    sample_sufficiency: "SampleSufficiencyConfig" = Field(default_factory=lambda: SampleSufficiencyConfig())
    claim_nature_thresholds: ClaimNatureThresholdsConfig = Field(
        default_factory=ClaimNatureThresholdsConfig
    )

# Lazy import for circular dependency
from src.schemas.sample_sufficiency import SampleSufficiencyConfig
IndustryConfig.model_rebuild()
