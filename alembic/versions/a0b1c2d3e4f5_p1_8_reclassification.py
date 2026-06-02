"""P1-8: Historical reclassification — reclassification_runs table, extended models.

Revision ID: a0b1c2d3e4f5
Revises: e9f0a1b2c3d4
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create reclassification_runs table
    op.create_table(
        "reclassification_runs",
        sa.Column("id", postgresql.UUID, primary_key=True),
        sa.Column("organization_id", postgresql.UUID,
                  sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("brand_id", postgresql.UUID,
                  sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("from_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("to_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column("mode", sa.String(32), server_default="dry_run", nullable=False),
        sa.Column("trigger_source", sa.String(32), server_default="manual", nullable=False),
        # version钉定
        sa.Column("detector_version", sa.String(64), server_default="p0-7-v1", nullable=False),
        sa.Column("quality_schema_version", sa.String(64), server_default="template_health_v1", nullable=False),
        sa.Column("metric_mapping_version", sa.String(64), nullable=True),
        sa.Column("gt_schema_version", sa.String(64), nullable=True),
        sa.Column("gt_version_strategy", sa.String(32), server_default="latest_active", nullable=False),
        sa.Column("detector_config_hash", sa.String(64), nullable=True),
        # counts
        sa.Column("eligible_runs_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runs_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runs_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("query_results_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hallucination_results_created", sa.Integer(), server_default="0", nullable=False),
        # results
        sa.Column("classification_changes_json", postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column("error_summary_json", postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column("progress_json", postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column("sample_diffs_json", postgresql.JSONB, nullable=True),
        sa.Column("run_original_summaries_json", postgresql.JSONB, nullable=True),
        # state
        sa.Column("dry_run", sa.Boolean(), server_default=text("false"), nullable=False),
        sa.Column("official", sa.Boolean(), server_default=text("false"), nullable=False),
        sa.Column("superseded_by", postgresql.UUID,
                  sa.ForeignKey("reclassification_runs.id"), nullable=True),
        sa.Column("is_current_for_range", sa.Boolean(), server_default=text("false"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        # audit
        sa.Column("triggered_by", postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by", postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        # timestamps
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=text("now()"), nullable=False),
    )
    op.create_index("ix_rr_org_brand", "reclassification_runs", ["organization_id", "brand_id"])
    op.create_index("ix_rr_status", "reclassification_runs", ["status"])
    op.create_index("ix_rr_idempotency", "reclassification_runs", ["idempotency_key"], unique=True,
                    postgresql_where=text("idempotency_key IS NOT NULL"))
    # P0-8: prevent concurrent active runs
    op.create_index("ix_rr_active_lock", "reclassification_runs", ["organization_id", "brand_id"],
                    unique=True,
                    postgresql_where=text("status IN ('queued', 'running')"))

    # 2. Extend collection_runs
    op.add_column("collection_runs",
                  sa.Column("reclassified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("collection_runs",
                  sa.Column("latest_reclassification_run_id", postgresql.UUID,
                            sa.ForeignKey("reclassification_runs.id"), nullable=True))
    op.add_column("collection_runs",
                  sa.Column("original_report_quality_summary_json", postgresql.JSONB, nullable=True))
    op.add_column("collection_runs",
                  sa.Column("latest_reclassified_quality_summary_json", postgresql.JSONB, nullable=True))

    # 3. Extend hallucination_results
    op.add_column("hallucination_results",
                  sa.Column("source_query_result_id", postgresql.UUID,
                            sa.ForeignKey("query_results.id"), nullable=True))
    op.add_column("hallucination_results",
                  sa.Column("source_hallucination_result_id", postgresql.UUID,
                            sa.ForeignKey("hallucination_results.id"), nullable=True))
    op.add_column("hallucination_results",
                  sa.Column("reclassification_of", postgresql.UUID,
                            sa.ForeignKey("hallucination_results.id"), nullable=True))
    op.add_column("hallucination_results",
                  sa.Column("result_origin", sa.String(32), server_default="original", nullable=False))
    op.add_column("hallucination_results",
                  sa.Column("reclassification_run_id", postgresql.UUID,
                            sa.ForeignKey("reclassification_runs.id"), nullable=True))
    op.add_column("hallucination_results",
                  sa.Column("is_current_reclassification", sa.Boolean(),
                            server_default=text("false"), nullable=False))

    # 4. Backfill existing hallucination_results
    conn = op.get_bind()
    conn.execute(text(
        "UPDATE hallucination_results "
        "SET source_query_result_id = query_result_id, result_origin = 'original' "
        "WHERE result_origin = 'original' AND source_query_result_id IS NULL"
    ))


def downgrade() -> None:
    op.drop_column("hallucination_results", "is_current_reclassification")
    op.drop_column("hallucination_results", "reclassification_run_id")
    op.drop_column("hallucination_results", "result_origin")
    op.drop_column("hallucination_results", "reclassification_of")
    op.drop_column("hallucination_results", "source_hallucination_result_id")
    op.drop_column("hallucination_results", "source_query_result_id")
    op.drop_column("collection_runs", "latest_reclassified_quality_summary_json")
    op.drop_column("collection_runs", "original_report_quality_summary_json")
    op.drop_column("collection_runs", "latest_reclassification_run_id")
    op.drop_column("collection_runs", "reclassified_at")
    op.drop_index("ix_rr_active_lock", table_name="reclassification_runs",
                  postgresql_where=text("status IN ('queued', 'running')"))
    op.drop_index("ix_rr_idempotency", table_name="reclassification_runs",
                  postgresql_where=text("idempotency_key IS NOT NULL"))
    op.drop_index("ix_rr_status", table_name="reclassification_runs")
    op.drop_index("ix_rr_org_brand", table_name="reclassification_runs")
    op.drop_table("reclassification_runs")
