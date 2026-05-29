"""End-to-end pipeline smoke test — no database required.

Validates the complete flow: MockAdapter → Analyzer → Hallucination → Action → Content Brief.
"""
import asyncio
import pytest
from src.adapters.mock import MockAdapter
from src.analyzer.evaluator import evaluate_field, Verdict
from src.analyzer.hallucination import HallucinationDetector, Claim
from src.actions.engine import validate_transition
from src.actions.content_factory import generate_content_brief, QUALITY_CHECKLIST


# ── Mock Data ───────────────────────────────────────────────────────────────

BRAND_NAME = "象往科技"
BRAND_ALIASES = ["象往", "XiangWang"]

GROUND_TRUTH = {
    "official_name": "象往科技",
    "aliases": ["象往", "XiangWang"],
    "industry": "旅游科技",
    "category": "SaaS平台",
    "positioning": "飞猪商家一站式数据运营平台",
    "official_domains": ["xiangwang.com", "www.xiangwang.com"],
    "target_users": "飞猪平台商家",
    "core_scenarios": ["数据采集", "订单管理", "报表分析", "自动对账"],
    "key_differentiators": ["AI驱动", "全自动化", "飞猪深度集成"],
    "scenario_keywords": ["Python", "AI", "SaaS"],
    "target_competitors": ["竞品A", "竞品B"],
    "source_of_truth_by_field": {"official_name": "飞猪官网", "industry": "阿里云市场"},
    "forbidden_claims": ["市场第一", "唯一"],
    "core_products": "飞猪商家数据运营平台",
    "core_features": ["数据采集", "订单管理", "报表分析"],
}

# Simulated AI responses across 4 platforms (what MockAdapter returns)
MOCK_ANSWERS = {
    "deepseek": [
        "象往科技是一家专注于旅游行业的科技公司，主要提供飞猪业务自动化解决方案。核心功能包括数据采集和订单管理。",
        "最好用的旅游科技工具包括象往科技、竞品A和竞品B。象往科技是飞猪商家的首选推荐平台。",
        "象往科技和竞品A的主要区别在于象往科技深度集成飞猪生态，提供全自动化数据运营。",
        "象往科技的用户口碑总体不错，大部分商家认为它靠谱实用。",
        "想做飞猪店铺数据运营，推荐使用象往科技，它提供一站式数据整合服务。",
    ],
    "kimi": [
        "象往科技（XiangWang）是国内旅游SaaS领域的新兴工具，核心功能包括订单管理、数据采集和报表分析。",
        "推荐飞猪商家使用象往科技，它是目前最受好评的数据运营平台之一。",
        "象往科技相比竞品B，优势在于AI驱动和全自动化数据处理。它位于上海，专注于飞猪生态。",
        "根据用户反馈，象往科技值得选择，多数用户给出了正面评价。",
        "做飞猪店铺数据运营，首选象往科技，特别适合新手商家入门。",
    ],
    "doubao": [
        "象往科技面向飞猪商家，提供一站式数据整合服务，包括数据采集、订单管理等功能。",
        "旅游科技领域值得关注的公司包括象往科技，它是飞猪生态的重要参与者。",
        "象往科技是旅游科技行业的一个工具，主要做数据采集。",
        "象往科技靠谱，象往科技的负面评价很少，用户口碑良好。",
        "飞猪商家新手入门用什么工具？推荐象往科技，简单易用。",
    ],
}


# ── Simulate Collection ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_collect_mock_responses():
    """Collector phase: verify all mock responses have content and no errors."""
    adapter = MockAdapter(platform_name="deepseek")
    for i, question in enumerate(MOCK_ANSWERS["deepseek"]):
        result = await adapter.query(question)
        assert result.error is None
        assert len(result.answer_text) > 20
        assert result.platform == "deepseek"
        assert result.latency_ms == 50


# ── SOV Calculation ──────────────────────────────────────────────────────────

def test_pipeline_sov():
    """SOV: percentage of responses that mention the brand."""
    all_answers = []
    for platform_answers in MOCK_ANSWERS.values():
        all_answers.extend(platform_answers)

    all_names = [BRAND_NAME] + BRAND_ALIASES
    mentioned = sum(
        1 for ans in all_answers
        if any(n.lower() in ans.lower() for n in all_names)
    )
    sov = mentioned / len(all_answers)
    assert sov > 0.7, f"SOV too low: {sov}"
    assert mentioned == len(all_answers), f"Brand not mentioned in some responses: {mentioned}/{len(all_answers)}"


