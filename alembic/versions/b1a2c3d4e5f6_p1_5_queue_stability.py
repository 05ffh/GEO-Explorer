"""p1_5_queue_stability

Revision ID: b1a2c3d4e5f6
Revises: 3ed036d3c68b
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3ed036d3c68b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TaskState
    op.create_table(
        'task_states',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('celery_task_id', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('root_task_id', sa.String(255), nullable=True, index=True),
        sa.Column('parent_task_state_id', postgresql.UUID, nullable=True),
        sa.Column('task_name', sa.String(255), nullable=False, index=True),
        sa.Column('queue_name', sa.String(100), server_default='geo_default', nullable=False),
        sa.Column('routing_key', sa.String(100), server_default='default', nullable=False),
        sa.Column('priority', sa.Integer(), server_default='5', nullable=False),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True, index=True),
        sa.Column('collection_run_id', postgresql.UUID, sa.ForeignKey("collection_runs.id"), nullable=True),
        sa.Column('operation_type', sa.String(50), server_default='', nullable=False),
        sa.Column('trigger_type', sa.String(50), server_default='manual', nullable=False),
        sa.Column('args_json', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('kwargs_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('payload_hash', sa.String(64), server_default='', nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=True, index=True),
        sa.Column('idempotency_acquired_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('idempotency_ttl', sa.Integer(), server_default='3600', nullable=False),
        sa.Column('execution_lock_owner', sa.String(255), nullable=True),
        sa.Column('execution_lock_acquired_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('execution_lock_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(30), server_default='queued', nullable=False, index=True),
        sa.Column('version', sa.Integer(), server_default='0', nullable=False),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_retries', sa.Integer(), server_default='3', nullable=False),
        sa.Column('progress', sa.Float(), server_default='0', nullable=False),
        sa.Column('progress_message', sa.String(500), server_default='', nullable=False),
        sa.Column('last_progress_update_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timeout_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_json', postgresql.JSONB, nullable=True),
        sa.Column('error_type', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_traceback', sa.Text(), nullable=True),
        sa.Column('dlq_reason', sa.String(500), nullable=True),
        sa.Column('dlq_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dlq_retry_policy', sa.String(20), nullable=True),
        sa.Column('dlq_requeue_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('dlq_max_requeues', sa.Integer(), server_default='3', nullable=False),
        sa.Column('dlq_backoff_seconds', sa.Integer(), server_default='300', nullable=False),
        sa.Column('next_requeue_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('control_action', sa.String(20), nullable=True),
        sa.Column('requested_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # TaskEvent
    op.create_table(
        'task_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('task_state_id', postgresql.UUID, sa.ForeignKey("task_states.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('old_status', sa.String(30), nullable=True),
        sa.Column('new_status', sa.String(30), nullable=True),
        sa.Column('message', sa.Text(), server_default='', nullable=False),
        sa.Column('metadata_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # QueueAlert
    op.create_table(
        'queue_alerts',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column('queue_name', sa.String(100), nullable=True),
        sa.Column('platform', sa.String(50), nullable=True),
        sa.Column('alert_type', sa.String(50), nullable=False, index=True),
        sa.Column('severity', sa.String(20), server_default='warning', nullable=False),
        sa.Column('current_value', sa.Float(), nullable=True),
        sa.Column('threshold', sa.Float(), nullable=True),
        sa.Column('message', sa.Text(), server_default='', nullable=False),
        sa.Column('status', sa.String(20), server_default='open', nullable=False, index=True),
        sa.Column('dedupe_key', sa.String(255), unique=True, nullable=False),
        sa.Column('acknowledged_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('queue_alerts')
    op.drop_table('task_events')
    op.drop_table('task_states')
