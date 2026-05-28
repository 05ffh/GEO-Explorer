import uuid
from datetime import date
from sqlalchemy import String, ForeignKey, Integer, Float, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class MetricsSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "metrics_snapshots"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sov: Mapped[float] = mapped_column(Float, default=0.0)
    first_rec_rate: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy_rate: Mapped[float] = mapped_column(Float, default=0.0)
    completeness_rate: Mapped[float] = mapped_column(Float, default=0.0)
    citation_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
