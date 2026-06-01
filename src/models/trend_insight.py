"""GEO Explorer — Trend Insight & related models (P2-2)."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class TrendAnalysisDefinition(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trend_analysis_definitions"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    sampling_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    quality_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    cliff_detection_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    sustained_trend_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    stability_score_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    change_scope_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    dedupe_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    resolved_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TrendInsight(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "trend_insights"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    insight_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    insight_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # cliff_drop / sustained_improvement / sustained_decline / platform_shift /
    # model_update_impact / anomaly / stability_assessment
    kpi_key: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")  # info/warning/critical
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    # open / acknowledged / resolved / dismissed / superseded
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # customer language
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    sample_point_count: Mapped[int] = mapped_column(Integer, default=0)
    required_point_count: Mapped[int] = mapped_column(Integer, default=6)
    data_coverage_ratio: Mapped[float] = mapped_column(Float, default=1.0)
    data_quality_level: Mapped[str] = mapped_column(String(20), default="medium")
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    confidence_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_scope: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_strength: Mapped[str] = mapped_column(String(20), default="moderate")
    evidence_strength_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Algorithm binding
    analysis_definition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trend_analysis_definitions.id"), nullable=True)
    analysis_definition_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    definition_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(20), default="1.0")
    # Timing
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Governance
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trend_insights.id"), nullable=True)
    parent_insight_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trend_insights.id"), nullable=True)


class TrendInsightEvent(Base, UUIDMixin):
    __tablename__ = "trend_insight_events"
    trend_insight_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trend_insights.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # detected/updated/severity_upgraded/acknowledged/dismissed/resolved/reopened/superseded
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    old_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PlatformTrendIncident(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "platform_trend_incidents"
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    kpi_key: Mapped[str] = mapped_column(String(50), nullable=False)
    incident_type: Mapped[str] = mapped_column(String(50), nullable=False)
    affected_brand_count: Mapped[int] = mapped_column(Integer, default=0)
    affected_industry_count: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")


class ImpactEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "impact_events"
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_events"
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    event_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    affected_region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    affected_model_version_before: Mapped[str | None] = mapped_column(String(50), nullable=True)
    affected_model_version_after: Mapped[str | None] = mapped_column(String(50), nullable=True)
    impact_scope: Mapped[str] = mapped_column(String(50), default="unknown")
    source: Mapped[str] = mapped_column(String(50), default="observed")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
