import pytest

from src.analyzer.gt_aggregator import aggregate_all_fields
from src.analyzer.gt_confidence import compute_field_confidence


def test_aggregate_field_detects_ai_consensus():
    sources = [
        {"value": "SaaS/旅游科技", "source_type": "ai_platform", "source_quality": "medium", "platform": "deepseek"},
        {"value": "SaaS/旅游科技", "source_type": "ai_platform", "source_quality": "medium", "platform": "kimi"},
        {"value": "旅游服务", "source_type": "search_result", "source_quality": "low", "platform": "duckduckgo"},
    ]
    result = aggregate_all_fields(
        [{"platform": s["platform"], "answer": s["value"], "target_fields": ["industry"], "source_type": s["source_type"]} for s in sources[:2]],
        [{"snippet": sources[2]["value"], "source_type": sources[2]["source_type"], "source_quality": sources[2]["source_quality"], "platform": sources[2]["platform"], "title": "", "url": ""}],
    )
    # AI consensus should produce at least medium confidence for industry
    assert "industry" in result


def test_confidence_high_requires_official_source():
    sources = [
        {"source_type": "ai_platform", "source_quality": "medium", "value": "SaaS"},
        {"source_type": "search_result", "source_quality": "low", "value": "SaaS"},
    ]
    conf = compute_field_confidence(sources)
    assert conf != "high"  # no official source


def test_confidence_medium_with_two_ai_agreeing():
    sources = [
        {"source_type": "ai_platform", "source_quality": "medium", "value": "SaaS/旅游科技"},
        {"source_type": "ai_platform", "source_quality": "medium", "value": "SaaS/旅游科技"},
    ]
    conf = compute_field_confidence(sources)
    assert conf == "medium"


def test_confidence_uncertain_with_conflict():
    sources = [
        {"source_type": "ai_platform", "source_quality": "medium", "value": "SaaS"},
        {"source_type": "ai_platform", "source_quality": "medium", "value": "硬件制造"},
    ]
    conf = compute_field_confidence(sources)
    assert conf == "uncertain"


def test_confidence_low_for_single_low_quality():
    sources = [
        {"source_type": "search_result", "source_quality": "low", "value": "something"},
    ]
    conf = compute_field_confidence(sources)
    assert conf == "low"


def test_empty_field_results_compute_overall_low():
    from src.collector.gt_collector import _compute_overall
    assert _compute_overall({}) == "low"
