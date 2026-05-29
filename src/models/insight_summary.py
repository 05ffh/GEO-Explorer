import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class InsightSummary(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "insight_summaries"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False, index=True)
    platform_health_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    brand_performance_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    key_findings_json: Mapped[dict] = mapped_column(JSONB, default=list)
    data_reliability_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence_level: Mapped[str] = mapped_column(String(20), default="low")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())
