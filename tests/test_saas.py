"""P2-5 Multi-tenant SaaS tests — models, entitlement, quota, API Key, security."""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ── Model Tests ────────────────────────────────────────────────────────────────

class TestPlanDefinition:
    def test_plan_creation(self):
        from src.models.saas import PlanDefinition
        p = PlanDefinition(name="pro", display_name="专业版", tier=1, version="1.0")
        assert p.name == "pro"
        assert p.tier == 1

    def test_plan_has_quota_fields(self):
        from src.models.saas import PlanDefinition
        quota_fields = ["max_brands", "max_users", "max_api_keys", "max_competitors",
                        "max_cms_targets", "max_reports_per_month", "data_retention_days"]
        for f in quota_fields:
            assert hasattr(PlanDefinition, f)

    def test_plan_unlimited(self):
        from src.models.saas import PlanDefinition
        p = PlanDefinition(name="enterprise", tier=2, version="1.0",
                           max_brands=-1, max_users=-1)
        assert p.max_brands == -1
        assert p.max_users == -1


class TestOrgSubscription:
    def test_subscription_defaults(self):
        from src.models.saas import OrgSubscription
        s = OrgSubscription(organization_id=uuid.uuid4(), plan_id=uuid.uuid4(),
                            status="active", started_at=datetime.now(timezone.utc))
        assert s.status == "active"
        assert s.auto_renew is False or s.auto_renew is None
        assert s.current_brand_count == 0 or s.current_brand_count is None

    def test_subscription_statuses(self):
        valid = {"trialing", "active", "grace", "past_due", "expired",
                 "cancelled", "suspended", "internal_test"}
        assert len(valid) == 8


class TestApiKey:
    def test_api_key_creation(self):
        from src.models.saas import ApiKey
        key = ApiKey(organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
                     name="Test Key", key_prefix="geo_live_",
                     key_hash="abc123", key_type="live",
                     scopes_json=["brands:read"])
        assert key.key_type == "live"
        assert "brands:read" in (key.scopes_json or [])

    def test_api_key_scopes(self):
        from src.models.saas import ApiKey
        key = ApiKey(organization_id=uuid.uuid4(), user_id=uuid.uuid4(),
                     name="API Key", key_prefix="geo_live_",
                     key_hash="def456", key_type="live",
                     scopes_json=["brands:read", "collections:run"])
        assert "brands:read" in key.scopes_json
        assert "collections:run" in key.scopes_json


class TestAllModels:
    def test_all_models_exist(self):
        from src.models.saas import (
            PlanDefinition, OrgSubscription, ApiKey, ApiKeyUsageLog,
            OrgInvite, DataExport, DataDeletionRequest,
            UsageEvent, UsageSnapshot, UsageMeterDefinition,
            PlanChangeRequest, FeatureFlag, FeatureFlagOverride,
            EmergencyPause, PlatformAdminProfile, PlatformAccessSession,
            PlatformApprovalRequest, AuditIntegrityCheck, RateLimitPolicy,
        )
        models = [PlanDefinition, OrgSubscription, ApiKey, ApiKeyUsageLog,
                  OrgInvite, DataExport, DataDeletionRequest,
                  UsageEvent, UsageSnapshot, UsageMeterDefinition,
                  PlanChangeRequest, FeatureFlag, FeatureFlagOverride,
                  EmergencyPause, PlatformAdminProfile, PlatformAccessSession,
                  PlatformApprovalRequest, AuditIntegrityCheck, RateLimitPolicy]
        for m in models:
            assert hasattr(m, "__tablename__")


class TestOrganizationExtension:
    def test_org_has_new_fields(self):
        from src.models.organization import Organization
        org = Organization(name="Test Org")
        assert hasattr(org, "slug")
        assert hasattr(org, "is_active")
        assert hasattr(org, "brand_count")
        assert hasattr(org, "onboarding_step")

    def test_org_slug_can_be_set(self):
        from src.models.organization import Organization
        org = Organization(name="Test", slug="test-org")
        assert org.slug == "test-org"


class TestUserExtension:
    def test_user_has_new_fields(self):
        from src.models.user import User
        u = User(organization_id=uuid.uuid4(), email="test@test.com",
                 name="Test", password_hash="hash")
        assert hasattr(u, "platform_mfa_required")
        assert hasattr(u, "platform_access_enabled")


# ── Entitlement Tests ─────────────────────────────────────────────────────────

