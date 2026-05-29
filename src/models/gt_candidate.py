import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class GroundTruthCandidate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "gt_candidates"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    candidate_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    overall_confidence: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
