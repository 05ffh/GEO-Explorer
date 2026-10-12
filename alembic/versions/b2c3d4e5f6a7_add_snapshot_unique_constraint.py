"""add unique constraint on measurement_snapshots (collection_run_id, snapshot_no)

Revision ID: b2c3d4e5f6a7
Revises: a5f6b7c8d9e0
Create Date: 2026-08-31

数据库兜底：同一 run 的版本号（snapshot_no）必须唯一，拒绝并发/自动触发算出重复号。
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a5f6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_measurement_snapshot_run_no', 'measurement_snapshots',
        ['collection_run_id', 'snapshot_no'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_measurement_snapshot_run_no', 'measurement_snapshots', type_='unique')
