"""add search_results.content_layer

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-17

架构改造（2026-09-17 用户拍板）：content_text 只存「甲方真实可信可用的事实」。
显式分层标记 content_layer：
  - fact    = 官网资料页 + OTA 资料区（概览/房间/设施/政策）→ content_text 事实库
  - opinion = UGC 页 + OTA 点评区（住客评价）→ content_text 置空，原文存 raw_content
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('search_results',
                  sa.Column('content_layer', sa.String(20), nullable=False, server_default='fact'))


def downgrade() -> None:
    op.drop_column('search_results', 'content_layer')
