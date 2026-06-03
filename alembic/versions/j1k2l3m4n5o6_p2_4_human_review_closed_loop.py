"""P2-4: Human Review Closed Loop — review fields, review log, feedback tables."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── HallucinationResult review fields ──────────────────────────────
    op.add_column("hallucination_results", sa.Column("review_status", sa.String(20), server_default="pending", nullable=False))
    op.add_column("hallucination_results", sa.Column("review_notes", sa.Text, server_default="", nullable=False))
    op.add_column("hallucination_results", sa.Column("corrected_value", sa.Text, server_default="", nullable=False))
    op.add_column("hallucination_results", sa.Column("claimed_by", UUID, nullable=True))
    op.add_column("hallucination_results", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hallucination_results", sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hallucination_results", sa.Column("review_priority", sa.String(10), server_default="medium", nullable=False))
    op.add_column("hallucination_results", sa.Column("review_reason", sa.String(50), server_default="", nullable=False))
    op.add_column("hallucination_results", sa.Column("review_decision", sa.String(50), server_default="", nullable=False))
    op.create_index("ix_hallucination_results_review_status", "hallucination_results", ["review_status"])
    op.create_index("ix_hallucination_results_review_priority", "hallucination_results", ["review_priority"])

    # ── HallucinationReviewLog ─────────────────────────────────────────
    op.create_table("hallucination_review_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("hallucination_result_id", UUID, nullable=False),
        sa.Column("collection_run_id", UUID, nullable=True),
        sa.Column("query_result_id", UUID, nullable=True),
        sa.Column("reviewer_id", UUID, nullable=True),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("old_review_status", sa.String(20), server_default=""),
        sa.Column("new_review_status", sa.String(20), server_default=""),
        sa.Column("old_verdict", sa.String(50), server_default=""),
        sa.Column("new_verdict", sa.String(50), server_default=""),
        sa.Column("old_severity", sa.String(10), server_default=""),
        sa.Column("new_severity", sa.String(10), server_default=""),
        sa.Column("old_claim_nature", sa.String(20), server_default=""),
        sa.Column("new_claim_nature", sa.String(20), server_default=""),
        sa.Column("old_evidence_strength", sa.String(30), server_default=""),
        sa.Column("new_evidence_strength", sa.String(30), server_default=""),
        sa.Column("review_decision", sa.String(50), server_default=""),
        sa.Column("notes", sa.Text, server_default=""),
        sa.Column("corrected_value", sa.Text, server_default=""),
        sa.Column("snapshot_before_json", JSONB, nullable=True),
        sa.Column("snapshot_after_json", JSONB, nullable=True),
        sa.Column("feedback_generated_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_review_logs_result_id", "hallucination_review_logs", ["hallucination_result_id"])
    op.create_index("ix_review_logs_action", "hallucination_review_logs", ["action"])

    # ── GTUpdateCandidate ──────────────────────────────────────────────
    op.create_table("gt_update_candidates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("brand_id", UUID, nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("current_gt_value", sa.Text, server_default=""),
        sa.Column("proposed_value", sa.Text, server_default=""),
        sa.Column("corrected_value", sa.Text, server_default=""),
        sa.Column("source_hallucination_result_id", UUID, nullable=True),
        sa.Column("source_review_log_id", UUID, nullable=True),
        sa.Column("evidence_required", sa.Boolean, server_default=sa.text("true")),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("reviewed_by", UUID, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gt_update_candidates_status", "gt_update_candidates", ["status"])

    # ── ReviewFeedbackItem ─────────────────────────────────────────────
    op.create_table("review_feedback_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("feedback_type", sa.String(30), nullable=False),
        sa.Column("source_review_log_ids", JSONB, nullable=True),
        sa.Column("source_hallucination_result_ids", JSONB, nullable=True),
        sa.Column("brand_id", UUID, nullable=True),
        sa.Column("template_id", UUID, nullable=True),
        sa.Column("question_type", sa.String(50), server_default=""),
        sa.Column("field_name", sa.String(100), server_default=""),
        sa.Column("summary", sa.Text, server_default=""),
        sa.Column("recommendation", sa.Text, server_default=""),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("priority", sa.String(10), server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_review_feedback_type", "review_feedback_items", ["feedback_type"])
    op.create_index("ix_review_feedback_status", "review_feedback_items", ["status"])


def downgrade() -> None:
    op.drop_table("review_feedback_items")
    op.drop_table("gt_update_candidates")
    op.drop_table("hallucination_review_logs")
    op.execute("DROP INDEX IF EXISTS ix_hallucination_results_review_priority")
    op.execute("DROP INDEX IF EXISTS ix_hallucination_results_review_status")
    op.drop_column("hallucination_results", "review_decision")
    op.drop_column("hallucination_results", "review_reason")
    op.drop_column("hallucination_results", "review_priority")
    op.drop_column("hallucination_results", "claim_expires_at")
    op.drop_column("hallucination_results", "claimed_at")
    op.drop_column("hallucination_results", "claimed_by")
    op.drop_column("hallucination_results", "corrected_value")
    op.drop_column("hallucination_results", "review_notes")
    op.drop_column("hallucination_results", "review_status")
