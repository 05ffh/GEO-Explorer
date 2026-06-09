"""add execution_mode to collection_runs

Revision ID: p7q8r9s0t1u2
Revises: j1k2l3m4n5o6
Create Date: 2026-06-09
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'p7q8r9s0t1u2'
down_revision: Union[str, None] = 'j1k2l3m4n5o6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('collection_runs', sa.Column('execution_mode', sa.String(20), nullable=False, server_default='celery'))


def downgrade() -> None:
    op.drop_column('collection_runs', 'execution_mode')
