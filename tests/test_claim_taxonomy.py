"""P2-1: ClaimNatureClassifier unit tests."""
import pytest
from src.analyzer.claim_taxonomy import (
    ClaimNatureClassifier, classify_claim_nature, ClaimNatureResult,
    HIGH_RISK_PREDICATES, LOW_RISK_PREDICATES,
)
from src.analyzer.enums import ClaimNature


class TestClaimNatureClassifier:
    def setup_method(self):
        self.c = ClaimNatureClassifier()

    # ── Chinese FACT tests ─────────────────────────────────────────────

    def test_fact_numeric_date_cn(self):
        r = self.c.classify("星巴克成立于1971年")
        assert r.claim_nature == ClaimNature.FACT
        assert r.confidence >= 0.55
        assert "成立于" in r.matched_signals or any("numeric" in s for s in r.signal_categories)

    def test_fact_store_count_cn(self):
        r = self.c.classify("拥有38,000家门店")
        assert r.claim_nature == ClaimNature.FACT
        assert r.confidence >= 0.55

    def test_fact_revenue_cn(self):
        r = self.c.classify("2025年营收达到$36B")
        assert r.claim_nature == ClaimNature.FACT

    def test_fact_employees_cn(self):
        r = self.c.classify("全球员工超过40万人")
        assert r.claim_nature == ClaimNature.FACT

    # ── Chinese OPINION tests ──────────────────────────────────────────

    def test_opinion_best_cn(self):
        r = self.c.classify("星巴克提供最好的咖啡体验")
        assert r.claim_nature == ClaimNature.OPINION
        assert r.confidence >= 0.65

    def test_opinion_leading_cn(self):
        r = self.c.classify("行业领先的移动应用")
        assert r.claim_nature == ClaimNature.OPINION

    def test_opinion_popular_cn(self):
        r = self.c.classify("深受好评的品牌")
        assert r.claim_nature == ClaimNature.OPINION

    def test_opinion_excellent_cn(self):
        r = self.c.classify("卓越的产品品质")
        assert r.claim_nature == ClaimNature.OPINION

    # ── Chinese SPECULATION tests ──────────────────────────────────────

    def test_speculation_may_cn(self):
        r = self.c.classify("星巴克可能扩展到更多低线城市")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert r.confidence >= 0.65

    def test_speculation_will_cn(self):
        r = self.c.classify("星巴克将推出新产品")
        assert r.claim_nature == ClaimNature.SPECULATION
        # "将" is weak signal → lower confidence
        assert r.confidence >= 0.55

    def test_speculation_expected_cn(self):
        r = self.c.classify("预计明年业绩会有显著提升")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert r.confidence >= 0.85  # strong signal

    def test_speculation_plan_cn(self):
        r = self.c.classify("正在探索新的业务模式")
        assert r.claim_nature == ClaimNature.SPECULATION

    # ── English tests ──────────────────────────────────────────────────

    def test_fact_founded_en(self):
        r = self.c.classify("Founded in 1971, has 38,000 stores worldwide")
        assert r.claim_nature == ClaimNature.FACT

    def test_opinion_best_en(self):
        r = self.c.classify("Offers the best coffee experience")
        assert r.claim_nature == ClaimNature.OPINION

    def test_speculation_could_en(self):
        r = self.c.classify("Will likely expand to smaller cities next year")
        assert r.claim_nature == ClaimNature.SPECULATION

    # ── Priority: speculation > opinion > fact ────────────────────────

    def test_mixed_speculation_overrides_opinion(self):
        r = self.c.classify("星巴克可能成为最好的品牌")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert "可能" in r.matched_signals

    def test_mixed_speculation_overrides_fact(self):
        r = self.c.classify("成立于1971年的品牌可能推出新品")
        assert r.claim_nature == ClaimNature.SPECULATION

    # ── Edge cases ────────────────────────────────────────────────────

    def test_short_text_unknown(self):
        r = self.c.classify("好的")
        assert r.claim_nature == ClaimNature.UNKNOWN
        assert r.confidence == 0.0

    def test_no_signal_unknown(self):
        r = self.c.classify("这是一个很普通的句子没有任何信号词")
        assert r.claim_nature == ClaimNature.UNKNOWN
        assert r.confidence == 0.0

    def test_classifier_returns_confidence_and_reason(self):
        r = self.c.classify("星巴克成立于1971年")
        assert r.confidence > 0
        assert len(r.reason) > 0
        assert len(r.matched_signals) > 0

    def test_classifier_returns_signal_categories(self):
        r = self.c.classify("星巴克提供最好的咖啡体验")
        assert "opinion" in r.signal_categories
        assert len(r.signal_categories) > 0

    # ── Speculation risk levels ───────────────────────────────────────

    def test_speculation_high_risk_financial(self):
        r = self.c.classify("该银行预计营收增长50%", predicate_type="financial_performance")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert r.speculation_risk_level == "high"

    def test_speculation_low_risk_reputation(self):
        r = self.c.classify("可能成为受欢迎的消费品牌", predicate_type="reputation")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert r.speculation_risk_level == "low"

    # ── Convenience function ───────────────────────────────────────────

    def test_convenience_function(self):
        r = classify_claim_nature("星巴克成立于1971年")
        assert r.claim_nature == ClaimNature.FACT


class TestClaimNatureEnum:
    def test_enum_values(self):
        assert ClaimNature.FACT.value == "fact"
        assert ClaimNature.OPINION.value == "opinion"
        assert ClaimNature.SPECULATION.value == "speculation"
        assert ClaimNature.UNKNOWN.value == "unknown"

    def test_enum_is_string(self):
        assert isinstance(ClaimNature.FACT, str)


class TestPredicateRiskLevels:
    def test_high_risk_predicates(self):
        assert "identity" in HIGH_RISK_PREDICATES
        assert "financial_performance" in HIGH_RISK_PREDICATES
        assert "safety" in HIGH_RISK_PREDICATES

    def test_low_risk_predicates(self):
        assert "reputation" in LOW_RISK_PREDICATES
        assert "scenario" in LOW_RISK_PREDICATES