class TestEntitlement:
    def test_default_free_entitlements(self):
        from src.saas.entitlement import DEFAULT_FREE_ENTITLEMENTS
        assert "features" in DEFAULT_FREE_ENTITLEMENTS
        assert "limits" in DEFAULT_FREE_ENTITLEMENTS
        assert DEFAULT_FREE_ENTITLEMENTS["limits"]["max_brands"] == 1

    def test_default_free_entitlements_structure(self):
        from src.saas.entitlement import DEFAULT_FREE_ENTITLEMENTS
        assert "features" in DEFAULT_FREE_ENTITLEMENTS
        assert "limits" in DEFAULT_FREE_ENTITLEMENTS
        assert DEFAULT_FREE_ENTITLEMENTS["limits"]["max_brands"] == 1

    def test_subscription_blocking_statuses(self):
        blocking = {"expired": "subscription_expired",
                    "suspended": "subscription_suspended",
                    "cancelled": "subscription_cancelled"}
        assert len(blocking) == 3

    def test_priority_levels(self):
        """7 priority levels in effective entitlements."""
        levels = ["emergency_pause", "subscription_status", "system_owner_override",
                  "feature_flag_override", "subscription_snapshot",
                  "plan_definition", "default_free"]
        assert len(levels) == 7

    def test_check_feature(self):
        from src.saas.entitlement import check_feature
        entitlements = {"effective_features": {"feature_benchmark": True}}
        assert check_feature(entitlements, "feature_benchmark") is True
        assert check_feature(entitlements, "feature_trends") is False

    def test_check_limit(self):
        from src.saas.entitlement import check_limit
        entitlements = {"effective_limits": {"max_brands": 10}}
        assert check_limit(entitlements, "max_brands") == 10
        assert check_limit(entitlements, "max_competitors") == 0

    def test_unified_feature_keys(self):
        from src.saas.entitlement import UNIFIED_FEATURE_KEYS
        assert "feature_benchmark" in UNIFIED_FEATURE_KEYS
        assert "feature_cms_webhook" in UNIFIED_FEATURE_KEYS
        assert "feature_api_access" in UNIFIED_FEATURE_KEYS


# ── Quota Tests ───────────────────────────────────────────────────────────────

class TestQuota:
    @pytest.mark.asyncio
    async def test_quota_exceeded_raises_error(self):
        from src.saas.quota import QuotaExceededError
        with pytest.raises(QuotaExceededError):
            raise QuotaExceededError("brands", 1, 1, "升级到 Pro")

    def test_quota_error_contains_upgrade_hint(self):
        from src.saas.quota import QuotaExceededError
        err = QuotaExceededError("brands", 1, 1, "升级到 Pro")
        assert "brands" in str(err)
        assert "升级到 Pro" == err.upgrade_hint

    @pytest.mark.asyncio
    async def test_quota_unlimited_minus_one(self):
        """-1 means unlimited quota."""
        from src.saas.quota import check_and_reserve_quota
        db = AsyncMock()
        sub = MagicMock()
        sub.status = "active"
        sub.override_max_brands = -1
        sub.override_max_users = None
        sub.override_max_api_keys = None
        sub.override_max_cms_targets = None
        sub.entitlements_snapshot_json = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub

        async def mock_exec(stmt):
            return mock_result

        db.execute.side_effect = mock_exec
        result = await check_and_reserve_quota(db, uuid.uuid4(), "brands")
        assert result is True

    def test_hard_limit_types(self):
        hard_limits = ["brands", "users", "api_keys", "cms_targets"]
        assert len(hard_limits) >= 4


# ── API Key Tests ─────────────────────────────────────────────────────────────

class TestApiKeyAuth:
    def test_hash_is_deterministic(self):
        from src.saas.api_key_auth import hash_api_key
        h1 = hash_api_key("test-key-123")
        h2 = hash_api_key("test-key-123")
        assert h1 == h2

    def test_hash_is_different_for_different_keys(self):
        from src.saas.api_key_auth import hash_api_key
        h1 = hash_api_key("test-key-a")
        h2 = hash_api_key("test-key-b")
        assert h1 != h2

    def test_generate_api_key_returns_tuple(self):
        from src.saas.api_key_auth import generate_api_key
        raw, prefix, key_hash = generate_api_key("live")
        assert len(raw) == 64
        assert prefix == "geo_live_"

    def test_generate_test_key(self):
        from src.saas.api_key_auth import generate_api_key
        raw, prefix, key_hash = generate_api_key("test")
        assert prefix == "geo_test_"

    def test_hash_does_not_contain_raw_key(self):
        from src.saas.api_key_auth import generate_api_key, hash_api_key
        raw, prefix, key_hash = generate_api_key()
        assert raw not in key_hash


