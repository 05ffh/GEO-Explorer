"""Phase A regression tests for hallucination detection — false positive exclusion + true P0 recall."""
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
            "core_products": ["意式浓缩咖啡", "星冰乐", "拿铁", "冷萃咖啡"],
            "core_features": ["第三空间体验", "季节限定饮品", "星巴克会员"],
        }
        status = "active"
    return _GT()


class TestGenericNotP0:
    @pytest.mark.parametrize("sample", load_samples("starbucks_generic_false_positive.jsonl"))
    async def test_generic_statement_not_p0(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        for r in results:
            assert r.verdict != "contradicted", \
                f"{sample['sample_id']}: generic statement wrongly marked contradicted"
            assert r.severity != "P0", \
                f"{sample['sample_id']}: generic statement wrongly marked P0"


class TestGtInsufficientNotP0:
    @pytest.mark.parametrize("sample", load_samples("starbucks_gt_insufficient.jsonl"))
    async def test_gt_insufficient_not_contradicted(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        for r in results:
            assert r.verdict != "contradicted", \
                f"{sample['sample_id']}: GT insufficient wrongly marked contradicted"


class TestTemplateInvalidNotHallucination:
    @pytest.mark.parametrize("sample", load_samples("starbucks_template_invalid.jsonl"))
    async def test_template_invalid_not_hallucination(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session, render_status="missing_variable")
        for r in results:
            assert r.verdict == "template_invalid", \
                f"{sample['sample_id']}: expected template_invalid, got {r.verdict}"
            assert r.severity != "P0", \
                f"{sample['sample_id']}: template invalid wrongly marked P0"


class TestTrueCoreFactErrorDetected:
    @pytest.mark.parametrize("sample", load_samples("true_core_fact_errors.jsonl"))
    async def test_true_core_fact_error_detected(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session)
        p0_results = [r for r in results if r.severity == "P0" and r.verdict == "contradicted"]
        assert len(p0_results) > 0, \
            f"{sample['sample_id']}: true core fact error NOT detected"
        if "expected_matched_gt_field" in sample:
            assert any(r.field_name == sample["expected_matched_gt_field"] for r in p0_results), \
                f"{sample['sample_id']}: expected GT field '{sample['expected_matched_gt_field']}' not matched"
        for r in p0_results:
            assert r.subject_type == "target_brand", \
                f"{sample['sample_id']}: P0 result should have subject_type=target_brand, got '{r.subject_type}'"
