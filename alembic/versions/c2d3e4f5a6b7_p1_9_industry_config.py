"""P1-9: Industry adaptation layer — extended tables and seed data.

Revision ID: c2d3e4f5a6b7
Revises: a0b1c2d3e4f5
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "a0b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend industry_templates with config fields
    op.add_column("industry_templates",
                  sa.Column("hallucination_thresholds", postgresql.JSONB,
                            server_default=text("'{}'::jsonb"), nullable=False))
    op.add_column("industry_templates",
                  sa.Column("template_strategy", postgresql.JSONB,
                            server_default=text("'{}'::jsonb"), nullable=False))
    op.add_column("industry_templates",
                  sa.Column("config_version", sa.Integer(), server_default="1", nullable=False))

    # 2. Extend brands with industry fields
    op.add_column("brands",
                  sa.Column("industry_template_id", postgresql.UUID,
                            sa.ForeignKey("industry_templates.id"), nullable=True))
    op.add_column("brands",
                  sa.Column("industry_detection_status", sa.String(32),
                            server_default="unset", nullable=False))
    op.add_column("brands",
                  sa.Column("industry_detection_confidence", sa.Float(), nullable=True))
    op.add_column("brands",
                  sa.Column("industry_detection_evidence_json", postgresql.JSONB,
                            server_default=text("'{}'::jsonb"), nullable=False))
    op.add_column("brands",
                  sa.Column("industry_confirmed_by", postgresql.UUID,
                            sa.ForeignKey("users.id"), nullable=True))
    op.add_column("brands",
                  sa.Column("industry_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("brands",
                  sa.Column("industry_config_override", postgresql.JSONB, nullable=True))

    # 3. Extend collection_runs
    op.add_column("collection_runs",
                  sa.Column("industry_config_snapshot_json", postgresql.JSONB, nullable=True))
    op.add_column("collection_runs",
                  sa.Column("template_selection_summary_json", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("collection_runs", "template_selection_summary_json")
    op.drop_column("collection_runs", "industry_config_snapshot_json")
    op.drop_column("brands", "industry_config_override")
    op.drop_column("brands", "industry_confirmed_at")
    op.drop_column("brands", "industry_confirmed_by")
    op.drop_column("brands", "industry_detection_evidence_json")
    op.drop_column("brands", "industry_detection_confidence")
    op.drop_column("brands", "industry_detection_status")
    op.drop_column("brands", "industry_template_id")
    op.drop_column("industry_templates", "config_version")
    op.drop_column("industry_templates", "template_strategy")
    op.drop_column("industry_templates", "hallucination_thresholds")
