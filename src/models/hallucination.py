import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class HallucinationResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "hallucination_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True, index=True)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_level: Mapped[str] = mapped_column(String(10), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="P1")
    verdict: Mapped[str] = mapped_column(String(50), default="ambiguous")
    error_type: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    ai_claim: Mapped[str] = mapped_column(Text, default="")
    ground_truth_value: Mapped[str] = mapped_column(Text, default="")
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_reviewed: Mapped[bool] = mapped_column(default=False)
    human_verdict: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    claim_text: Mapped[str] = mapped_column(Text, default="")
    subject_type: Mapped[str] = mapped_column(String(50), default="")
    matched_gt_field: Mapped[str] = mapped_column(String(100), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)

    # P2-1: claim nature taxonomy
    claim_type: Mapped[str] = mapped_column(String(20), default="unknown", server_default="unknown")
    predicate_type: Mapped[str] = mapped_column(String(30), default="other", server_default="other")

    # P2-2: multi-evidence consensus
    evidence_consensus_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # P2-4: human review closed loop
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    review_notes: Mapped[str] = mapped_column(Text, default="")
    corrected_value: Mapped[str] = mapped_column(Text, default="")
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_priority: Mapped[str] = mapped_column(String(10), default="medium")
    review_reason: Mapped[str] = mapped_column(String(50), default="")
    review_decision: Mapped[str] = mapped_column(String(50), default="")

    # P1-8: reclassification tracking
    source_query_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("query_results.id"), nullable=True)
    source_hallucination_result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hallucination_results.id"), nullable=True)
    reclassification_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hallucination_results.id"), nullable=True)
    result_origin: Mapped[str] = mapped_column(String(32), default="original")
    reclassification_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reclassification_runs.id"), nullable=True)
    is_current_reclassification: Mapped[bool] = mapped_column(Boolean, default=False)
