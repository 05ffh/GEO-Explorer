"""P1-3 — Permission & Audit Tests."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.auth.permissions import PERMISSIONS, has_permission
from src.view_models.action import can_transition, TRANSITION_GUARDS
from src.services.audit import sanitize_payload, add_audit_log


class TestPermissionMap:
    """Verify PERMISSIONS dictionary is valid and covers all operations."""

    def test_viewer_has_no_sensitive_permissions(self):
        for perm, roles in PERMISSIONS.items():
            assert "viewer" not in roles, f"viewer should not have {perm}"

    def test_admin_has_all_sensitive_permissions_except_owner_only(self):
        for perm, roles in PERMISSIONS.items():
            if perm == "user.remove_admin":
                continue  # owner-only
            assert has_permission("admin", perm), f"admin should have {perm}"

    def test_admin_does_not_have_owner_only(self):
        assert not has_permission("admin", "user.remove_admin")

    def test_owner_has_all_permissions(self):
        for perm in PERMISSIONS:
            assert has_permission("owner", perm), f"owner should have {perm}"

    def test_gt_reviewer_can_review_gt(self):
        assert has_permission("gt_reviewer", "gt.review") is True
        assert has_permission("gt_reviewer", "gt.promote") is True

    def test_gt_reviewer_cannot_approve_content(self):
        assert has_permission("gt_reviewer", "content.approve.high") is False

    def test_content_editor_can_approve_low(self):
        assert has_permission("content_editor", "content.approve.low") is True

    def test_content_editor_cannot_approve_high(self):
        assert has_permission("content_editor", "content.approve.high") is False

    def test_legal_reviewer_can_approve_all_levels(self):
        for level in ("low", "medium", "high"):
            assert has_permission("legal_reviewer", f"content.approve.{level}") is True

    def test_analyst_can_review_hallucination(self):
        assert has_permission("analyst", "hallucination.review") is True

    def test_analyst_cannot_promote_gt(self):
        assert has_permission("analyst", "gt.promote") is False

    def test_unknown_permission_returns_false(self):
        assert has_permission("admin", "nonexistent.permission") is False

    def test_user_manage_permissions_split(self):
        assert "user.view" in PERMISSIONS
        assert "user.invite" in PERMISSIONS
        assert "user.role_change" in PERMISSIONS
        assert "user.disable" in PERMISSIONS
        assert "user.remove" in PERMISSIONS

    def test_only_owner_can_remove_admin(self):
        assert "owner" in PERMISSIONS["user.remove_admin"]
        assert "admin" not in PERMISSIONS["user.remove_admin"]


class TestAuditSanitization:
    """Verify sensitive fields are masked in audit payloads."""

    def test_masks_api_key(self):
        result = sanitize_payload({"api_key": "sk-secret123", "name": "test"})
        assert result["api_key"] == "***REDACTED***"
        assert result["name"] == "test"

    def test_masks_token(self):
        result = sanitize_payload({"token": "abc123", "data": "ok"})
        assert result["token"] == "***REDACTED***"

    def test_masks_password(self):
        result = sanitize_payload({"password": "secret"})
        assert result["password"] == "***REDACTED***"

    def test_masks_nested_secrets(self):
        result = sanitize_payload({"config": {"api_key": "sk-nested", "host": "x.com"}})
        assert result["config"]["api_key"] == "***REDACTED***"
        assert result["config"]["host"] == "x.com"

    def test_handles_empty_payload(self):
        assert sanitize_payload({}) == {}
        assert sanitize_payload(None) == {}


class TestAuditLogService:
    """Verify audit log service sanitizes and creates entries correctly."""

    @pytest.mark.asyncio
    async def test_add_audit_log_creates_orm_object_without_commit(self, db_session):
        """add_audit_log creates an AuditLog ORM object and adds to session."""
        user = MagicMock()
        user.organization_id = "00000000-0000-0000-0000-000000000001"
        user.id = "00000000-0000-0000-0000-000000000002"
        user.name = "Test User"
        user.role = "admin"

        await add_audit_log(db_session, user, "gt_promote", "gt_candidate", "cand-1",
                            before={"status": "pending"}, after={"status": "active"},
                            reason="Verified evidence")

        # Verify the AuditLog was added to session (but NOT committed)
        assert len(db_session.new) >= 1

    @pytest.mark.asyncio
    async def test_add_audit_log_sanitizes_sensitive_fields(self, db_session):
        user = MagicMock()
        user.organization_id = "org-1"
        user.id = "user-1"
        user.name = "Test"
        user.role = "admin"

        await add_audit_log(db_session, user, "gt_promote", "gt_candidate", "cand-1",
                            before={"api_key": "sk-secret", "name": "test"})

        for obj in db_session.new:
            if hasattr(obj, 'before_json'):
                assert obj.before_json["api_key"] == "***REDACTED***"
                assert obj.before_json["name"] == "test"