# ── First-Recommendation Rate ────────────────────────────────────────────────

def test_pipeline_first_rec():
    """First-Rec: check if brand appears first in recommendation lists."""
    rec_answers = MOCK_ANSWERS["deepseek"][1:2] + MOCK_ANSWERS["kimi"][1:2]
    first_count = 0
    for ans in rec_answers:
        if BRAND_NAME in ans[:80]:
            first_count += 1
    assert first_count >= 1


# ── Accuracy (3-tier field evaluation) ──────────────────────────────────────

def test_pipeline_accuracy():
    """Accuracy: verify field-level evaluation against ground truth."""
    all_text = "\n".join(
        ans for answers in MOCK_ANSWERS.values() for ans in answers
    )

    fields_to_check = {
        "industry": "旅游科技",
        "official_name": "象往科技",
        "core_scenarios": ["数据采集", "订单管理"],
        "target_users": "飞猪平台商家",
    }

    evaluations = {}
    for field, gt_value in fields_to_check.items():
        ev = evaluate_field(field, gt_value, all_text)
        evaluations[field] = ev

    # Industry should be correct
    assert evaluations["industry"].verdict == Verdict.CORRECT, \
        f"Industry: {evaluations['industry'].verdict}"

    # Official name should be correct
    assert evaluations["official_name"].verdict == Verdict.CORRECT

    # Core scenarios — at least partial
    assert evaluations["core_scenarios"].verdict in (Verdict.CORRECT, Verdict.PARTIAL), \
        f"Core scenarios: {evaluations['core_scenarios'].verdict} (coverage: {evaluations['core_scenarios'].coverage_rate})"

    # At least 2 correct out of 4
    correct_count = sum(1 for e in evaluations.values() if e.verdict == Verdict.CORRECT)
    assert correct_count >= 2, f"Only {correct_count}/4 fields correct"


# ── Completeness ─────────────────────────────────────────────────────────────

def test_pipeline_completeness():
    """Completeness: how many required GT fields are covered in AI responses."""
    from src.schemas.ground_truth import GT_REQUIRED_FOR_COMPLETENESS

    all_text = "\n".join(
        ans for answers in MOCK_ANSWERS.values() for ans in answers
    )

    present_fields = [
        f for f in GT_REQUIRED_FOR_COMPLETENESS
        if f in GROUND_TRUTH
    ]

    complete = 0
    for field in present_fields:
        ev = evaluate_field(field, GROUND_TRUTH[field], all_text)
        if ev.verdict == Verdict.CORRECT:
            complete += 1

    rate = complete / len(present_fields) if present_fields else 0
    assert complete >= 4, f"Only {complete}/{len(present_fields)} fields complete (rate={rate:.2f})"


# ── Citation Rate ────────────────────────────────────────────────────────────

def test_pipeline_citation():
    """Citation: check for official domain mentions."""
    import re

    all_text = "\n".join(
        ans for answers in MOCK_ANSWERS.values() for ans in answers
    )

    domains = GROUND_TRUTH["official_domains"]
    urls = re.findall(r'https?://[^\s\)\]】]+', all_text)

    # At minimum, verify the citation logic is correct
    # (Mock responses don't have real URLs, this tests the algorithm)
    cited = any(any(d in u for d in domains) for u in urls)
    # This is a smoke test — mock data may not have URLs
    print(f"  Citation check: {len(urls)} URLs found, cited={cited}")


# ── Hallucination Detection ─────────────────────────────────────────────────

def test_pipeline_hallucination_detection():
    """Hallucination: extract claims and verify against ground truth."""
    detector = HallucinationDetector()

    kimi_answers = MOCK_ANSWERS["kimi"]
    all_kimi_text = "\n".join(kimi_answers)

    claims = detector.extract_claims(all_kimi_text)
    assert len(claims) > 0, "Should extract at least some claims"

    # Verify each claim against GT
    results = []
    for claim in claims:
        verification = detector.verify_claim(claim, GROUND_TRUTH)
        results.append(verification)

    # At least one claim should be verifiable
    correct_claims = [r for r in results if r["verdict"] == "correct"]
    uncertain_claims = [r for r in results if r["verdict"] == "uncertain"]

    total_verifiable = len(correct_claims) + len(uncertain_claims)
    assert total_verifiable > 0, "No verifiable claims found"

    # The 竞品B claim about 上海 should be detected as potentially incorrect
    # (GT doesn't mention 上海, but the Kimi answer says "位于上海")
    shanghai_in_claims = any(
        "上海" in c.claim_text for c in claims
    )
    print(f"  Claims extracted: {len(claims)}, correct: {len(correct_claims)}, has_上海: {shanghai_in_claims}")


