"""P1-3 — Permission & Audit Tests (Dual-Layer Platform + Org)."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.auth.permissions import (
    ORG_PERMISSIONS, PLATFORM_PERMISSIONS,
    has_permission, has_org_permission, has_platform_permission,
)
from src.view_models.action import can_transition, TRANSITION_GUARDS
from src.services.audit import sanitize_payload, add_audit_log


class TestPermissionMap:
    """Verify dual-layer permission system."""

    # -- Platform permissions --
    def test_system_owner_has_all_platform_perms(self):
        for perm in PLATFORM_PERMISSIONS:
            assert has_platform_permission("system_owner", perm)

    def test_system_admin_has_scoped_platform_perms(self):
        assert has_platform_permission("system_admin", "platform.user.manage_all")
        assert not has_platform_permission("system_admin", "platform.organization.delete")

    def test_system_operator_can_only_view_health(self):
        assert has_platform_permission("system_operator", "platform.system_health.view")
        assert not has_platform_permission("system_operator", "platform.user.manage_all")

    def test_org_role_has_no_platform_perms(self):
        assert not has_platform_permission("admin", "platform.organization.create")
        assert not has_platform_permission("owner", "platform.config.manage")

    # -- Organization permissions --
    def test_viewer_has_no_sensitive_permissions(self):
        for perm, roles in ORG_PERMISSIONS.items():
            assert "viewer" not in roles, f"viewer should not have {perm}"

    def test_admin_has_all_org_perms_except_owner_only(self):
        for perm, roles in ORG_PERMISSIONS.items():
            if perm == "user.remove_admin":
                continue
            assert has_org_permission("admin", perm), f"admin should have {perm}"

    def test_admin_does_not_have_owner_only(self):
        assert not has_org_permission("admin", "user.remove_admin")

    def test_owner_has_all_org_permissions(self):
        for perm in ORG_PERMISSIONS:
            assert has_org_permission("owner", perm), f"owner should have {perm}"

    # -- Unified has_permission --
    def test_system_owner_has_everything(self):
        """system_owner bypasses all permission checks."""
        for perm in PLATFORM_PERMISSIONS:
            assert has_permission("system_owner", None, perm)
        for perm in ORG_PERMISSIONS:
            assert has_permission("system_owner", None, perm)

    def test_normal_org_admin_no_platform_perms(self):
        assert not has_permission(None, "admin", "platform.organization.delete")
        assert not has_permission(None, "admin", "platform.audit.view_all")

    def test_org_perm_without_role_returns_false(self):
        assert not has_permission(None, None, "gt.review")
        assert not has_permission(None, None, "content.publish")


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
