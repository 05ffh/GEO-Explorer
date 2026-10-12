"""add search_results raw_content

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-14

正文分层（2026-09-14）：content_text = 过滤后基准事实（下游消费）；raw_content = 抓取的页面原文
（重处理原料，不对下游暴露，过滤规则升级时重跑）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('search_results', sa.Column('raw_content', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('search_results', 'raw_content')
