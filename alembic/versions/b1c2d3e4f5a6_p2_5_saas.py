"""p2_5_saas

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-05-31
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Organization extension
    op.add_column('organizations', sa.Column('slug', sa.String(100), nullable=True))
    op.create_unique_constraint('uq_org_slug', 'organizations', ['slug'])
    op.add_column('organizations', sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    op.add_column('organizations', sa.Column('brand_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('organizations', sa.Column('user_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('organizations', sa.Column('onboarding_step', sa.Integer(), server_default='0', nullable=False))
    op.add_column('organizations', sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('organizations', sa.Column('first_brand_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('organizations', sa.Column('first_collection_run_at', sa.DateTime(timezone=True), nullable=True))

    # User extension
    op.add_column('users', sa.Column('platform_mfa_required', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('platform_access_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False))

    # PlanDefinition
    op.create_table('plan_definitions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), server_default='', nullable=False),
        sa.Column('tier', sa.Integer(), server_default='0', nullable=False),
        sa.Column('version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_public', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_deprecated', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('max_brands', sa.Integer(), server_default='1', nullable=False),
        sa.Column('max_users', sa.Integer(), server_default='1', nullable=False),
        sa.Column('max_competitors', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_api_keys', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_cms_targets', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_webhook_targets', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_reports_per_month', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_exports_per_month', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_collection_runs_per_month', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_questions_per_collection', sa.Integer(), server_default='5', nullable=False),
        sa.Column('max_platforms_per_collection', sa.Integer(), server_default='3', nullable=False),
        sa.Column('max_api_requests_per_month', sa.Integer(), server_default='0', nullable=False),
        sa.Column('data_retention_days', sa.Integer(), server_default='90', nullable=False),
        sa.Column('trend_history_days', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_storage_mb', sa.Integer(), server_default='100', nullable=False),
        sa.Column('features_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('monthly_price_cny', sa.Numeric(10, 2), nullable=True),
        sa.Column('yearly_price_cny', sa.Numeric(10, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_plans_name_version', 'plan_definitions', ['name', 'version'])
    op.create_index('ix_plans_name_active', 'plan_definitions', ['name', 'is_active'])
    op.create_index('ix_plans_public_deprecated', 'plan_definitions', ['is_public', 'is_deprecated'])
    op.create_index('ix_plans_effective', 'plan_definitions', ['effective_from', 'effective_until'])

    # OrgSubscription
    op.create_table('org_subscriptions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('plan_id', postgresql.UUID, sa.ForeignKey("plan_definitions.id"), nullable=False),
        sa.Column('plan_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('suspension_reason', sa.Text(), nullable=True),
        sa.Column('grace_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_renew', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('entitlements_snapshot_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('override_max_brands', sa.Integer(), nullable=True),
        sa.Column('override_max_users', sa.Integer(), nullable=True),
        sa.Column('override_max_api_keys', sa.Integer(), nullable=True),
        sa.Column('override_max_cms_targets', sa.Integer(), nullable=True),
        sa.Column('pending_plan_id', postgresql.UUID, sa.ForeignKey("plan_definitions.id"), nullable=True),
        sa.Column('pending_change_effective_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pending_change_type', sa.String(30), nullable=True),
        sa.Column('current_brand_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('current_user_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('current_token_usage', sa.Integer(), server_default='0', nullable=False),
        sa.Column('current_cost_cny', sa.Numeric(12, 4), server_default='0', nullable=False),
        sa.Column('last_usage_update_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_sub_org_status', 'org_subscriptions', ['organization_id', 'status'])
    op.create_index('ix_sub_plan_version', 'org_subscriptions', ['plan_id', 'plan_version'])

    # ApiKey
    op.create_table('api_keys',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('name', sa.String(255), server_default='', nullable=False),
        sa.Column('key_type', sa.String(20), server_default='live', nullable=False),
        sa.Column('key_prefix', sa.String(20), nullable=False),
        sa.Column('key_hash', sa.String(255), nullable=False),
        sa.Column('scopes_json', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('allowed_ips', postgresql.JSONB, nullable=True),
        sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
        sa.Column('rotated_from_key_id', postgresql.UUID, sa.ForeignKey("api_keys.id"), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('revocation_reason', sa.Text(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_ip_hash', sa.String(128), nullable=True),
        sa.Column('last_used_user_agent', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_api_keys_hash', 'api_keys', ['key_hash'])
    op.create_index('ix_api_keys_org_active', 'api_keys', ['organization_id', 'is_active'])
    op.create_index('ix_api_keys_prefix', 'api_keys', ['key_prefix'])
    op.create_index('ix_api_keys_expires', 'api_keys', ['expires_at'])

    # ApiKeyUsageLog
    op.create_table('api_key_usage_logs',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('api_key_id', postgresql.UUID, sa.ForeignKey("api_keys.id"), nullable=False),
        sa.Column('endpoint', sa.String(255), server_default='', nullable=False),
        sa.Column('method', sa.String(10), server_default='', nullable=False),
        sa.Column('status_code', sa.Integer(), server_default='0', nullable=False),
        sa.Column('ip_hash', sa.String(128), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_apikey_log_key', 'api_key_usage_logs', ['api_key_id', 'created_at'])
    op.create_index('ix_apikey_log_org', 'api_key_usage_logs', ['organization_id'])

    # OrgInvite
    op.create_table('org_invites',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('invited_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), server_default='viewer', nullable=False),
        sa.Column('token_hash', sa.String(128), nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_invites_token', 'org_invites', ['token_hash'])
    op.create_index('ix_invites_expires', 'org_invites', ['expires_at'])

    # DataExport
    op.create_table('data_exports',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('scope', sa.String(20), server_default='brand', nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True),
        sa.Column('format', sa.String(20), server_default='json', nullable=False),
        sa.Column('redaction_level', sa.String(20), server_default='full', nullable=False),
        sa.Column('included_sections_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.String(20), server_default='queued', nullable=False),
        sa.Column('task_state_id', sa.String(255), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_hash', sa.String(128), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('storage_key', sa.String(255), nullable=True),
        sa.Column('download_token_hash', sa.String(128), nullable=True),
        sa.Column('download_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_downloads', sa.Integer(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('requested_by_role', sa.String(50), nullable=True),
        sa.Column('export_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_exports_org_status', 'data_exports', ['organization_id', 'status'])
    op.create_index('ix_exports_user', 'data_exports', ['user_id', 'created_at'])
    op.create_index('ix_exports_expires', 'data_exports', ['expires_at'])
    op.create_unique_constraint('uq_exports_download_token', 'data_exports', ['download_token_hash'])

    # DataDeletionRequest
    op.create_table('data_deletion_requests',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('requested_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('scope', sa.String(20), server_default='brand', nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True),
        sa.Column('status', sa.String(20), server_default='requested', nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('scheduled_delete_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retention_days', sa.Integer(), server_default='90', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('affected_tables_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('affected_backup_policy', sa.Text(), nullable=True),
        sa.Column('dry_run_result_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('task_state_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_deletion_org_scope_status', 'data_deletion_requests', ['organization_id', 'scope', 'status'])

    # UsageEvent
    op.create_table('usage_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('meter_key', sa.String(100), nullable=False),
        sa.Column('meter_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('source_type', sa.String(50), server_default='', nullable=False),
        sa.Column('source_id', postgresql.UUID, nullable=True),
        sa.Column('quantity', sa.Numeric(12, 4), server_default='1', nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('idempotency_key', sa.String(255), nullable=False),
        sa.Column('metadata_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_usage_events_idempotency', 'usage_events', ['idempotency_key'])
    op.create_index('ix_usage_events_org_meter_time', 'usage_events', ['organization_id', 'meter_key', 'occurred_at'])

    # UsageSnapshot
    op.create_table('usage_snapshots',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('snapshot_type', sa.String(30), server_default='customer', nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_timezone', sa.String(50), server_default='UTC', nullable=False),
        sa.Column('period_type', sa.String(20), server_default='monthly', nullable=False),
        sa.Column('brand_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('user_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('collection_runs', sa.Integer(), server_default='0', nullable=False),
        sa.Column('api_requests', sa.Integer(), server_default='0', nullable=False),
        sa.Column('token_usage', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cost_cny', sa.Numeric(12, 4), server_default='0', nullable=False),
        sa.Column('report_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('export_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('storage_mb', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_usage_snapshots_period', 'usage_snapshots',
                                ['organization_id', 'period_start', 'period_end', 'snapshot_type'])
    op.create_index('ix_usage_snapshots_period', 'usage_snapshots', ['period_start', 'period_end'])

    # UsageMeterDefinition
    op.create_table('usage_meter_definitions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('meter_key', sa.String(100), nullable=False),
        sa.Column('version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('counting_rule_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('reset_period', sa.String(20), server_default='monthly', nullable=False),
        sa.Column('is_billable', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_customer_visible', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_meter_def_key_version', 'usage_meter_definitions', ['meter_key', 'version'])

    # PlanChangeRequest
    op.create_table('plan_change_requests',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('requested_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('current_plan_id', postgresql.UUID, sa.ForeignKey("plan_definitions.id"), nullable=False),
        sa.Column('target_plan_id', postgresql.UUID, sa.ForeignKey("plan_definitions.id"), nullable=False),
        sa.Column('target_plan_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('change_type', sa.String(30), server_default='upgrade', nullable=False),
        sa.Column('effective_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), server_default='previewed', nullable=False),
        sa.Column('impact_preview_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('approved_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_plan_change_org_status', 'plan_change_requests', ['organization_id', 'status'])
    op.create_index('ix_plan_change_effective', 'plan_change_requests', ['effective_at'])

    # FeatureFlag
    op.create_table('feature_flags',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), server_default='', nullable=False),
        sa.Column('flag_type', sa.String(30), server_default='beta_feature', nullable=False),
        sa.Column('default_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('rollout_percentage', sa.Integer(), nullable=True),
        sa.Column('allowed_plan_names', postgresql.JSONB, nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_feature_flags_key', 'feature_flags', ['key'])

    # FeatureFlagOverride
    op.create_table('feature_flag_overrides',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('feature_flag_id', postgresql.UUID, sa.ForeignKey("feature_flags.id"), nullable=False),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column('user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('reason', sa.Text(), server_default='', nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_flag_override_org', 'feature_flag_overrides', ['feature_flag_id', 'organization_id'])

    # EmergencyPause
    op.create_table('emergency_pauses',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('scope', sa.String(30), server_default='global', nullable=False),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column('feature_key', sa.String(100), nullable=True),
        sa.Column('operation_type', sa.String(50), nullable=True),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('reason', sa.Text(), server_default='', nullable=False),
        sa.Column('risk_level', sa.String(10), server_default='medium', nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('resolved_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_epause_scope_status', 'emergency_pauses', ['scope', 'status'])
    op.create_index('ix_epause_org', 'emergency_pauses', ['organization_id'])

    # PlatformAdminProfile
    op.create_table('platform_admin_profiles',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column('platform_role', sa.String(30), server_default='system_admin', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('mfa_enforced', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('granted_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # PlatformAccessSession
    op.create_table('platform_access_sessions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('platform_user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('target_organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('access_type', sa.String(30), server_default='governance', nullable=False),
        sa.Column('reason', sa.Text(), server_default='', nullable=False),
        sa.Column('scope', sa.String(30), server_default='read_only', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('approved_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('customer_visible', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_pas_user_status', 'platform_access_sessions', ['platform_user_id', 'status'])
    op.create_index('ix_pas_target_org', 'platform_access_sessions', ['target_organization_id'])

    # PlatformApprovalRequest
    op.create_table('platform_approval_requests',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('requested_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column('action_type', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', postgresql.UUID, nullable=True),
        sa.Column('risk_level', sa.String(10), server_default='medium', nullable=False),
        sa.Column('reason', sa.Text(), server_default='', nullable=False),
        sa.Column('status', sa.String(20), server_default='pending', nullable=False),
        sa.Column('approved_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_par_requested_by', 'platform_approval_requests', ['requested_by', 'status'])
    op.create_index('ix_par_resource', 'platform_approval_requests', ['resource_type', 'resource_id'])

    # AuditIntegrityCheck
    op.create_table('audit_integrity_checks',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('scope', sa.String(20), server_default='organization', nullable=False),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), server_default='passed', nullable=False),
        sa.Column('failed_at_event_id', postgresql.UUID, nullable=True),
        sa.Column('details_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # RateLimitPolicy
    op.create_table('rate_limit_policies',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('scope', sa.String(30), server_default='organization', nullable=False),
        sa.Column('limit', sa.Integer(), server_default='100', nullable=False),
        sa.Column('window_seconds', sa.Integer(), server_default='60', nullable=False),
        sa.Column('burst', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_unique_constraint('uq_rl_policy_key', 'rate_limit_policies', ['key'])


def downgrade() -> None:
    for tbl in ['rate_limit_policies', 'audit_integrity_checks', 'platform_approval_requests',
                'platform_access_sessions', 'platform_admin_profiles', 'emergency_pauses',
                'feature_flag_overrides', 'feature_flags', 'plan_change_requests',
                'usage_meter_definitions', 'usage_snapshots', 'usage_events',
                'data_deletion_requests', 'data_exports', 'org_invites',
                'api_key_usage_logs', 'api_keys', 'org_subscriptions', 'plan_definitions']:
        op.drop_table(tbl)
    op.drop_column('users', 'platform_access_enabled')
    op.drop_column('users', 'platform_mfa_required')
    op.drop_column('organizations', 'first_collection_run_at')
    op.drop_column('organizations', 'first_brand_created_at')
    op.drop_column('organizations', 'onboarding_completed_at')
    op.drop_column('organizations', 'onboarding_step')
    op.drop_column('organizations', 'user_count')
    op.drop_column('organizations', 'brand_count')
    op.drop_column('organizations', 'is_active')
    op.drop_constraint('uq_org_slug', 'organizations')
    op.drop_column('organizations', 'slug')
