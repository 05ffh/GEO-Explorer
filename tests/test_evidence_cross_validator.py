"""P2-2: EvidenceCrossValidator unit and integration tests."""
import pytest
from unittest.mock import MagicMock, PropertyMock
from src.services.evidence_cross_validator import (
    EvidenceCrossValidator, EvidenceStrengthLevel, ConflictLevel,
    FieldEvidence, EvidenceConsensusResult, EvidenceCache,
    compute_source_weight, _normalize_value, _values_match,
    CRITICAL_FIELDS,
)
from src.schemas.gt_v2 import SOURCE_TIER_RANK


# ── Test fixtures ─────────────────────────────────────────────────────────

def _make_gt(gt_json, gt_schema_version="gt_v2", source_urls=None):
    """Create a mock GroundTruthVersion."""
    gt = MagicMock()
    gt.id = "test-gt-id"
    gt.ground_truth_json = gt_json
    gt.gt_schema_version = gt_schema_version
    gt.source_urls = source_urls or []
    return gt


def _make_v2_field(values):
    """Make v2 GT field structure."""
    return {"fields": {"test_field": {"values": values}}}


def _make_source(tier="B", source_type="other", evidence_text="", url="", confirmed=False):
    src = {"tier": tier, "source_type": source_type, "url": url, "evidence_text": evidence_text}
    if confirmed:
        src["confirmed_by"] = "test-user"
    return src


def _make_value(value, primary=True, sources=None):
    return {"value": value, "primary": primary, "sources": sources or []}


# ── Value normalization tests ────────────────────────────────────────────

class TestValueNormalization:
    def test_lowercase_trim(self):
        assert _normalize_value("  CoffEE  ") == "coffee"

    def test_brand_name_prefix(self):
        assert _normalize_value("星巴克 星冰乐") == "星冰乐"
        assert _normalize_value("starbucks latte") == "latte"

    def test_fullwidth_to_halfwidth(self):
        v = _normalize_value("Ｃｏｆｆｅｅ")
        assert v == "coffee"

    def test_punctuation_normalize(self):
        v = _normalize_value("咖啡，茶、可可")
        assert "，" not in v
        assert "、" not in v

    def test_empty_string(self):
        assert _normalize_value("") == ""
        assert _normalize_value("  ") == ""

    def test_alias_match(self):
        assert _values_match("frappuccino", "星冰乐")

    def test_exact_match(self):
        assert _values_match("coffee", "coffee")

    def test_no_match(self):
        assert not _values_match("coffee", "tea")


# ── Source weight tests ──────────────────────────────────────────────────

class TestSourceWeight:
    def test_tier_base(self):
        assert compute_source_weight({"tier": "S"}) == 5.0
        assert compute_source_weight({"tier": "A"}) == 4.0
        assert compute_source_weight({"tier": "C"}) == 2.0

    def test_official_multiplier(self):
        w = compute_source_weight({"tier": "A", "source_type": "official_site"})
        assert w == round(4.0 * 1.2, 3)

    def test_evidence_text_multiplier(self):
        w = compute_source_weight({"tier": "B", "evidence_text": "some text"})
        assert w == round(3.0 * 1.1, 3)

    def test_d_tier_capped(self):
        w = compute_source_weight({"tier": "D", "source_type": "official_site", "evidence_text": "text"})
        assert w <= 1.0

    def test_combined_multipliers(self):
        w = compute_source_weight({
            "tier": "A", "source_type": "official_report",
            "evidence_text": "evidence", "confirmed_by": "user",
        })
        assert w == round(4.0 * 1.2 * 1.1 * 1.1, 3)


# ── FieldEvidence building tests ──────────────────────────────────────────

class TestBuildFieldEvidence:
    def test_v1_gt_unavailable(self):
        gt = _make_gt({"field": "value"}, gt_schema_version=None)
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("test_field")
        assert fe.gt_schema == "v1"
        assert "v1 GT" in str(fe.notes)

    def test_v2_no_values(self):
        gt = _make_gt({"fields": {}})
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("nonexistent")
        assert fe.total_sources == 0

    def test_v2_single_source_s_tier(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("S", "official_site", "evidence")])
        ])
        gt = _make_gt(gt_json)
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("test_field")
        assert fe.total_sources == 1
        assert fe.best_tier == "S"
        assert fe.consensus_value == "coffee"
        assert fe.agreement_ratio == 1.0

    def test_v2_multi_source_all_agree(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[
                _make_source("S", "official_site", "evidence"),
                _make_source("A", "database"),
            ])
        ])
        gt = _make_gt(gt_json)
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("test_field")
        assert fe.total_sources == 2
        assert fe.agreement_ratio == 1.0
        assert fe.has_conflict is False
        assert fe.best_tier == "S"

    def test_v2_synonym_values_not_conflict(self):
        gt_json = _make_v2_field([
            _make_value("星冰乐", sources=[_make_source("A")]),
            _make_value("Frappuccino", sources=[_make_source("B")]),
        ])
        gt = _make_gt(gt_json)
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("test_field")
        assert fe.distinct_raw_values == 2
        assert len(fe.variants) == 1  # aliases merged
        assert fe.has_conflict is False

    def test_v2_conflict_different_values(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A")]),
            _make_value("tea", sources=[_make_source("B")]),
        ])
        gt = _make_gt(gt_json)
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("test_field")
        assert fe.has_conflict is True
        assert len(fe.variants) == 2

    def test_consensus_weighted_not_highest_tier(self):
        """S-tier has 1 source, but A-tier has 5 sources — A should win."""
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("S", "official_site")]),
            _make_value("beverage", sources=[
                _make_source("A", "database"),
                _make_source("A", "database"),
                _make_source("A", "database"),
                _make_source("B"),
                _make_source("B"),
            ]),
        ])
        gt = _make_gt(gt_json)
        validator = EvidenceCrossValidator(gt)
        fe = validator.build_field_evidence("test_field")
        assert fe.has_conflict is True
        # beverage has 5 sources with higher weighted score
        assert fe.consensus_value == "beverage"


