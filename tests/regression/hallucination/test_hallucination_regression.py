"""Phase A regression tests for hallucination detection — 4-layer classification coverage."""
import uuid
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

REGRESSION_DIR = Path(__file__).parent


def load_samples(filename: str) -> list[dict]:
    with open(REGRESSION_DIR / filename) as f:
        return [json.loads(line) for line in f if line.strip()]


def _make_query_result_mock(sample: dict):
    qr = MagicMock()
    qr.id = sample.get("sample_id", "test")
    qr.answer_text = sample.get("response", "")
    qr.brand_id = uuid.uuid4()
    qr.platform = "deepseek"
    qr.status = "success"
    qr.question = sample.get("question", "")
    return qr


@pytest.fixture
def detector():
    from src.analyzer.hallucination import HallucinationDetector
    return HallucinationDetector()


@pytest.fixture
def starbucks_gt():
    class _GT:
        id = "gt-test-id"
        ground_truth_json = {
            "official_name": "星巴克（Starbucks）",
            "industry": "连锁咖啡/餐饮零售",
            "category": "连锁咖啡品牌",
            "positioning": "高端品质咖啡品牌",
            "core_products": ["意式浓缩咖啡", "星冰乐", "拿铁", "冷萃咖啡"],
            "core_features": ["第三空间体验", "季节限定饮品", "星巴克会员"],
        }
        status = "active"
    return _GT()


# ── Layer 4: Not About Brand ──────────────────────────────────────────────

class TestNotAboutBrand:
    """Responses unrelated to the target brand → not_about_brand or generic_statement."""

    @pytest.mark.parametrize("sample", load_samples("starbucks_generic_false_positive.jsonl"))
    async def test_generic_statement_not_p0(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        for r in results:
            assert r.verdict != "contradicted", \
                f"{sample['sample_id']}: expected non-contradicted, got {r.verdict}"
            assert r.severity != "P0", \
                f"{sample['sample_id']}: expected non-P0, got {r.severity}"
            assert r.verdict in ("generic_statement", "not_about_brand"), \
                f"{sample['sample_id']}: expected generic/not_about_brand, got {r.verdict}"


# ── Layer 3: GT Insufficient ───────────────────────────────────────────────

class TestGtInsufficientNotP0:
    """Claims that GT cannot verify → gt_insufficient or unsupported, never contradicted."""

    @pytest.mark.parametrize("sample", load_samples("starbucks_gt_insufficient.jsonl"))
    async def test_gt_insufficient_not_contradicted(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        for r in results:
            assert r.verdict != "contradicted", \
                f"{sample['sample_id']}: GT insufficient wrongly marked contradicted"
            if r.field_name:
                assert r.subject_type in ("target_brand", "generic"), \
                    f"{sample['sample_id']}: unexpected subject_type '{r.subject_type}'"


# ── Layer 2: Template Issue ────────────────────────────────────────────────

class TestTemplateInvalidNotHallucination:
    """Unresolved template variables → template_invalid verdict."""

    @pytest.mark.parametrize("sample", load_samples("starbucks_template_invalid.jsonl"))
    async def test_template_invalid_not_hallucination(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session, render_status="missing_variable")
        for r in results:
            assert r.verdict == "template_invalid", \
                f"{sample['sample_id']}: expected template_invalid, got {r.verdict}"
            assert r.severity != "P0", \
                f"{sample['sample_id']}: template invalid wrongly marked P0"


# ── Layer 1: AI Hallucination ──────────────────────────────────────────────

class TestTrueCoreFactErrorDetected:
    """Genuine contradictions with GT → contradicted with correct severity and field."""

    @pytest.mark.parametrize("sample", load_samples("true_core_fact_errors.jsonl"))
    async def test_true_core_fact_error_detected(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        expected_sev = sample.get("expected_severity", "P0")
        matched = [r for r in results
                   if r.severity == expected_sev and r.verdict == "contradicted"]
        assert len(matched) > 0, \
            f"{sample['sample_id']}: true core fact error NOT detected (expected {expected_sev})"
        if "expected_matched_gt_field" in sample:
            assert any(r.field_name == sample["expected_matched_gt_field"] for r in matched), \
                f"{sample['sample_id']}: expected GT field '{sample['expected_matched_gt_field']}' not matched"
        for r in matched:
            assert r.subject_type == "target_brand", \
                f"{sample['sample_id']}: should have subject_type=target_brand, got '{r.subject_type}'"


# ── Cross-cutting: subject_type propagation ────────────────────────────────

class TestSubjectTypePropagation:
    """HallucinationResult must carry subject_type from claim detection."""

    @pytest.mark.parametrize("sample", [
        {"sample_id": "subj_brand", "response": "星巴克的核心产品是咖啡。",
         "expected_subject": "target_brand"},
        {"sample_id": "subj_generic", "response": "选择一个可靠的供应商很重要。",
         "expected_subject": ""},
    ])
    async def test_subject_type_set(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        for r in results:
            if sample["expected_subject"]:
                assert r.subject_type == sample["expected_subject"], \
                    f"{sample['sample_id']}: subject_type mismatch"


# ── Edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Boundary conditions that should not throw exceptions."""

    async def test_empty_response_returns_single_result(self, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock({"sample_id": "empty", "response": "", "question": "?"})
        results = await detector.detect(qr, starbucks_gt, db_session)
        assert len(results) == 1
        assert results[0].verdict in ("not_about_brand", "generic_statement")

    async def test_very_short_response_not_brand_related(self, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock({"sample_id": "short", "response": "好的。", "question": "?"})
        results = await detector.detect(qr, starbucks_gt, db_session)
        assert len(results) >= 0  # should not crash
        for r in results:
            assert r.verdict != "contradicted"

    async def test_response_only_mentions_brand_once(self, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock({
            "sample_id": "single_mention",
            "response": "市面上有很多咖啡品牌。星巴克是其中之一，但本回答不展开讨论。",
            "question": "有哪些咖啡品牌？",
        })
        results = await detector.detect(qr, starbucks_gt, db_session)
        # Brand mentioned but not as primary subject — should not create false P0
        for r in results:
            assert r.severity != "P0", \
                f"single brand mention should not trigger P0, got {r.verdict}/{r.severity}"