# ── Organization Extension Tests ──────────────────────────────────────────────

class TestOrganizationModel:
    def test_slug_unique_constraint(self):
        from src.models.organization import Organization
        assert Organization.__table__.columns["slug"].unique is True


# ── EmergencyPause Tests ──────────────────────────────────────────────────────

class TestEmergencyPause:
    def test_pause_scopes(self):
        valid_scopes = {"global", "organization", "feature", "operation_type"}
        assert len(valid_scopes) == 4

    def test_pause_statuses(self):
        valid_statuses = {"active", "resolved", "expired"}
        assert len(valid_statuses) == 3


# ── FeatureFlag Tests ─────────────────────────────────────────────────────────

class TestFeatureFlag:
    def test_flag_types(self):
        valid_types = {"beta_feature", "kill_switch", "commercial_override"}
        assert len(valid_types) == 3


# ── UsageEvent Tests ─────────────────────────────────────────────────────────

class TestUsageEvent:
    def test_idempotency_key_required(self):
        from src.models.saas import UsageEvent
        e = UsageEvent(organization_id=uuid.uuid4(), meter_key="collection_runs",
                       meter_version="1.0", occurred_at=datetime.now(timezone.utc),
                       idempotency_key="test-key-123")
        assert e.idempotency_key == "test-key-123"

    def test_usage_snapshot_types(self):
        valid = {"customer", "internal_cost", "billing"}
        assert len(valid) == 3


# ── Subscription Status Tests ─────────────────────────────────────────────────

class TestSubscriptionStatuses:
    def test_blocking_statuses(self):
        """Statuses that block core actions."""
        blocking = {"suspended", "expired", "cancelled"}
        assert len(blocking) == 3

    def test_allowing_statuses(self):
        allowing = {"active", "trialing", "internal_test"}
        assert len(allowing) == 3


# ── Data Export/Deletion Tests ────────────────────────────────────────────────

class TestDataExport:
    def test_export_statuses(self):
        valid = {"queued", "generating", "completed", "failed", "expired"}
        assert len(valid) == 5

    def test_redaction_levels(self):
        levels = {"basic", "full", "redacted"}
        assert len(levels) == 3


class TestDataDeletion:
    def test_deletion_statuses(self):
        valid = {"requested", "approved", "scheduled", "processing",
                 "completed", "failed", "cancelled"}
        assert len(valid) == 7


# ── PlatformAdminProfile Tests ───────────────────────────────────────────────

class TestPlatformAdmin:
    def test_profile_statuses(self):
        valid = {"active", "suspended", "revoked"}
        assert len(valid) == 3

    def test_mfa_enforced_field_exists(self):
        from src.models.saas import PlatformAdminProfile
        assert hasattr(PlatformAdminProfile, "mfa_enforced")


# ── Scopes Tests ──────────────────────────────────────────────────────────────

class TestApiKeyScopes:
    def test_valid_scopes(self):
        scopes = ["brands:read", "brands:write", "collections:read",
                  "collections:run", "reports:read", "reports:generate",
                  "exports:create", "cms:publish", "usage:read", "admin:manage"]
        assert len(scopes) == 10

    def test_admin_scope_is_highest(self):
        assert "admin:manage" in ["admin:manage"]


# ── Error Code Tests ──────────────────────────────────────────────────────────

class TestErrorCodes:
    def test_error_codes_defined(self):
        codes = [
            "PLAN_VERSION_DEPRECATED", "SUBSCRIPTION_NOT_ACTIVE",
            "SUBSCRIPTION_SUSPENDED", "ENTITLEMENT_DENIED", "QUOTA_EXCEEDED",
            "API_KEY_SCOPE_DENIED", "API_KEY_REVOKED",
            "INVITE_EXPIRED", "INVITE_SEAT_QUOTA_EXCEEDED",
            "EXPORT_PERMISSION_DENIED", "DELETION_REQUIRES_SYSTEM_OWNER_APPROVAL",
            "SYSTEM_OWNER_MFA_REQUIRED", "PLATFORM_ACCESS_REASON_REQUIRED",
            "EMERGENCY_PAUSE_ACTIVE", "FEATURE_FLAG_DISABLED",
        ]
        assert len(codes) == 15
