"""GEO Explorer — Publishing models (P2-4)."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Boolean, Text, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


# ── PublishTarget ─────────────────────────────────────────────────────────────

class PublishTarget(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "publish_targets"
    __table_args__ = (
        Index("ix_publish_targets_org_brand", "organization_id", "brand_id"),
        Index("ix_publish_targets_status_health", "status", "health_status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(255), default="")
    target_type: Mapped[str] = mapped_column(String(30), default="webhook")  # webhook/wordpress
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/inactive/invalid/archived
    health_status: Mapped[str] = mapped_column(String(20), default="healthy")

    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # none/bearer/basic/api_key/oauth
    auth_config_encrypted: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    webhook_secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    secret_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    credential_status: Mapped[str] = mapped_column(String(20), default="unknown")
    credential_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credential_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)

    cms_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    payload_version: Mapped[str] = mapped_column(String(20), default="2026-05")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    auto_publish_on_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_publish_max_risk_level: Mapped[str] = mapped_column(String(10), default="P2")
    auto_publish_target_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("publish_targets.id"), nullable=True)

    max_requests_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_concurrent_requests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    circuit_breaker_state: Mapped[str] = mapped_column(String(20), default="closed")

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_health_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── PublishBatch ──────────────────────────────────────────────────────────────

class PublishBatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "publish_batches"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_publish_batches_idempotency_key"),
        Index("ix_publish_batches_org_brand_cp", "organization_id", "brand_id", "content_package_id"),
        Index("ix_publish_batches_status", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    content_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("content_packages.id"), nullable=False)

    trigger_type: Mapped[str] = mapped_column(String(30), default="manual")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="queued")
    total_targets: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    cancelled_count: Mapped[int] = mapped_column(Integer, default=0)

    publish_request_ids: Mapped[list] = mapped_column(JSONB, default=list)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    orchestration_task_state_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── PublishRequest ────────────────────────────────────────────────────────────

PUBLISH_REQUEST_TRANSITIONS = {
    "queued": ["sending", "cancelled", "enqueue_failed"],
    "sending": ["delivered", "failed", "cancel_requested"],
    "cancel_requested": ["cancelled"],
    "delivered": ["acknowledged", "rejected", "delivered_no_callback", "published"],
    "acknowledged": ["draft_created", "published", "rejected"],
    "draft_created": ["published", "external_deleted"],
    "published": ["revoked", "archived"],
    "failed": ["queued"],
    "cancelled": [],
    "rejected": ["queued"],
    "revoked": [],
    "archived": [],
    "enqueue_failed": ["queued"],
    "delivered_no_callback": ["acknowledged", "published", "failed"],
    "unknown": ["failed", "sending"],
    "stale": [],
}


class PublishRequest(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "publish_requests"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_publish_requests_idempotency_key"),
        Index("ix_publish_requests_org_brand_cp", "organization_id", "brand_id", "content_package_id"),
        Index("ix_publish_requests_batch", "publish_batch_id"),
        Index("ix_publish_requests_target_status", "publish_target_id", "status"),
        Index("ix_publish_requests_status", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    content_package_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("content_packages.id"), nullable=False)
    publish_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_targets.id"), nullable=False)
    publish_batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_batches.id"), nullable=False)

    publish_action: Mapped[str] = mapped_column(String(30), default="create")
    trigger_type: Mapped[str] = mapped_column(String(30), default="manual")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), default="")

    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_for_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    force_republish: Mapped[bool] = mapped_column(Boolean, default=False)
    republish_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_publish_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("publish_requests.id"), nullable=True)

    task_state_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_edit_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_public_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── PublishAttempt ────────────────────────────────────────────────────────────

class PublishAttempt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "publish_attempts"
    __table_args__ = (
        Index("ix_publish_attempts_request", "publish_request_id"),
        Index("ix_publish_attempts_target", "publish_target_id"),
    )

    publish_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_requests.id"), nullable=False)
    publish_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_targets.id"), nullable=False)

    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    channel: Mapped[str] = mapped_column(String(30), default="webhook")
    status: Mapped[str] = mapped_column(String(20), default="sending")

    request_payload_hash: Mapped[str] = mapped_column(String(128), default="")
    payload_version: Mapped[str] = mapped_column(String(20), default="2026-05")

    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    task_state_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_edit_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_preview_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_public_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_status: Mapped[str | None] = mapped_column(String(30), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── PublishStatusCallback ─────────────────────────────────────────────────────

class PublishStatusCallback(Base, UUIDMixin):
    __tablename__ = "publish_status_callbacks"
    __table_args__ = (
        UniqueConstraint("callback_event_id", name="uq_publish_callbacks_event_id"),
        Index("ix_publish_callbacks_request", "publish_request_id"),
        Index("ix_publish_callbacks_target", "publish_target_id"),
        Index("ix_publish_callbacks_received_at", "received_at"),
    )

    publish_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_requests.id"), nullable=False)
    publish_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_targets.id"), nullable=False)

    callback_token_hash: Mapped[str] = mapped_column(String(128), default="")
    callback_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    callback_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    callback_signature_version: Mapped[str] = mapped_column(String(10), default="v1")
    callback_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    callback_token_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="received")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    signature_header: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    token_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    replay_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


# ── PublishEvent ──────────────────────────────────────────────────────────────

class PublishEvent(Base, UUIDMixin):
    __tablename__ = "publish_events"
    __table_args__ = (
        Index("ix_publish_events_batch", "publish_batch_id"),
        Index("ix_publish_events_request", "publish_request_id"),
        Index("ix_publish_events_type", "event_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    content_package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("content_packages.id"), nullable=True)
    publish_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("publish_batches.id"), nullable=True)
    publish_request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("publish_requests.id"), nullable=True)
    publish_attempt_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("publish_attempts.id"), nullable=True)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


# ── CMSFieldMapping ───────────────────────────────────────────────────────────

class CMSFieldMapping(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cms_field_mappings"
    __table_args__ = (
        UniqueConstraint("publish_target_id", "field_type", "local_value",
                         name="uq_cms_field_mappings_target_type_value"),
        Index("ix_cms_field_mappings_target_type", "publish_target_id", "field_type"),
    )

    publish_target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("publish_targets.id"), nullable=False)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)  # category/tag/custom_field
    local_value: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), default="")
    external_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
