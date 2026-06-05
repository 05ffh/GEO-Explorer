"""P2-4: Append-only audit log for hallucination human review actions."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin


class HallucinationReviewLog(Base, UUIDMixin):
    """Immutable audit log — insert only, never update."""
    __tablename__ = "hallucination_review_logs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    hallucination_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hallucination_results.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    query_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("query_results.id"), nullable=True)

    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # claimed/completed/skipped/reopened/released

    old_review_status: Mapped[str] = mapped_column(String(20), default="")
    new_review_status: Mapped[str] = mapped_column(String(20), default="")
    old_verdict: Mapped[str] = mapped_column(String(50), default="")
    new_verdict: Mapped[str] = mapped_column(String(50), default="")
    old_severity: Mapped[str] = mapped_column(String(10), default="")
    new_severity: Mapped[str] = mapped_column(String(10), default="")
    old_claim_nature: Mapped[str] = mapped_column(String(20), default="")
    new_claim_nature: Mapped[str] = mapped_column(String(20), default="")
    old_evidence_strength: Mapped[str] = mapped_column(String(30), default="")
    new_evidence_strength: Mapped[str] = mapped_column(String(30), default="")

    review_decision: Mapped[str] = mapped_column(String(50), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    corrected_value: Mapped[str] = mapped_column(Text, default="")

    snapshot_before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    snapshot_after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feedback_generated_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
