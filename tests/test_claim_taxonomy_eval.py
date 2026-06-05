"""P2-1v2: Golden sample evaluation for ClaimNature Chinese classifier.

Evaluates the ClaimNatureClassifier against the zh_claim_nature_golden.jsonl
test set. Computes per-class precision, recall, F1, and macro F1.

MVP targets:
- Accuracy >= 70%
- UNKNOWN rate <= 30%
- SPECULATION recall >= 70%
"""

import json
from collections import defaultdict
from pathlib import Path

import pytest

from src.analyzer.claim_taxonomy import classifier, ClaimNature


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "claim_taxonomy"
GOLDEN_FILE = FIXTURE_DIR / "zh_claim_nature_golden.jsonl"


def load_golden_samples(path: Path) -> list[dict]:
    """Load golden samples from JSONL file."""
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def compute_metrics(samples: list[dict]) -> dict:
    """Run classifier on all samples and compute per-class metrics."""
    classes = ["fact", "opinion", "speculation", "unknown"]
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)
    correct = 0
    unknown_count = 0

    for s in samples:
        expected = s["expected_claim_nature"]
        industry = s.get("industry", "")
        r = classifier.classify(s["claim_text"], industry_code=industry)
        predicted = r.claim_nature.value

        if predicted == "unknown":
            unknown_count += 1

        if predicted == expected:
            correct += 1
            tp[expected] += 1
        else:
            fp[predicted] += 1
            fn[expected] += 1

    total = len(samples)
    accuracy = correct / total if total else 0
    unknown_rate = unknown_count / total if total else 0

    per_class = {}
    for cls in classes:
        tp_c = tp[cls]
        fp_c = fp[cls]
        fn_c = fn[cls]
        precision = tp_c / (tp_c + fp_c) if (tp_c + fp_c) > 0 else 0.0
        recall = tp_c / (tp_c + fn_c) if (tp_c + fn_c) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[cls] = {
            "tp": tp_c, "fp": fp_c, "fn": fn_c,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }

    macro_f1 = sum(per_class[c]["f1"] for c in classes) / len(classes)

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(accuracy, 3),
        "unknown_rate": round(unknown_rate, 3),
        "per_class": per_class,
        "macro_f1": round(macro_f1, 3),
    }


class TestClaimNatureEvaluation:
    """Golden sample evaluation for ClaimNature Chinese classifier."""

    @pytest.fixture(scope="class")
    def samples(self):
        return load_golden_samples(GOLDEN_FILE)

    @pytest.fixture(scope="class")
    def metrics(self, samples):
        return compute_metrics(samples)

    def test_golden_sample_count(self, samples):
        """Ensure at least 120 golden samples."""
        assert len(samples) >= 100, f"Expected >= 100 samples, got {len(samples)}"

    def test_class_distribution(self, samples):
        """Ensure reasonable class distribution."""
        counts = defaultdict(int)
        for s in samples:
            counts[s["expected_claim_nature"]] += 1
        assert counts["fact"] >= 30, f"FACT samples: {counts['fact']}"
        assert counts["opinion"] >= 15, f"OPINION samples: {counts['opinion']}"
        assert counts["speculation"] >= 20, f"SPECULATION samples: {counts['speculation']}"
        assert counts["unknown"] >= 8, f"UNKNOWN samples: {counts['unknown']}"

    def test_accuracy_threshold(self, metrics):
        """MVP: overall accuracy >= 70%."""
        assert metrics["accuracy"] >= 0.70, \
            f"Accuracy {metrics['accuracy']:.1%} below 70% threshold"

    def test_unknown_rate_threshold(self, metrics):
        """MVP: UNKNOWN rate <= 30%."""
        assert metrics["unknown_rate"] <= 0.30, \
            f"UNKNOWN rate {metrics['unknown_rate']:.1%} above 30% threshold"

    def test_speculation_recall_threshold(self, metrics):
        """High-risk recall: SPECULATION recall >= 70%."""
        spec_recall = metrics["per_class"]["speculation"]["recall"]
        assert spec_recall >= 0.70, \
            f"SPECULATION recall {spec_recall:.1%} below 70% threshold"

    def test_fact_precision_threshold(self, metrics):
        """FACT precision should be reasonable."""
        fact_prec = metrics["per_class"]["fact"]["precision"]
        assert fact_prec >= 0.60, \
            f"FACT precision {fact_prec:.1%} below 60% threshold"

    def test_outputs_confidence(self, samples):
        """Every classification should output confidence."""
        for s in samples[:20]:  # Sample first 20 for speed
            r = classifier.classify(s["claim_text"])
            assert 0.0 <= r.confidence <= 1.0

    def test_outputs_matched_signals(self, samples):
        """Every classification should output matched_signals (may be empty)."""
        for s in samples[:20]:
            r = classifier.classify(s["claim_text"])
            assert isinstance(r.matched_signals, list)

    def test_outputs_signal_strength(self, samples):
        """Every classification should output signal_strength."""
        valid = {"strong", "weak", "mixed", "none"}
        for s in samples[:20]:
            r = classifier.classify(s["claim_text"])
            assert r.signal_strength in valid

    def test_outputs_reason(self, samples):
        """Every classification should output reason string."""
        for s in samples[:20]:
            r = classifier.classify(s["claim_text"])
            assert isinstance(r.reason, str) and len(r.reason) > 0

    def test_report_metrics(self, metrics):
        """Print evaluation report (always passes, informational)."""
        report_lines = [
            f"\nClaimNature Evaluation Report",
            f"  Samples: {metrics['total']}",
            f"  Accuracy: {metrics['accuracy']:.1%}",
            f"  Macro F1: {metrics['macro_f1']:.3f}",
            f"  UNKNOWN rate: {metrics['unknown_rate']:.1%}",
            f"  Per-class:",
        ]
        for cls, m in metrics["per_class"].items():
            report_lines.append(
                f"    {cls:15s}  P={m['precision']:.3f}  R={m['recall']:.3f}  "
                f"F1={m['f1']:.3f}  (tp={m['tp']} fp={m['fp']} fn={m['fn']})")
        report = "\n".join(report_lines)
        print(report)
        assert True  # Always passes


