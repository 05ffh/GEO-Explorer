"""add cdp_facts_json to collection_runs

Revision ID: b8c9d0e1f2a3
Revises: f6a7b8c9d0e1
Create Date: 2026-10-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 先带 server_default 回填现有行 {}, 再摘掉默认值，与模型 default=dict 对齐
    op.add_column('collection_runs', sa.Column('cdp_facts_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.alter_column('collection_runs', 'cdp_facts_json', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('collection_runs', 'cdp_facts_json')
