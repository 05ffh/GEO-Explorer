"""P1-1: Add gt_schema_version column to ground_truth_versions.

Revision ID: 89abc123def4
Revises: 700124a47f1c
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "89abc123def4"
down_revision: Union[str, None] = "700124a47f1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ground_truth_versions",
        sa.Column("gt_schema_version", sa.String(20), nullable=True),
    )
    op.create_index(
        "ix_gt_versions_schema_version",
        "ground_truth_versions",
        ["gt_schema_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_gt_versions_schema_version", table_name="ground_truth_versions")
    op.drop_column("ground_truth_versions", "gt_schema_version")
