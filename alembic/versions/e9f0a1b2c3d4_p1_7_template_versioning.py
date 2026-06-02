"""P1-7: QueryTemplate versioning — shadow table, version fields, v1 backfill.

Revision ID: e9f0a1b2c3d4
Revises: f8a7b6c5d4e3
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import text

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, None] = "f8a7b6c5d4e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create query_template_versions table
    op.create_table(
        "query_template_versions",
        sa.Column("id", postgresql.UUID, primary_key=True),
        sa.Column("template_id", postgresql.UUID,
                  sa.ForeignKey("query_templates.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("organization_id", postgresql.UUID,
                  sa.ForeignKey("organizations.id"), nullable=True),
        # versioned fields snapshot
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("question_type", sa.String(50), server_default="brand_definition", nullable=False),
        sa.Column("brand_directed", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("hallucination_check_enabled", sa.Boolean(), server_default=text("true"), nullable=False),
        sa.Column("template_level", sa.String(20), server_default="important", nullable=False),
        sa.Column("question_scope", sa.String(30), nullable=True),
        sa.Column("required_variables", postgresql.JSONB, server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column("applicable_industries", postgresql.JSONB, server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column("excluded_industries", postgresql.JSONB, server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column("metric_eligibility", postgresql.JSONB, server_default=text("'{}'::jsonb"), nullable=False),
        # version metadata
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("rollback_from_version", sa.Integer(), nullable=True),
        sa.Column("created_by", postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=text("now()"), nullable=False),
    )
    op.create_index("ix_qtv_template", "query_template_versions", ["template_id"])
    op.create_index("ix_qtv_template_version", "query_template_versions", ["template_id", "version"])
    op.create_index("ix_qtv_org", "query_template_versions", ["organization_id"])
    op.create_unique_constraint("uq_qtv_template_version", "query_template_versions", ["template_id", "version"])

    # 2. Add current_version to query_templates
    op.add_column("query_templates",
                  sa.Column("current_version", sa.Integer(), server_default="1", nullable=False))

    # 3. Add template_version_id to query_results (nullable, no backfill)
    op.add_column("query_results",
                  sa.Column("template_version_id", postgresql.UUID,
                            sa.ForeignKey("query_template_versions.id"), nullable=True))

    # 4. Add template_version_ids to collection_runs
    op.add_column("collection_runs",
                  sa.Column("template_version_ids", postgresql.JSONB,
                            server_default=text("'{}'::jsonb"), nullable=False))

    # 5. Backfill v1 for existing templates (idempotent — skips templates that already have v1)
    # Only backfill templates that are active and missing v1
    conn = op.get_bind()
    existing = conn.execute(
        text("SELECT DISTINCT template_id FROM query_template_versions WHERE version = 1")
    ).fetchall()
    existing_ids = {row[0] for row in existing}

    templates = conn.execute(text("""
        SELECT qt.id, qt.dimension, qt.template_text, qt.priority, qt.question_type,
               qt.brand_directed, qt.hallucination_check_enabled,
               qt.template_level, qt.question_scope,
               qt.organization_id, qt.created_by
        FROM query_templates qt
        WHERE qt.is_active = TRUE AND qt.id != ALL(:existing)
    """), {"existing": list(existing_ids) if existing_ids else ["00000000-0000-0000-0000-000000000000"]}).fetchall()

    for t in templates:
        import uuid
        conn.execute(text("""
            INSERT INTO query_template_versions
                (id, template_id, version, organization_id,
                 dimension, template_text, priority, question_type,
                 brand_directed, hallucination_check_enabled,
                 template_level, question_scope,
                 change_type, created_by, created_at)
            VALUES
                (:id, :template_id, 1, :organization_id,
                 :dimension, :template_text, :priority, :question_type,
                 :brand_directed, :hallucination_check_enabled,
                 :template_level, :question_scope,
                 'create', :created_by, now())
        """), {
            "id": uuid.uuid4(),
            "template_id": t.id,
            "organization_id": t.organization_id,
            "dimension": t.dimension,
            "template_text": t.template_text,
            "priority": t.priority,
            "question_type": t.question_type,
            "brand_directed": t.brand_directed,
            "hallucination_check_enabled": t.hallucination_check_enabled,
            "template_level": t.template_level,
            "question_scope": t.question_scope,
            "created_by": t.created_by,
        })


def downgrade() -> None:
    op.drop_column("collection_runs", "template_version_ids")
    op.drop_column("query_results", "template_version_id")
    op.drop_column("query_templates", "current_version")
    op.drop_index("ix_qtv_org", table_name="query_template_versions")
    op.drop_index("ix_qtv_template_version", table_name="query_template_versions")
    op.drop_index("ix_qtv_template", table_name="query_template_versions")
    op.drop_constraint("uq_qtv_template_version", "query_template_versions")
    op.drop_table("query_template_versions")
