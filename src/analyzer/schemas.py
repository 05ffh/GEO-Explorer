"""Pydantic models for Phase A JSONB structures. All writes validate through these."""

from pydantic import BaseModel
from typing import Literal


class BlockingReason(BaseModel):
    code: str
    message: str
    severity: Literal["block", "warning"]


class AiHallucinationSummary(BaseModel):
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    confirmed_claim_count: int = 0
    p0_explanation: str = ""
    excluded_explanation: str = ""


class TemplateIssueSummary(BaseModel):
    invalid_template_count: int = 0
    unresolved_variable_count: int = 0
    affected_query_count: int = 0


class GtInsufficientSummary(BaseModel):
    unsupported_claim_count: int = 0
    missing_gt_fields: list[str] = []


class NotAboutBrandSummary(BaseModel):
    generic_statement_count: int = 0
    irrelevant_response_count: int = 0


class ReportQualitySummaryModel(BaseModel):
    schema_version: Literal["report_quality_summary_v1"]
    generated_at: str
    ai_hallucination: AiHallucinationSummary
    template_issue: TemplateIssueSummary
    gt_insufficient: GtInsufficientSummary
    not_about_brand: NotAboutBrandSummary
    report_publishable: bool
    blocking_reasons: list[BlockingReason] = []


class TemplateHealthReportModel(BaseModel):
    schema_version: Literal["template_health_v1"]
    generated_at: str
    total_templates: int
    valid_templates: int
    invalid_templates: int
    skipped_templates: int
    critical_invalid: int
    important_invalid: int
    optional_skipped: int
    blocking_invalid_templates: int
    non_blocking_skipped_templates: int
    invalid_ratio: float
    missing_variables: dict
    can_collect: bool
    can_publish_report: bool


class CoverageReportModel(BaseModel):
    raw_coverage: float
    valid_answer_coverage: float
    metric_eligible_coverage: float
    platform_coverage: dict


class GoNoGoItem(BaseModel):
    name: str
    status: Literal["go", "no_go"]
    evidence: str
    blocking: bool


class GoNoGoResultModel(BaseModel):
    schema_version: Literal["go_no_go_v1"]
    run_target: str
    checked_at: str
    overall_decision: Literal["go", "no_go"]
    items: list[GoNoGoItem]
    approved_by: str
