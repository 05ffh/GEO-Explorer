"""add measurement_snapshots (测量版本快照)

Revision ID: a5f6b7c8d9e0
Revises: e2c7e88014fd
Create Date: 2026-08-31

快照表承载测量版本历史：每次采集（全量 full / 补测 remeasure）一条快照，
回填（complete_measure）不新增版本，只修订最新快照的 measurement_json + backfilled_at。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a5f6b7c8d9e0'
down_revision: Union[str, Sequence[str], None] = 'e2c7e88014fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'measurement_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('collection_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_no', sa.Integer(), nullable=False),
        sa.Column('snapshot_type', sa.String(length=20), nullable=False),
        sa.Column('collected_at', sa.String(length=40), nullable=False),
        sa.Column('measurement_json', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('backfilled_at', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['collection_run_id'], ['collection_runs.id']),
    )
    op.create_index('ix_measurement_snapshots_collection_run_id', 'measurement_snapshots', ['collection_run_id'])


def downgrade() -> None:
    op.drop_index('ix_measurement_snapshots_collection_run_id', table_name='measurement_snapshots')
    op.drop_table('measurement_snapshots')
