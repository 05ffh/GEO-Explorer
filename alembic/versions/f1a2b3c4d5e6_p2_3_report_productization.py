"""p2_3_report_productization

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-05-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ReportBranding
    op.create_table('report_brandings',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('scope', sa.String(20), server_default='brand', nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column('is_default', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('logo_url', sa.String(500), nullable=True),
        sa.Column('primary_color', sa.String(7), server_default='#1E40AF', nullable=False),
        sa.Column('accent_color', sa.String(7), server_default='#3B82F6', nullable=False),
        sa.Column('font_heading', sa.String(100), server_default='Fira Sans', nullable=False),
        sa.Column('font_body', sa.String(100), server_default='Fira Sans', nullable=False),
        sa.Column('footer_text', sa.Text(), nullable=True),
        sa.Column('company_name_display', sa.String(255), nullable=True),
        sa.Column('hide_geo_branding', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # ReportSchedule
    op.create_table('report_schedules',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('name', sa.String(255), server_default='', nullable=False),
        sa.Column('editions', postgresql.JSONB, server_default=sa.text("'[\"executive\",\"customer\"]'::jsonb"), nullable=False),
        sa.Column('formats', postgresql.JSONB, server_default=sa.text("'[\"pdf\"]'::jsonb"), nullable=False),
        sa.Column('frequency', sa.String(30), server_default='monthly', nullable=False),
        sa.Column('timezone', sa.String(50), server_default='Asia/Shanghai', nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('only_if_new_collection', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('schedule_key', sa.String(255), nullable=True, unique=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_successful_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failed_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # ReportScheduleRun
    op.create_table('report_schedule_runs',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('schedule_id', postgresql.UUID, sa.ForeignKey("report_schedules.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('period_key', sa.String(255), nullable=False),
        sa.Column('status', sa.String(30), server_default='triggered', nullable=False),
        sa.Column('skip_reason', sa.Text(), nullable=True),
        sa.Column('artifact_ids', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('delivery_attempt_ids', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # ReportSubscription
    op.create_table('report_subscriptions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('schedule_id', postgresql.UUID, sa.ForeignKey("report_schedules.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('recipient_type', sa.String(30), server_default='internal_user', nullable=False),
        sa.Column('recipient_user_ids', postgresql.JSONB, nullable=True),
        sa.Column('external_recipients', postgresql.JSONB, nullable=True),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('webhook_secret_hash', sa.String(128), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('unsubscribe_token_hash', sa.String(128), nullable=True),
        sa.Column('delivery_method', sa.String(30), server_default='email', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('last_delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # ReportDeliveryAttempt
    op.create_table('report_delivery_attempts',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('report_artifact_id', postgresql.UUID, sa.ForeignKey("report_artifacts.id"), nullable=False, index=True),
        sa.Column('schedule_id', postgresql.UUID, sa.ForeignKey("report_schedules.id"), nullable=True),
        sa.Column('subscription_id', postgresql.UUID, sa.ForeignKey("report_subscriptions.id"), nullable=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('delivery_method', sa.String(30), server_default='email', nullable=False),
        sa.Column('delivery_key', sa.String(255), nullable=True, unique=True),
        sa.Column('recipient', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), server_default='queued', nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provider_message_id', sa.String(255), nullable=True),
        sa.Column('force_resend', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # ReportDownloadLink
    op.create_table('report_download_links',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('report_artifact_id', postgresql.UUID, sa.ForeignKey("report_artifacts.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('token_hash', sa.String(128), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('max_downloads', sa.Integer(), nullable=True),
        sa.Column('download_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_revoked', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('access_scope', sa.String(20), server_default='internal', nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # ReportDownloadEvent
    op.create_table('report_download_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('report_artifact_id', postgresql.UUID, sa.ForeignKey("report_artifacts.id"), nullable=False),
        sa.Column('download_link_id', postgresql.UUID, sa.ForeignKey("report_download_links.id"), nullable=True),
        sa.Column('user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column('access_scope', sa.String(20), server_default='internal', nullable=False),
        sa.Column('ip_address_hash', sa.String(128), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('status', sa.String(30), server_default='success', nullable=False),
        sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    # ReportBatch
    op.create_table('report_batches',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('name', sa.String(255), server_default='', nullable=False),
        sa.Column('brand_ids', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('editions', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('formats', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('status', sa.String(30), server_default='queued', nullable=False),
        sa.Column('total_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('success_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_concurrency', sa.Integer(), server_default='3', nullable=False),
        sa.Column('estimated_artifact_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    for tbl in ['report_batches', 'report_download_events', 'report_download_links',
                'report_delivery_attempts', 'report_subscriptions', 'report_schedule_runs',
                'report_schedules', 'report_brandings']:
        op.drop_table(tbl)
