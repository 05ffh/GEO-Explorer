"""add report_json to collection_runs

Revision ID: c9d0e1f2a3b4
Revises: a1b2c3d4e5f6
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 先带 server_default 回填现有行 {}, 再摘掉默认值，与模型 default=dict 对齐
    op.add_column('collection_runs', sa.Column('report_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.alter_column('collection_runs', 'report_json', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('collection_runs', 'report_json')