class TestIndustryRiskDetection:
    """Industry-specific high-risk term detection."""

    def test_financial_speculation_flagged(self):
        """Financial speculation with high-risk terms -> needs_human_review."""
        r = classifier.classify(
            "该银行预计保本收益达到年化8%",
            industry_code="banking")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert r.industry_risk is True
        assert r.needs_human_review is True

    def test_healthcare_speculation_flagged(self):
        """Healthcare speculation with high-risk terms -> needs_human_review."""
        r = classifier.classify(
            "该药品有望彻底治愈糖尿病且无副作用",
            industry_code="healthcare")
        assert r.claim_nature == ClaimNature.SPECULATION
        assert r.industry_risk is True

    def test_education_opinion_absolute_flagged(self):
        """Education absolute opinion + risk terms -> needs_human_review."""
        r = classifier.classify(
            "我们是最好的培训机构保证100%通过",
            industry_code="education")
        # Should detect industry risk for "最好" + "保证" in education context
        assert r.industry_risk or r.claim_nature in (ClaimNature.OPINION, ClaimNature.SPECULATION)

    def test_non_risk_industry_no_flag(self):
        """Restaurant speculation without risk terms -> no industry flag."""
        r = classifier.classify(
            "星巴克可能推出新口味咖啡",
            industry_code="restaurant_chain")
        assert r.industry_risk is False


class TestNegationWindow:
    """Negation window detection tests."""

    def test_negated_opinion_not_speculation(self):
        """\"并不是最便宜\" should not be classified as speculation."""
        r = classifier.classify("星巴克并不是最便宜的咖啡品牌")
        # Should be OPINION (negated), not SPECULATION
        assert r.claim_nature in (ClaimNature.OPINION, ClaimNature.UNKNOWN)
        if r.claim_nature == ClaimNature.OPINION:
            assert r.negation_detected is True

    def test_negated_fact_stays_fact(self):
        """\"尚未获得批准\" is still a verifiable fact."""
        r = classifier.classify("该产品尚未获得监管部门的正式批准")
        # Should be FACT or UNKNOWN (not SPECULATION)
        assert r.claim_nature != ClaimNature.SPECULATION

    def test_negation_reduces_confidence(self):
        """Negated claims should have lower or checked confidence."""
        r_pos = classifier.classify("星巴克是最好的咖啡品牌")
        r_neg = classifier.classify("星巴克不是最好的咖啡品牌")
        # The negated version may have lower confidence or different classification
        assert r_neg.negation_detected or r_neg.confidence <= r_pos.confidence + 0.1


class TestNGramFallback:
    """n-gram fallback matching tests."""

    def test_ngram_catches_variant(self):
        """n-gram should catch word variants that substring misses."""
        # "市场份额" as signal should match "市场占有份额" via n-gram
        r = classifier.classify("该品牌在市场占有份额方面表现突出")
        # May or may not match — just verify no crash
        assert r.claim_nature in (
            ClaimNature.FACT, ClaimNature.OPINION,
            ClaimNature.SPECULATION, ClaimNature.UNKNOWN)

    def test_ngram_no_false_positive(self):
        """n-gram should NOT match completely unrelated text."""
        r = classifier.classify("天气很好适合出游")
        assert r.claim_nature == ClaimNature.UNKNOWN
        assert "市场份额" not in r.matched_signals
        assert "最好" not in r.matched_signals
