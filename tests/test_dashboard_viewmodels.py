"""Phase 12 Dashboard — ViewModel Tests."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.view_models.dashboard import KPI_KEYS, get_latest_completed_run
from src.view_models.hallucination import cluster_key
from src.view_models.action import can_transition, TRANSITION_GUARDS
from src.view_models.trends import compute_attribution_label


class TestDashboardKPIKeys:
    def test_ten_kpi_keys_defined(self):
        assert len(KPI_KEYS) == 10

    def test_core_five_included(self):
        assert "sov" in KPI_KEYS
        assert "first_rec_rate" in KPI_KEYS
        assert "accuracy_rate" in KPI_KEYS
        assert "completeness_rate" in KPI_KEYS
        assert "citation_rate" in KPI_KEYS

    def test_extended_five_included(self):
        assert "scenario_recall" in KPI_KEYS
        assert "semantic_stability" in KPI_KEYS
        assert "differentiation" in KPI_KEYS
        assert "cross_platform_consistency" in KPI_KEYS
        assert "recommendation_quality" in KPI_KEYS


class TestHallucinationClustering:
    def test_cluster_key_includes_all_dimensions(self):
        """P0-10: Cluster key uses (error_type, severity, field_name, dimension)."""
        mock_h = MagicMock()
        mock_h.error_type = "category_error"
        mock_h.severity = "P0"
        mock_h.field_name = "positioning"

        key = cluster_key(mock_h, "品牌认知")
        assert key == ("category_error", "P0", "positioning", "品牌认知")

    def test_cluster_key_different_fields_not_same_cluster(self):
        """Different field_name → different clusters even with same error_type."""
        h1 = MagicMock(error_type="identity_error", severity="P0", field_name="official_name")
        h2 = MagicMock(error_type="identity_error", severity="P0", field_name="positioning")

        assert cluster_key(h1, "品牌认知") != cluster_key(h2, "品牌认知")

    def test_cluster_key_null_error_type_defaults(self):
        mock_h = MagicMock(error_type=None, severity="P1", field_name="category")
        key = cluster_key(mock_h, "")
        assert key[0] == "unknown"


class TestActionTransitionGuards:
    def test_viewer_cannot_confirm_action(self):
        """P0-11: Viewer cannot transition detected → confirmed."""
        assert can_transition("viewer", "detected", "confirmed") is False

    def test_admin_can_confirm_action(self):
        assert can_transition("admin", "detected", "confirmed") is True

    def test_analyst_can_confirm_action(self):
        assert can_transition("analyst", "detected", "confirmed") is True

    def test_gt_reviewer_can_confirm_action(self):
        assert can_transition("gt_reviewer", "detected", "confirmed") is True

    def test_content_editor_cannot_confirm_action(self):
        assert can_transition("content_editor", "detected", "confirmed") is False

    def test_content_editor_can_generate_content(self):
        assert can_transition("content_editor", "confirmed", "content_generating") is True

    def test_viewer_cannot_generate_content(self):
        assert can_transition("viewer", "confirmed", "content_generating") is False

    def test_only_legal_reviewer_can_approve(self):
        """P0-11: content_ready → approved requires legal_reviewer or admin."""
        assert can_transition("legal_reviewer", "content_ready", "approved") is True
        assert can_transition("content_editor", "content_ready", "approved") is False
        assert can_transition("viewer", "content_ready", "approved") is False

    def test_only_admin_can_verify(self):
        """published_marked → verification_pending requires admin."""
        assert can_transition("admin", "published_marked", "verification_pending") is True
        assert can_transition("content_editor", "published_marked", "verification_pending") is False

    def test_admin_can_verify_completed(self):
        assert can_transition("admin", "verification_pending", "verified") is True
        assert can_transition("analyst", "verification_pending", "verified") is True

    def test_invalid_transition_returns_false(self):
        """Non-existent transition always returns False."""
        assert can_transition("admin", "detected", "published_marked") is False
        assert can_transition("admin", "verified", "detected") is False

    def test_all_guards_have_valid_statuses(self):
        """Every guard key references real THEME_TRANSITIONS states."""
        from src.models.action_theme import THEME_TRANSITIONS
        for (from_s, to_s), roles in TRANSITION_GUARDS.items():
            assert to_s in THEME_TRANSITIONS.get(from_s, []), \
                f"Guard ({from_s}→{to_s}) not in THEME_TRANSITIONS"
            assert isinstance(roles, tuple)
            assert all(isinstance(r, str) for r in roles)


class TestAttribution:
    def test_insufficient_sample_label(self):
        """P0-13: Sample < 3 returns '样本不足'."""
        label = compute_attribution_label(0.5, 0.6, 2, False, False)
        assert label == "样本不足"

    def test_platform_failure_label(self):
        label = compute_attribution_label(0.5, 0.6, 5, False, True)
        assert label == "平台失败影响"

    def test_gt_update_label(self):
        label = compute_attribution_label(0.5, 0.6, 5, True, False)
        assert label == "GT 更新混淆"

    def test_possible_action_effect_label(self):
        """Significant change → '可能由 Action 导致'."""
        label = compute_attribution_label(0.5, 0.65, 5, False, False)
        assert label == "可能由 Action 导致"

    def test_no_obvious_effect_label(self):
        label = compute_attribution_label(0.50, 0.51, 5, False, False)
        assert label == "无明显效果"
