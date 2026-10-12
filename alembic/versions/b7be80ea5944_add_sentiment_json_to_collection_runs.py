"""add sentiment_json to collection_runs

Revision ID: b7be80ea5944
Revises: ff2b179b9edd
Create Date: 2026-08-27 14:06:03.074184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7be80ea5944'
down_revision: Union[str, Sequence[str], None] = 'ff2b179b9edd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 先带 server_default 回填现有行 {}, 再摘掉默认值，与模型 default=dict（无 server_default）对齐
    op.add_column('collection_runs', sa.Column('sentiment_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.alter_column('collection_runs', 'sentiment_json', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('collection_runs', 'sentiment_json')
