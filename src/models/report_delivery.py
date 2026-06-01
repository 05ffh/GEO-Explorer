"""GEO Explorer — Report productization models (P2-3)."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Boolean, Text, DateTime, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class ReportBranding(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_brandings"
    scope: Mapped[str] = mapped_column(String(20), default="brand")  # platform/organization/brand
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Visuals
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), default="#1E40AF")
    accent_color: Mapped[str] = mapped_column(String(7), default="#3B82F6")
    font_heading: Mapped[str] = mapped_column(String(100), default="Fira Sans")
    font_body: Mapped[str] = mapped_column(String(100), default="Fira Sans")
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name_display: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hide_geo_branding: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReportSchedule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_schedules"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    editions: Mapped[list] = mapped_column(JSONB, default=["executive", "customer"])
    formats: Mapped[list] = mapped_column(JSONB, default=["pdf"])
    frequency: Mapped[str] = mapped_column(String(30), default="monthly")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai")
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    day_of_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    only_if_new_collection: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReportScheduleRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_schedule_runs"
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_schedules.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    period_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="triggered")
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_ids: Mapped[list] = mapped_column(JSONB, default=list)
    delivery_attempt_ids: Mapped[list] = mapped_column(JSONB, default=list)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReportSubscription(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_subscriptions"
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_schedules.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(30), default="internal_user")
    recipient_user_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    external_recipients: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribe_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    delivery_method: Mapped[str] = mapped_column(String(30), default="email")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


class ReportDeliveryAttempt(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_delivery_attempts"
    report_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_artifacts.id"), nullable=False, index=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_schedules.id"), nullable=True)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_subscriptions.id"), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    delivery_method: Mapped[str] = mapped_column(String(30), default="email")
    delivery_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    recipient: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    force_resend: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportDownloadLink(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_download_links"
    report_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_artifacts.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    access_scope: Mapped[str] = mapped_column(String(20), default="internal")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class ReportDownloadEvent(Base, UUIDMixin):
    __tablename__ = "report_download_events"
    report_artifact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_artifacts.id"), nullable=False)
    download_link_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_download_links.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    access_scope: Mapped[str] = mapped_column(String(20), default="internal")
    ip_address_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="success")
    downloaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReportBatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_batches"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    brand_ids: Mapped[list] = mapped_column(JSONB, default=list)
    editions: Mapped[list] = mapped_column(JSONB, default=list)
    formats: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=3)
    estimated_artifact_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
