"""P2-4: Feedback models — GT update candidates + review feedback items."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin


class GTUpdateCandidate(Base, UUIDMixin):
    """GT field update proposal from human review — does NOT auto-modify GT."""
    __tablename__ = "gt_update_candidates"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_gt_value: Mapped[str] = mapped_column(Text, default="")
    proposed_value: Mapped[str] = mapped_column(Text, default="")
    corrected_value: Mapped[str] = mapped_column(Text, default="")
    source_hallucination_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hallucination_results.id"), nullable=True)
    source_review_log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hallucination_review_logs.id"), nullable=True)
    evidence_required: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/rejected/applied
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ReviewFeedbackItem(Base, UUIDMixin):
    """Actionable feedback item from human review — GT / template / detector."""
    __tablename__ = "review_feedback_items"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)  # gt_update/template_fix/detector_calibration
    source_review_log_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source_hallucination_result_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("query_templates.id"), nullable=True)
    question_type: Mapped[str] = mapped_column(String(50), default="")
    field_name: Mapped[str] = mapped_column(String(100), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/rejected/applied
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
