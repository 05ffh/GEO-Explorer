import pytest
from src.actions.engine import validate_transition
from src.actions.content_factory import generate_content_brief, QUALITY_CHECKLIST
from src.models.action_plan import VALID_TRANSITIONS


class TestStateMachine:
    def test_valid_transition_pending_to_in_progress(self):
        assert validate_transition("pending", "in_progress") is True

    def test_valid_transition_in_progress_to_completed(self):
        assert validate_transition("in_progress", "completed") is True

    def test_valid_transition_completed_to_verified(self):
        assert validate_transition("completed", "verified") is True

    def test_invalid_transition_pending_to_verified(self):
        assert validate_transition("pending", "verified") is False

    def test_invalid_transition_verified_to_anything(self):
        assert validate_transition("verified", "in_progress") is False

    def test_cancelled_terminal(self):
        assert validate_transition("cancelled", "in_progress") is False

    def test_reopened_to_in_progress(self):
        assert validate_transition("reopened", "in_progress") is True

    def test_all_valid_transitions_exist(self):
        assert "pending" in VALID_TRANSITIONS
        assert "in_progress" in VALID_TRANSITIONS
        assert "completed" in VALID_TRANSITIONS
        assert "verified" in VALID_TRANSITIONS
        assert "cancelled" in VALID_TRANSITIONS
        assert "reopened" in VALID_TRANSITIONS


class TestContentBrief:
    def test_generate_faq_brief(self):
        from unittest.mock import MagicMock
        action = MagicMock()
        action.id = "test-action-id"
        action.suggested_content_type = "FAQ"
        action.priority = "P0"
        action.trigger_type = "field_industry_error"
        action.ai_wrong_claims = {"claim": "CRM公司"}
        action.correct_ground_truth = {"field": "industry", "value": "旅游科技"}
        action.target_page = ""
        action.acceptance_criteria = "Field industry resolved"

        gt = {
            "official_name": "TestBrand",
            "industry": "旅游科技",
            "positioning": "飞猪数据平台",
            "differentiators": ["自动化", "AI驱动"],
            "forbidden_claims": ["市场第一"],
        }

        brief = generate_content_brief(action, gt)

        assert brief["action_plan_id"] == "test-action-id"
        assert brief["content_type"] == "FAQ"
        assert brief["priority"] == "P0"
        assert brief["problem_evidence"]["trigger"] == "field_industry_error"
        assert brief["correct_facts"]["field"] == "industry"
        assert brief["correct_facts"]["value"] == "旅游科技"
        assert brief["brand_context"]["official_name"] == "TestBrand"
        assert brief["brand_context"]["industry"] == "旅游科技"
        assert brief["forbidden_claims"] == ["市场第一"]
        assert "question" in "".join(brief["required_sections"]).lower() or \
               len(brief["required_sections"]) == 4
        assert len(brief["quality_checklist"]) == 6

    def test_quality_checklist_has_six_items(self):
        assert len(QUALITY_CHECKLIST) == 6

    def test_get_required_sections_tutorial(self):
        from src.actions.content_factory import _get_required_sections
        sections = _get_required_sections("Tutorial")
        assert len(sections) == 5
        assert "实操步骤" in sections

    def test_get_required_sections_unknown_type(self):
        from src.actions.content_factory import _get_required_sections
        sections = _get_required_sections("UnknownType")
        assert len(sections) == 3
