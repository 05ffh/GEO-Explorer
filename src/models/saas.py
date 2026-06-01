"""GEO Explorer — Multi-tenant SaaS models (P2-5)."""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (String, ForeignKey, Integer, Boolean, Text, DateTime,
                         Numeric, UniqueConstraint, Index)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


# ── PlanDefinition ────────────────────────────────────────────────────────────

class PlanDefinition(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "plan_definitions"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_plans_name_version"),
        Index("ix_plans_name_active", "name", "is_active"),
        Index("ix_plans_public_deprecated", "is_public", "is_deprecated"),
        Index("ix_plans_effective", "effective_from", "effective_until"),
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), default="")
    tier: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Quotas (-1 = unlimited)
    max_brands: Mapped[int] = mapped_column(Integer, default=1)
    max_users: Mapped[int] = mapped_column(Integer, default=1)
    max_competitors: Mapped[int] = mapped_column(Integer, default=0)
    max_api_keys: Mapped[int] = mapped_column(Integer, default=0)
    max_cms_targets: Mapped[int] = mapped_column(Integer, default=0)
    max_webhook_targets: Mapped[int] = mapped_column(Integer, default=0)
    max_reports_per_month: Mapped[int] = mapped_column(Integer, default=0)
    max_exports_per_month: Mapped[int] = mapped_column(Integer, default=0)
    max_collection_runs_per_month: Mapped[int] = mapped_column(Integer, default=0)
    max_questions_per_collection: Mapped[int] = mapped_column(Integer, default=5)
    max_platforms_per_collection: Mapped[int] = mapped_column(Integer, default=3)
    max_api_requests_per_month: Mapped[int] = mapped_column(Integer, default=0)
    data_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    trend_history_days: Mapped[int] = mapped_column(Integer, default=0)
    max_storage_mb: Mapped[int] = mapped_column(Integer, default=100)
    features_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    monthly_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    yearly_price_cny: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


# ── OrgSubscription ───────────────────────────────────────────────────────────

class OrgSubscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "org_subscriptions"
    __table_args__ = (
        Index("ix_sub_org_status", "organization_id", "status"),
        Index("ix_sub_plan_version", "plan_id", "plan_version"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_definitions.id"), nullable=False)
    plan_version: Mapped[str] = mapped_column(String(20), default="1.0")
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    entitlements_snapshot_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Override quotas (Enterprise custom)
    override_max_brands: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_max_api_keys: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_max_cms_targets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Pending change
    pending_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plan_definitions.id"), nullable=True)
    pending_change_effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_change_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Usage cache
    current_brand_count: Mapped[int] = mapped_column(Integer, default=0)
    current_user_count: Mapped[int] = mapped_column(Integer, default=0)
    current_token_usage: Mapped[int] = mapped_column(Integer, default=0)
    current_cost_cny: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    last_usage_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── ApiKey ────────────────────────────────────────────────────────────────────

class ApiKey(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_keys_hash"),
        Index("ix_api_keys_org_active", "organization_id", "is_active"),
        Index("ix_api_keys_prefix", "key_prefix"),
        Index("ix_api_keys_expires", "expires_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    key_type: Mapped[str] = mapped_column(String(20), default="live")  # test/live/service
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes_json: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    allowed_ips: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rotated_from_key_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_used_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)


# ── ApiKeyUsageLog ────────────────────────────────────────────────────────────

class ApiKeyUsageLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_key_usage_logs"
    __table_args__ = (
        Index("ix_apikey_log_key", "api_key_id", "created_at"),
        Index("ix_apikey_log_org", "organization_id"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    api_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("api_keys.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), default="")
    method: Mapped[str] = mapped_column(String(10), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ── OrgInvite ─────────────────────────────────────────────────────────────────

class OrgInvite(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "org_invites"
    __table_args__ = (
        Index("ix_invites_token", "token_hash"),
        Index("ix_invites_expires", "expires_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer")
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/expired/revoked/replaced
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


# ── DataExport ────────────────────────────────────────────────────────────────

class DataExport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "data_exports"
    __table_args__ = (
        Index("ix_exports_org_status", "organization_id", "status"),
        Index("ix_exports_user", "user_id", "created_at"),
        Index("ix_exports_expires", "expires_at"),
        UniqueConstraint("download_token_hash", name="uq_exports_download_token"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="brand")  # brand/organization
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    format: Mapped[str] = mapped_column(String(20), default="json")  # json/csv_zip
    redaction_level: Mapped[str] = mapped_column(String(20), default="full")  # basic/full/redacted
    included_sections_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    task_state_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    download_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_by_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    export_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── DataDeletionRequest ───────────────────────────────────────────────────────

class DataDeletionRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "data_deletion_requests"
    __table_args__ = (
        Index("ix_deletion_org_scope_status", "organization_id", "scope", "status"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="brand")  # brand/organization
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    scheduled_delete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, default=90)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_tables_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    affected_backup_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run_result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    task_state_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_table: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failed_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_processed_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


# ── DeletionReceipt ───────────────────────────────────────────────────────────

class DeletionReceipt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "deletion_receipts"
    __table_args__ = (
        UniqueConstraint("deletion_request_id", name="uq_deletion_receipt_request"),
        Index("ix_receipt_org", "organization_id"),
    )
    deletion_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_deletion_requests.id"), nullable=False, unique=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    affected_tables_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    deleted_counts_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    anonymized_counts_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    retained_items_json: Mapped[list] = mapped_column(JSONB, default=list)
    file_deleted_count: Mapped[int] = mapped_column(Integer, default=0)
    file_failed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_assets_json: Mapped[list] = mapped_column(JSONB, default=list)
    backup_expiry_note: Mapped[str] = mapped_column(Text, default="Backups will expire according to backup retention policy.")
    receipt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_log_refs_json: Mapped[list] = mapped_column(JSONB, default=list)


# ── UsageEvent ────────────────────────────────────────────────────────────────

class UsageEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_usage_events_idempotency"),
        Index("ix_usage_events_org_meter_time", "organization_id", "meter_key", "occurred_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    meter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    meter_version: Mapped[str] = mapped_column(String(20), default="1.0")
    source_type: Mapped[str] = mapped_column(String(50), default="")
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=1)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


# ── UsageSnapshot ─────────────────────────────────────────────────────────────

class UsageSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "usage_snapshots"
    __table_args__ = (
        UniqueConstraint("organization_id", "period_start", "period_end", "snapshot_type",
                         name="uq_usage_snapshots_period"),
        Index("ix_usage_snapshots_period", "period_start", "period_end"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(30), default="customer")  # customer/internal_cost/billing
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    period_type: Mapped[str] = mapped_column(String(20), default="monthly")
    brand_count: Mapped[int] = mapped_column(Integer, default=0)
    user_count: Mapped[int] = mapped_column(Integer, default=0)
    collection_runs: Mapped[int] = mapped_column(Integer, default=0)
    api_requests: Mapped[int] = mapped_column(Integer, default=0)
    token_usage: Mapped[int] = mapped_column(Integer, default=0)
    cost_cny: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    export_count: Mapped[int] = mapped_column(Integer, default=0)
    storage_mb: Mapped[int] = mapped_column(Integer, default=0)


# ── UsageMeterDefinition ─────────────────────────────────────────────────────

class UsageMeterDefinition(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "usage_meter_definitions"
    __table_args__ = (
        UniqueConstraint("meter_key", "version", name="uq_meter_def_key_version"),
    )
    meter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    description: Mapped[str] = mapped_column(Text, default="")
    counting_rule_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    reset_period: Mapped[str] = mapped_column(String(20), default="monthly")
    is_billable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_customer_visible: Mapped[bool] = mapped_column(Boolean, default=True)


# ── PlanChangeRequest ────────────────────────────────────────────────────────

class PlanChangeRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "plan_change_requests"
    __table_args__ = (
        Index("ix_plan_change_org_status", "organization_id", "status"),
        Index("ix_plan_change_effective", "effective_at"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    current_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_definitions.id"), nullable=False)
    target_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plan_definitions.id"), nullable=False)
    target_plan_version: Mapped[str] = mapped_column(String(20), default="1.0")
    change_type: Mapped[str] = mapped_column(String(30), default="upgrade")
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="previewed")
    impact_preview_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── FeatureFlag ───────────────────────────────────────────────────────────────

class FeatureFlag(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "feature_flags"
    __table_args__ = (
        UniqueConstraint("key", name="uq_feature_flags_key"),
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    flag_type: Mapped[str] = mapped_column(String(30), default="beta_feature")
    default_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rollout_percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_plan_names: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class FeatureFlagOverride(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "feature_flag_overrides"
    __table_args__ = (
        UniqueConstraint("feature_flag_id", "organization_id",
                         name="uq_flag_override_org"),
    )
    feature_flag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feature_flags.id"), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── EmergencyPause ───────────────────────────────────────────────────────────

class EmergencyPause(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "emergency_pauses"
    __table_args__ = (
        Index("ix_epause_scope_status", "scope", "status"),
        Index("ix_epause_org", "organization_id"),
    )
    scope: Mapped[str] = mapped_column(String(30), default="global")
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    feature_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/resolved/expired
    reason: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(10), default="medium")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── PlatformAdminProfile ─────────────────────────────────────────────────────

class PlatformAdminProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "platform_admin_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    platform_role: Mapped[str] = mapped_column(String(30), default="system_admin")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/suspended/revoked
    mfa_enforced: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── PlatformAccessSession ────────────────────────────────────────────────────

class PlatformAccessSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "platform_access_sessions"
    __table_args__ = (
        Index("ix_pas_user_status", "platform_user_id", "status"),
        Index("ix_pas_target_org", "target_organization_id"),
    )
    platform_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    access_type: Mapped[str] = mapped_column(String(30), default="governance")  # governance/support_debug
    reason: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(30), default="read_only")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/expired/revoked
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── PlatformApprovalRequest ──────────────────────────────────────────────────

class PlatformApprovalRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "platform_approval_requests"
    __table_args__ = (
        Index("ix_par_requested_by", "requested_by", "status"),
        Index("ix_par_resource", "resource_type", "resource_id"),
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(10), default="medium")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)


# ── AuditIntegrityCheck ──────────────────────────────────────────────────────

class AuditIntegrityCheck(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "audit_integrity_checks"
    scope: Mapped[str] = mapped_column(String(20), default="organization")  # organization/platform
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="passed")  # passed/failed
    failed_at_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True)
    details_json: Mapped[dict] = mapped_column(JSONB, default=dict)


# ── RateLimitPolicy ──────────────────────────────────────────────────────────

class RateLimitPolicy(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "rate_limit_policies"
    __table_args__ = (
        UniqueConstraint("key", name="uq_rl_policy_key"),
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), default="organization")
    limit: Mapped[int] = mapped_column(Integer, default=100)
    window_seconds: Mapped[int] = mapped_column(Integer, default=60)
    burst: Mapped[int | None] = mapped_column(Integer, nullable=True)