# ── Conflict level tests ──────────────────────────────────────────────────

class TestConflictLevel:
    def test_none_single_variant(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A"), _make_source("B")])
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        fe = validator.build_field_evidence("test_field")
        assert fe.conflict_level == ConflictLevel.NONE

    def test_weak_conflict_c_d_dissent(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A")]),
            _make_value("tea", sources=[_make_source("C"), _make_source("D")]),
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        fe = validator.build_field_evidence("test_field")
        assert fe.conflict_level == ConflictLevel.WEAK

    def test_moderate_conflict_b_dissent(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A")]),
            _make_value("tea", sources=[_make_source("B")]),
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        fe = validator.build_field_evidence("test_field")
        assert fe.conflict_level == ConflictLevel.MODERATE

    def test_strong_conflict_a_dissent(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("S")]),
            _make_value("tea", sources=[_make_source("A")]),
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        fe = validator.build_field_evidence("test_field")
        assert fe.conflict_level == ConflictLevel.STRONG

    def test_critical_conflict_on_critical_field(self):
        # Use "industry" field (is critical) with conflicting S vs A sources
        gt_json = {
            "fields": {
                "industry": {
                    "values": [
                        _make_value("coffee", sources=[_make_source("S")]),
                        _make_value("tea", sources=[_make_source("A")]),
                    ]
                }
            }
        }
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        fe = validator.build_field_evidence("industry")
        assert fe.is_critical_field is True
        assert fe.has_conflict is True
        assert fe.conflict_level == ConflictLevel.CRITICAL


# ── Consensus/Strength tests ─────────────────────────────────────────────

class TestComputeConsensus:
    def test_v1_gt_returns_unavailable(self):
        gt = _make_gt({"field": "value"}, gt_schema_version=None)
        validator = EvidenceCrossValidator(gt)
        result = validator.compute_consensus("test_field", "supported")
        assert result.evidence_strength_level == EvidenceStrengthLevel.UNAVAILABLE

    def test_no_sources_returns_insufficient(self):
        gt = _make_gt({"fields": {}})
        validator = EvidenceCrossValidator(gt)
        result = validator.compute_consensus("test_field", "supported")
        assert result.evidence_strength_level == EvidenceStrengthLevel.INSUFFICIENT

    def test_single_official_s_strong(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("S", "official_site", "evidence text")])
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        result = validator.compute_consensus("test_field", "supported")
        assert result.evidence_strength_level == EvidenceStrengthLevel.STRONG

    def test_single_c_weak(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("C")])
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        result = validator.compute_consensus("test_field", "supported")
        assert result.evidence_strength_level == EvidenceStrengthLevel.WEAK

    def test_multi_source_strong(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[
                _make_source("S", "official_site", "evidence"),
                _make_source("A", "database"),
            ])
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        result = validator.compute_consensus("test_field", "supported")
        assert result.evidence_strength_level == EvidenceStrengthLevel.STRONG

    def test_disputed_conflict(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A")]),
            _make_value("tea", sources=[_make_source("B")]),
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        result = validator.compute_consensus("test_field", "supported")
        assert result.evidence_strength_level == EvidenceStrengthLevel.DISPUTED
        assert result.base_verdict == "supported"

    def test_to_json_output(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A"), _make_source("B")])
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        result = validator.compute_consensus("test_field", "supported")
        j = result.to_json()
        assert j["schema_version"] == "evidence_consensus_v1"
        assert j["field_name"] == "test_field"
        assert j["base_verdict"] == "supported"
        assert "value_variants" in j
        assert "best_source" in j


# ── Cache tests ───────────────────────────────────────────────────────────

class TestEvidenceCache:
    def test_cache_hit(self):
        cache = EvidenceCache()
        fe = FieldEvidence(field_name="test")
        cache.set("gt1", "field1", fe)
        assert cache.get("gt1", "field1") is fe

    def test_cache_miss(self):
        cache = EvidenceCache()
        assert cache.get("gt1", "field1") is None

    def test_cache_isolated_by_gt_version(self):
        cache = EvidenceCache()
        fe1 = FieldEvidence(field_name="f1")
        fe2 = FieldEvidence(field_name="f2")
        cache.set("gt1", "field1", fe1)
        cache.set("gt2", "field1", fe2)
        assert cache.get("gt1", "field1") is fe1
        assert cache.get("gt2", "field1") is fe2
        assert len(cache) == 2

    def test_cache_clear(self):
        cache = EvidenceCache()
        cache.set("gt1", "field1", FieldEvidence(field_name="test"))
        cache.clear()
        assert len(cache) == 0

    def test_validator_uses_cache(self):
        gt_json = _make_v2_field([
            _make_value("coffee", sources=[_make_source("A")])
        ])
        validator = EvidenceCrossValidator(_make_gt(gt_json))
        fe1 = validator.build_field_evidence("test_field")
        fe2 = validator.build_field_evidence("test_field")
        assert fe1 is fe2  # same cached object


# ── Critical fields ───────────────────────────────────────────────────────

class TestCriticalFields:
    def test_critical_fields_list(self):
        assert "official_name" in CRITICAL_FIELDS
        assert "industry" in CRITICAL_FIELDS
        assert "regulatory_status" in CRITICAL_FIELDS
