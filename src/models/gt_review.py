import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin


class GroundTruthReview(Base, UUIDMixin):
    __tablename__ = "gt_reviews"
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gt_candidates.id"), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    field_changes_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())
