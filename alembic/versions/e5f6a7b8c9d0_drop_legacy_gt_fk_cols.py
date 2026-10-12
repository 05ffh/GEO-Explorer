"""drop residual legacy GT FK columns

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-16

删旧 GT 表（d4e5f6a7b8c9）后残留的 3 处 GT 外键列（旧系统死表，新系统不用）：
api_usage_logs.gt_candidate_id / metrics_snapshots.ground_truth_version_id /
hallucination_results.ground_truth_version_id。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = [
    ('api_usage_logs', 'gt_candidate_id'),
    ('metrics_snapshots', 'ground_truth_version_id'),
    ('hallucination_results', 'ground_truth_version_id'),
    ('diagnostic_runs', 'gt_candidate_id'),
]


def upgrade() -> None:
    for tbl, col in _COLS:
        op.execute(f'ALTER TABLE {tbl} DROP COLUMN IF EXISTS {col} CASCADE')


def downgrade() -> None:
    for tbl, col in _COLS:
        op.add_column(tbl, sa.Column(col, postgresql.UUID(as_uuid=True), nullable=True))
