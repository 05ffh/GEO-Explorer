import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class HallucinationResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "hallucination_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False, index=True)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_level: Mapped[str] = mapped_column(String(10), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="P1")
    verdict: Mapped[str] = mapped_column(String(50), default="uncertain")
    ai_claim: Mapped[str] = mapped_column(Text, default="")
    ground_truth_value: Mapped[str] = mapped_column(Text, default="")
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_reviewed: Mapped[bool] = mapped_column(default=False)
    human_verdict: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
