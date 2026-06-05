import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin


class GroundTruthEvidence(Base, UUIDMixin):
    __tablename__ = "gt_evidences"
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gt_candidates.id"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    source_tier: Mapped[str] = mapped_column(String(10), default="C")  # S/A/B/C/D
    source_quality: Mapped[str] = mapped_column(String(20), default="low")
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/reviewed/flagged
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
