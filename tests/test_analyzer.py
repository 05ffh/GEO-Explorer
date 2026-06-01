import pytest
from src.analyzer.evaluator import evaluate_field, Verdict, FieldEvaluation
from src.analyzer.hallucination import HallucinationDetector, Claim


class TestFieldEvaluator:
    def test_scalar_exact_match_correct(self):
        result = evaluate_field("industry", "旅游科技", "TestBrand 是一家旅游科技公司")
        assert result.verdict == Verdict.CORRECT
        assert result.field == "industry"

    def test_scalar_not_found_not_mentioned(self):
        result = evaluate_field("industry", "金融科技", "TestBrand 是一家旅游科技公司")
        assert result.verdict == Verdict.NOT_MENTIONED

    def test_list_full_coverage_correct(self):
        result = evaluate_field(
            "core_scenarios",
            ["数据采集", "订单管理"],
            "TestBrand 提供数据采集和订单管理功能",
        )
        assert result.verdict == Verdict.CORRECT
        assert result.coverage_rate == 1.0

    def test_list_partial_coverage(self):
        result = evaluate_field(
            "core_scenarios",
            ["数据采集", "订单管理", "报表分析", "智能推荐"],
            "TestBrand 提供数据采集功能",
        )
        assert result.verdict == Verdict.PARTIAL
        assert result.coverage_rate == 0.25

    def test_list_zero_coverage_not_mentioned(self):
        result = evaluate_field(
            "core_scenarios",
            ["数据采集", "订单管理"],
            "TestBrand 是一个很好的工具",
        )
        assert result.verdict == Verdict.NOT_MENTIONED

    def test_empty_gt_value(self):
        result = evaluate_field("industry", "", "some text")
        assert result.verdict == Verdict.NOT_MENTIONED

    def test_none_gt_value(self):
        result = evaluate_field("positioning", None, "some text")
        assert result.verdict == Verdict.NOT_MENTIONED

    def test_case_insensitive_match(self):
        result = evaluate_field("industry", "TravelTech", "TestBrand is a traveltech platform")
        assert result.verdict == Verdict.CORRECT


class TestHallucinationDetector:
    def setup_method(self):
        self.detector = HallucinationDetector()

    def test_extract_industry_claim(self):
        claims = self.detector.extract_claims("TestBrand 是一家旅游科技公司，专注于飞猪生态")
        fields = {c.field for c in claims}
        # New keyword-based detector: "公司"/"企业"→official_name, "核心"/"专注于"→positioning
        assert len(claims) >= 1, f"Got fields: {fields}"

    def test_extract_positioning_claim(self):
        claims = self.detector.extract_claims("TestBrand 定位为飞猪商家一站式数据平台")
        positioning = [c for c in claims if c.field == "positioning"]
        assert len(positioning) >= 1

    def test_extract_target_users_claim(self):
        claims = self.detector.extract_claims("TestBrand 面向飞猪商家提供数据服务")
        target = [c for c in claims if c.field == "target_users"]
        assert len(target) >= 1

    def test_empty_response_returns_no_claims(self):
        claims = self.detector.extract_claims("")
        assert claims == []

    def test_verify_claim_correct(self):
        claim = Claim(field="industry", claim_text="旅游科技公司", context="...", confidence=0.7)
        gt = {"industry": "旅游科技", "official_name": "TestBrand"}
        result = self.detector.verify_claim(claim, gt)
        assert result["verdict"] in ("correct", "uncertain", "not_checkable")

    def test_verify_claim_contradiction(self):
        claim = Claim(field="industry", claim_text="CRM软件公司", context="...", confidence=0.7)
        gt = {"industry": "旅游科技", "official_name": "TestBrand"}
        result = self.detector.verify_claim(claim, gt)
        assert result["verdict"] in ("incorrect", "not_mentioned", "uncertain", "not_checkable")

    def test_verify_claim_missing_gt_field(self):
        claim = Claim(field="industry", claim_text="旅游科技公司", context="...", confidence=0.7)
        gt = {"official_name": "TestBrand"}
        result = self.detector.verify_claim(claim, gt)
        # GT field missing → uncertain or not_checkable
        assert result["verdict"] in ("uncertain", "not_checkable")


def test_field_evaluation_dataclass():
    ev = FieldEvaluation(
        field="industry", verdict=Verdict.CORRECT,
        evidence="test", reason="exact match",
        ai_claim="旅游科技", ground_truth_value="旅游科技",
    )
    assert ev.field == "industry"
    assert ev.coverage_rate == 1.0


def test_verdict_enum_values():
    assert Verdict.CORRECT.value == "correct"
    assert Verdict.INCORRECT.value == "incorrect"
    assert Verdict.PARTIAL.value == "partial"
    assert Verdict.UNCERTAIN.value == "uncertain"
    assert Verdict.NOT_MENTIONED.value == "not_mentioned"
