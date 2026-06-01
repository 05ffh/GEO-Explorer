"""p2_4_publishing

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PublishTarget
    op.create_table('publish_targets',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True),
        sa.Column('name', sa.String(255), server_default='', nullable=False),
        sa.Column('target_type', sa.String(30), server_default='webhook', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('health_status', sa.String(20), server_default='healthy', nullable=False),
        sa.Column('endpoint_url', sa.String(500), nullable=True),
        sa.Column('auth_type', sa.String(30), nullable=True),
        sa.Column('auth_config_encrypted', postgresql.JSONB, nullable=True),
        sa.Column('webhook_secret_hash', sa.String(128), nullable=True),
        sa.Column('previous_secret_hash', sa.String(128), nullable=True),
        sa.Column('secret_rotated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('credential_status', sa.String(20), server_default='unknown', nullable=False),
        sa.Column('credential_last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('credential_error_code', sa.String(100), nullable=True),
        sa.Column('cms_config', postgresql.JSONB, nullable=True),
        sa.Column('payload_version', sa.String(20), server_default='2026-05', nullable=False),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('auto_publish_on_approved', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('auto_publish_max_risk_level', sa.String(10), server_default='P2', nullable=False),
        sa.Column('auto_publish_target_id', postgresql.UUID, sa.ForeignKey("publish_targets.id"), nullable=True),
        sa.Column('max_requests_per_minute', sa.Integer(), nullable=True),
        sa.Column('max_concurrent_requests', sa.Integer(), nullable=True),
        sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('circuit_breaker_state', sa.String(20), server_default='closed', nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_health_change_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('health_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_publish_targets_org_brand', 'publish_targets', ['organization_id', 'brand_id'])
    op.create_index('ix_publish_targets_status_health', 'publish_targets', ['status', 'health_status'])

    # PublishBatch
    op.create_table('publish_batches',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False),
        sa.Column('content_package_id', postgresql.UUID, sa.ForeignKey("content_packages.id"), nullable=False),
        sa.Column('trigger_type', sa.String(30), server_default='manual', nullable=False),
        sa.Column('requested_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('status', sa.String(30), server_default='queued', nullable=False),
        sa.Column('total_targets', sa.Integer(), server_default='0', nullable=False),
        sa.Column('success_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cancelled_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('publish_request_ids', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=False),
        sa.Column('orchestration_task_state_id', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_publish_batches_idempotency_key', 'publish_batches', ['idempotency_key'])
    op.create_index('ix_publish_batches_org_brand_cp', 'publish_batches', ['organization_id', 'brand_id', 'content_package_id'])
    op.create_index('ix_publish_batches_status', 'publish_batches', ['status'])

    # PublishRequest
    op.create_table('publish_requests',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False),
        sa.Column('content_package_id', postgresql.UUID, sa.ForeignKey("content_packages.id"), nullable=False),
        sa.Column('publish_target_id', postgresql.UUID, sa.ForeignKey("publish_targets.id"), nullable=False),
        sa.Column('publish_batch_id', postgresql.UUID, sa.ForeignKey("publish_batches.id"), nullable=False),
        sa.Column('publish_action', sa.String(30), server_default='create', nullable=False),
        sa.Column('trigger_type', sa.String(30), server_default='manual', nullable=False),
        sa.Column('requested_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('status', sa.String(30), server_default='queued', nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=False),
        sa.Column('payload_hash', sa.String(128), server_default='', nullable=False),
        sa.Column('review_required', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('approved_for_publish', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('force_republish', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('republish_reason', sa.Text(), nullable=True),
        sa.Column('parent_publish_request_id', postgresql.UUID, sa.ForeignKey("publish_requests.id"), nullable=True),
        sa.Column('task_state_id', sa.String(255), nullable=True),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('external_edit_url', sa.String(500), nullable=True),
        sa.Column('external_preview_url', sa.String(500), nullable=True),
        sa.Column('external_public_url', sa.String(500), nullable=True),
        sa.Column('external_status', sa.String(30), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_publish_requests_idempotency_key', 'publish_requests', ['idempotency_key'])
    op.create_index('ix_publish_requests_org_brand_cp', 'publish_requests', ['organization_id', 'brand_id', 'content_package_id'])
    op.create_index('ix_publish_requests_batch', 'publish_requests', ['publish_batch_id'])
    op.create_index('ix_publish_requests_target_status', 'publish_requests', ['publish_target_id', 'status'])
    op.create_index('ix_publish_requests_status', 'publish_requests', ['status'])

    # PublishAttempt
    op.create_table('publish_attempts',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('publish_request_id', postgresql.UUID, sa.ForeignKey("publish_requests.id"), nullable=False),
        sa.Column('publish_target_id', postgresql.UUID, sa.ForeignKey("publish_targets.id"), nullable=False),
        sa.Column('attempt_no', sa.Integer(), server_default='1', nullable=False),
        sa.Column('channel', sa.String(30), server_default='webhook', nullable=False),
        sa.Column('status', sa.String(20), server_default='sending', nullable=False),
        sa.Column('request_payload_hash', sa.String(128), server_default='', nullable=False),
        sa.Column('payload_version', sa.String(20), server_default='2026-05', nullable=False),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body_summary', sa.Text(), nullable=True),
        sa.Column('task_state_id', sa.String(255), nullable=True),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('external_edit_url', sa.String(500), nullable=True),
        sa.Column('external_preview_url', sa.String(500), nullable=True),
        sa.Column('external_public_url', sa.String(500), nullable=True),
        sa.Column('external_status', sa.String(30), nullable=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_category', sa.String(50), nullable=True),
        sa.Column('retryable', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_publish_attempts_request', 'publish_attempts', ['publish_request_id'])
    op.create_index('ix_publish_attempts_target', 'publish_attempts', ['publish_target_id'])

    # PublishStatusCallback
    op.create_table('publish_status_callbacks',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('publish_request_id', postgresql.UUID, sa.ForeignKey("publish_requests.id"), nullable=False),
        sa.Column('publish_target_id', postgresql.UUID, sa.ForeignKey("publish_targets.id"), nullable=False),
        sa.Column('callback_token_hash', sa.String(128), server_default='', nullable=False),
        sa.Column('callback_event_id', sa.String(255), nullable=False),
        sa.Column('callback_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('callback_signature_version', sa.String(10), server_default='v1', nullable=False),
        sa.Column('callback_token_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('callback_token_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('external_url', sa.String(500), nullable=True),
        sa.Column('status', sa.String(30), server_default='received', nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('callback_payload', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('signature_header', sa.String(500), nullable=True),
        sa.Column('signature_valid', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('token_valid', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('replay_detected', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('processed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint('uq_publish_callbacks_event_id', 'publish_status_callbacks', ['callback_event_id'])
    op.create_index('ix_publish_callbacks_request', 'publish_status_callbacks', ['publish_request_id'])
    op.create_index('ix_publish_callbacks_target', 'publish_status_callbacks', ['publish_target_id'])
    op.create_index('ix_publish_callbacks_received_at', 'publish_status_callbacks', ['received_at'])

    # PublishEvent
    op.create_table('publish_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True),
        sa.Column('content_package_id', postgresql.UUID, sa.ForeignKey("content_packages.id"), nullable=True),
        sa.Column('publish_batch_id', postgresql.UUID, sa.ForeignKey("publish_batches.id"), nullable=True),
        sa.Column('publish_request_id', postgresql.UUID, sa.ForeignKey("publish_requests.id"), nullable=True),
        sa.Column('publish_attempt_id', postgresql.UUID, sa.ForeignKey("publish_attempts.id"), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('old_status', sa.String(30), nullable=True),
        sa.Column('new_status', sa.String(30), nullable=True),
        sa.Column('message', sa.Text(), server_default='', nullable=False),
        sa.Column('metadata_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_publish_events_batch', 'publish_events', ['publish_batch_id'])
    op.create_index('ix_publish_events_request', 'publish_events', ['publish_request_id'])
    op.create_index('ix_publish_events_type', 'publish_events', ['event_type'])

    # CMSFieldMapping
    op.create_table('cms_field_mappings',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('publish_target_id', postgresql.UUID, sa.ForeignKey("publish_targets.id"), nullable=False),
        sa.Column('field_type', sa.String(30), nullable=False),
        sa.Column('local_value', sa.String(255), nullable=False),
        sa.Column('external_id', sa.String(255), server_default='', nullable=False),
        sa.Column('external_label', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_cms_field_mappings_target_type_value', 'cms_field_mappings',
                                ['publish_target_id', 'field_type', 'local_value'])
    op.create_index('ix_cms_field_mappings_target_type', 'cms_field_mappings', ['publish_target_id', 'field_type'])

    # ContentPackage extension
    op.add_column('content_packages', sa.Column('publish_status_summary', sa.String(30), server_default='not_published', nullable=False))
    op.add_column('content_packages', sa.Column('published_target_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('content_packages', sa.Column('failed_target_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('content_packages', sa.Column('last_published_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('content_packages', 'last_published_at')
    op.drop_column('content_packages', 'failed_target_count')
    op.drop_column('content_packages', 'published_target_count')
    op.drop_column('content_packages', 'publish_status_summary')
    for tbl in ['cms_field_mappings', 'publish_events', 'publish_status_callbacks',
                'publish_attempts', 'publish_requests', 'publish_batches', 'publish_targets']:
        op.drop_table(tbl)
