"""GEO Explorer — Benchmark Snapshot (P2-1). Industry benchmark KPI percentiles."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class BenchmarkSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "benchmark_snapshots"

    # Industry binding
    industry_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    industry_template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("industry_templates.id"), nullable=True)
    industry_template_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    industry_domain: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="zh-CN")

    # Scope
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)  # None=global
    benchmark_scope: Mapped[str] = mapped_column(String(20), default="global")  # global | org

    # Sample quality
    sample_brand_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_run_count: Mapped[int] = mapped_column(Integer, default=0)
    kpi_sample_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    excluded_brand_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_reason_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    deduplicated_brand_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_demo_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_unconfirmed_industry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Period
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aggregation_strategy: Mapped[str] = mapped_column(String(30), default="latest")

    # KPI stats
    kpi_p50: Mapped[dict] = mapped_column(JSONB, default=dict)
    kpi_p25: Mapped[dict] = mapped_column(JSONB, default=dict)
    kpi_p75: Mapped[dict] = mapped_column(JSONB, default=dict)
    kpi_mean: Mapped[dict] = mapped_column(JSONB, default=dict)
    kpi_confidence_intervals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Quality
    quality_level: Mapped[str] = mapped_column(String(20), default="insufficient")
    # high | medium | low | insufficient
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    confidence_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_status: Mapped[str] = mapped_column(String(20), default="fresh")
    # fresh | stale | expired

    # Definition binding
    benchmark_definition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("benchmark_definitions.id"), nullable=True)
    benchmark_definition_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    definition_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Governance
    benchmark_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    status: Mapped[str] = mapped_column(String(20), default="computing", index=True)
    # computing | active | failed | superseded
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    computed_by_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("benchmark_snapshots.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
