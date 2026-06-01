import pytest
from src.analyzer.quality import build_report_quality_summary, compute_report_publishable


async def test_build_quality_summary_with_empty_hallucinations(db_session):
    import uuid
    summary = await build_report_quality_summary(
        collection_run_id=str(uuid.uuid4()),
        template_health={"schema_version": "template_health_v1", "invalid_templates": 0},
        coverage_report={"metric_eligible_coverage": 0.85},
        db=db_session,
    )
    assert summary["schema_version"] == "report_quality_summary_v1"
    assert "generated_at" in summary
    assert summary["ai_hallucination"]["p0_count"] == 0
    assert summary["template_issue"]["invalid_template_count"] == 0


async def test_build_quality_summary_with_missing_template_health(db_session):
    summary = await build_report_quality_summary(
        collection_run_id="nonexistent",
        template_health=None,
        coverage_report=None,
        db=db_session,
    )
    assert summary["template_issue"]["invalid_template_count"] == 0
    assert summary["schema_version"] == "report_quality_summary_v1"


def test_compute_publishable_blocks_when_critical_invalid():
    th = {"critical_invalid": 1, "invalid_ratio": 0.05, "can_collect": True, "can_publish_report": False}
    coverage = {"metric_eligible_coverage": 0.8}
    qs = {"schema_version": "report_quality_summary_v1", "ai_hallucination": {"p0_count": 0},
          "template_issue": {"invalid_template_count": 1}, "gt_insufficient": {"unsupported_claim_count": 0},
          "not_about_brand": {"generic_statement_count": 0}}
    metrics = {"information_accuracy": {"denominator": 10}}
    pub, reasons = compute_report_publishable(th, coverage, qs, metrics)
    assert pub is False
    assert any("CRITICAL_TEMPLATE_INVALID" in r["code"] for r in reasons)


def test_compute_publishable_blocks_when_coverage_missing():
    pub, reasons = compute_report_publishable(
        {"critical_invalid": 0, "invalid_ratio": 0.05, "can_collect": True, "can_publish_report": True},
        None,
        {"schema_version": "report_quality_summary_v1", "ai_hallucination": {"p0_count": 0},
         "template_issue": {"invalid_template_count": 0}, "gt_insufficient": {"unsupported_claim_count": 0},
         "not_about_brand": {"generic_statement_count": 0}},
        {},
    )
    assert pub is False
    assert any("COVERAGE_DATA_MISSING" in r["code"] for r in reasons)


def test_compute_publishable_true_with_warnings_only():
    th = {"critical_invalid": 0, "invalid_ratio": 0.05, "optional_skipped": 1,
          "can_collect": True, "can_publish_report": True}
    coverage = {"metric_eligible_coverage": 0.8, "platform_coverage": {"kimi": 0.45}}
    qs = {"schema_version": "report_quality_summary_v1", "ai_hallucination": {"p0_count": 2},
          "template_issue": {"invalid_template_count": 0}, "gt_insufficient": {"unsupported_claim_count": 0},
          "not_about_brand": {"generic_statement_count": 0}}
    metrics = {"information_accuracy": {"denominator": 10}}
    pub, reasons = compute_report_publishable(th, coverage, qs, metrics)
    assert pub is True
    warnings = [r for r in reasons if r["severity"] == "warning"]
    assert len(warnings) > 0
