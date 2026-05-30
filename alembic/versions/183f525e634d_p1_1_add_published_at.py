"""p1_1_add_published_at

Revision ID: 183f525e634d
Revises: 84ee2d3cb711
Create Date: 2026-05-30 14:44:40.235815

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '183f525e634d'
down_revision: Union[str, Sequence[str], None] = '84ee2d3cb711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('content_packages', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('content_packages', sa.Column('published_platform', sa.String(50), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('content_packages', 'published_platform')
    op.drop_column('content_packages', 'published_at')
