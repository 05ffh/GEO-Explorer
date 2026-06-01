"""GEO Explorer — Gap Attribution Result (P2-1). Persisted gap analysis between brand and competitors/benchmark."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class GapAttributionResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "gap_attribution_results"

    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    benchmark_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("benchmark_snapshots.id"), nullable=True)
    competitor_set_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("competitor_sets.id"), nullable=True)
    competitor_set_version: Mapped[int] = mapped_column(Integer, default=1)
    metrics_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("metrics_snapshots.id"), nullable=True)
    kpi_key: Mapped[str] = mapped_column(String(50), nullable=False)

    gap_magnitude: Mapped[float] = mapped_column(Float, default=0.0)
    gap_significance: Mapped[str] = mapped_column(String(20), default="none")
    # none | small | moderate | large
    materiality_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Full GapAttributionResult dict: likely_drivers, evidence_blocks, counter_evidence, caveat, by_platform, by_scenario, by_dimension

    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # active | stale | failed
    generated_by_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
