"""P1-4: Change brand_directed from Boolean to Float (5-level scale).

Revision ID: a1b2c3d4e5f6
Revises: 89abc123def4
Create Date: 2026-06-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "89abc123def4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE query_templates ALTER COLUMN brand_directed DROP DEFAULT")
    op.execute(
        "ALTER TABLE query_templates ALTER COLUMN brand_directed "
        "TYPE DOUBLE PRECISION USING CASE WHEN brand_directed THEN 1.0 ELSE 0.0 END"
    )
    op.execute("ALTER TABLE query_templates ALTER COLUMN brand_directed SET DEFAULT 1.0")


def downgrade() -> None:
    op.execute("ALTER TABLE query_templates ALTER COLUMN brand_directed DROP DEFAULT")
    op.execute(
        "ALTER TABLE query_templates ALTER COLUMN brand_directed "
        "TYPE BOOLEAN USING brand_directed >= 0.5"
    )
    op.execute("ALTER TABLE query_templates ALTER COLUMN brand_directed SET DEFAULT true")
