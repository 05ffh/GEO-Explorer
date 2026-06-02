"""P1-10: Sample sufficiency schemas — config, result, action."""
from pydantic import BaseModel, Field, model_validator


class SampleSufficiencyConfig(BaseModel):
    schema_version: str = "sample_sufficiency_v1"
    min_queries_per_platform: int = Field(default=3, ge=0)
    min_queries_per_qtype: int = Field(default=2, ge=0)
    min_queries_per_kpi_default: int = Field(default=5, ge=0)
    min_queries_by_kpi: dict[str, int] = Field(default_factory=dict)
    min_total_queries: int = Field(default=10, ge=0)
    min_platforms: int = Field(default=2, ge=1)
    require_all_platforms: bool = False
    critical_platforms: list[str] = Field(default_factory=list)
    critical_qtypes: list[str] = Field(default_factory=list)
    critical_kpis: list[str] = Field(default_factory=list)
    min_queries_by_platform: dict[str, int] = Field(default_factory=dict)
    min_queries_by_qtype: dict[str, int] = Field(default_factory=dict)
    optional_platforms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_config(self) -> "SampleSufficiencyConfig":
        for k, v in self.min_queries_by_kpi.items():
            if v < 0:
                raise ValueError(f"min_queries_by_kpi.{k} must be >= 0")
        for k, v in self.min_queries_by_platform.items():
            if v < 0:
                raise ValueError(f"min_queries_by_platform.{k} must be >= 0")
        return self


class SampleSufficiencyResult(BaseModel):
    schema_version: str = "sample_sufficiency_result_v1"
    generated_at: str = ""
    data_status: str = ""  # ok | no_data | insufficient | partial
    config_snapshot: dict = Field(default_factory=dict)
    config_source: dict = Field(default_factory=dict)

    total_raw_queries: int = 0
    total_successful_queries: int = 0
    total_valid_queries: int = 0
    total_metric_eligible_queries: int = 0

    total_platforms: int = 0
    enabled_platforms: int = 0
    successful_platforms: int = 0

    platform_breakdown: dict = Field(default_factory=dict)
    qtype_breakdown: dict = Field(default_factory=dict)
    kpi_breakdown: dict = Field(default_factory=dict)

    blocking_dimensions: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    recommended_actions: list[dict] = Field(default_factory=list)
    recommendation_summary: str = ""


class SampleSufficiencyAction(BaseModel):
    action_type: str  # retry_platform | add_templates | add_platform | collect_more | fix_auth | wait_rate_limit | review_gt
    target: str | None = None
    reason: str = ""
    priority: str = "medium"  # high | medium | low


BLOCKING_CODES = {
    "NO_DATA": ("block", "无成功 QueryResult"),
    "SAMPLE_TOTAL_TOO_LOW": ("block", "有效样本总数不足"),
    "SAMPLE_PLATFORM_TOO_LOW": ("block", "成功平台数不足"),
    "SAMPLE_QTYPE_TOO_LOW": ("block", "关键问题类型样本不足"),
    "SAMPLE_KPI_TOO_LOW": ("block", "关键 KPI 分母不足"),
    "SAMPLE_CRITICAL_PLATFORM_MISSING": ("block", "关键平台无数据"),
    "SAMPLE_REQUIRE_ALL_PLATFORMS_NOT_MET": ("block", "要求全平台但部分平台无数据"),
    "SAMPLE_PARTIAL_PLATFORM": ("warning", "非关键平台样本不足"),
    "SAMPLE_NON_CRITICAL_QTYPE_LOW": ("warning", "非关键问题类型样本不足"),
    "SAMPLE_LEGACY_TEMPLATE_VERSION": ("warning", "使用旧模板版本"),
    "SAMPLE_PLATFORM_RATE_LIMITED": ("warning", "平台触发限流"),
}