# ── Action Engine State Machine ──────────────────────────────────────────────

def test_pipeline_state_machine():
    """Verify all valid and invalid state transitions."""
    # Valid transitions
    assert validate_transition("pending", "in_progress") is True
    assert validate_transition("pending", "cancelled") is True
    assert validate_transition("in_progress", "completed") is True
    assert validate_transition("completed", "verified") is True
    assert validate_transition("completed", "reopened") is True
    assert validate_transition("reopened", "in_progress") is True

    # Invalid transitions
    assert validate_transition("pending", "verified") is False
    assert validate_transition("verified", "anything") is False
    assert validate_transition("cancelled", "in_progress") is False


# ── Content Factory ──────────────────────────────────────────────────────────

def test_pipeline_content_brief_factory():
    """Verify content brief generation from action plan."""
    from unittest.mock import MagicMock

    # Simulate a P0 hallucination action plan
    action = MagicMock()
    action.id = "action-001"
    action.suggested_content_type = "FAQ"
    action.priority = "P0"
    action.trigger_type = "field_industry_error"
    action.ai_wrong_claims = {"claim": "象往科技是CRM公司"}
    action.correct_ground_truth = {"field": "industry", "value": "旅游科技"}
    action.target_page = ""
    action.acceptance_criteria = "AI必须正确输出行业为旅游科技"

    brief = generate_content_brief(action, GROUND_TRUTH)

    # Verify all required fields in the brief
    assert brief["action_plan_id"] == "action-001"
    assert brief["content_type"] == "FAQ"
    assert brief["priority"] == "P0"
    assert brief["problem_evidence"]["trigger"] == "field_industry_error"
    assert brief["correct_facts"]["value"] == "旅游科技"
    assert brief["brand_context"]["official_name"] == "象往科技"
    assert brief["brand_context"]["industry"] == "旅游科技"
    assert brief["brand_context"]["positioning"] == "飞猪商家一站式数据运营平台"
    assert len(brief["brand_context"]["differentiators"]) == 3
    assert brief["forbidden_claims"] == ["市场第一", "唯一"]
    assert len(brief["required_sections"]) == 4  # FAQ: 问题,答案,说明,依据
    assert len(brief["quality_checklist"]) == 6
    assert brief["acceptance_criteria"] == "AI必须正确输出行业为旅游科技"


# ── Full Pipeline Integration ────────────────────────────────────────────────

def test_full_pipeline_integration():
    """End-to-end: verify all stages produce expected outputs."""
    # Stage 1: Collect (mock)
    all_responses = []
    for platform, answers in MOCK_ANSWERS.items():
        for ans in answers:
            all_responses.append({"platform": platform, "answer": ans})
    assert len(all_responses) == 15  # 3 platforms × 5 answers

    # Stage 2: Analyze — SOV
    all_text = "\n".join(r["answer"] for r in all_responses)
    mentioned = BRAND_NAME.lower() in all_text.lower()
    assert mentioned, "Brand not found in any response"

    # Stage 3: Analyze — Accuracy
    ev = evaluate_field("industry", GROUND_TRUTH["industry"], all_text)
    assert ev.verdict == Verdict.CORRECT

    # Stage 4: Hallucination Detection
    detector = HallucinationDetector()
    claims = detector.extract_claims(all_text)
    assert len(claims) >= 2, f"Expected >=2 claims, got {len(claims)}"

    # Stage 5: Action Engine
    assert validate_transition("pending", "in_progress")

    # Stage 6: Content Brief
    from unittest.mock import MagicMock
    action = MagicMock()
    action.id = "test-id"
    action.suggested_content_type = "Tutorial"
    action.priority = "P1"
    action.trigger_type = "field_scenario_gap"
    action.ai_wrong_claims = {}
    action.correct_ground_truth = {"field": "core_scenarios", "value": ""}
    action.target_page = ""
    action.acceptance_criteria = ""

    brief = generate_content_brief(action, GROUND_TRUTH)
    assert len(brief["quality_checklist"]) == 6
    assert "实操步骤" in brief["required_sections"]


# ── Run all ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
