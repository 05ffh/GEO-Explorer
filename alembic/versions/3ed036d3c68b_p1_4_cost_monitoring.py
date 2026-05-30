"""p1_4_cost_monitoring

Revision ID: 3ed036d3c68b
Revises: 5a9b36b5632b
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3ed036d3c68b'
down_revision: Union[str, Sequence[str], None] = '5a9b36b5632b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend api_usage_logs
    op.add_column('api_usage_logs', sa.Column('user_id', postgresql.UUID, nullable=True))
    op.add_column('api_usage_logs', sa.Column('provider', sa.String(50), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('model_name', sa.String(100), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('operation_type', sa.String(50), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('module_name', sa.String(100), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('total_tokens', sa.Integer(), server_default='0', nullable=True))
    op.add_column('api_usage_logs', sa.Column('cached_tokens', sa.Integer(), server_default='0', nullable=True))
    op.add_column('api_usage_logs', sa.Column('input_cost', sa.Numeric(10, 6), server_default='0', nullable=True))
    op.add_column('api_usage_logs', sa.Column('output_cost', sa.Numeric(10, 6), server_default='0', nullable=True))
    op.add_column('api_usage_logs', sa.Column('currency', sa.String(10), server_default='CNY', nullable=True))
    op.add_column('api_usage_logs', sa.Column('pricing_version', sa.String(20), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('estimated_cost', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('api_usage_logs', sa.Column('error_code', sa.String(100), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('error_message', sa.Text(), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('retry_count', sa.Integer(), server_default='0', nullable=True))
    op.add_column('api_usage_logs', sa.Column('is_retry', sa.Boolean(), server_default=sa.text('false'), nullable=True))
    op.add_column('api_usage_logs', sa.Column('billable', sa.Boolean(), server_default=sa.text('true'), nullable=True))
    op.add_column('api_usage_logs', sa.Column('latency_ms', sa.Integer(), nullable=True))
    op.add_column('api_usage_logs', sa.Column('request_id', sa.String(100), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('task_id', sa.String(100), server_default='', nullable=True))
    op.add_column('api_usage_logs', sa.Column('gt_candidate_id', postgresql.UUID, nullable=True))
    op.add_column('api_usage_logs', sa.Column('action_theme_id', postgresql.UUID, nullable=True))
    op.add_column('api_usage_logs', sa.Column('content_package_id', postgresql.UUID, nullable=True))
    # ModelPricing
    op.create_table(
        'model_pricing',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('input_price_per_1k_tokens', sa.Numeric(10, 6), server_default='0', nullable=False),
        sa.Column('output_price_per_1k_tokens', sa.Numeric(10, 6), server_default='0', nullable=False),
        sa.Column('cached_price_per_1k_tokens', sa.Numeric(10, 6), nullable=True),
        sa.Column('request_price', sa.Numeric(10, 6), nullable=True),
        sa.Column('currency', sa.String(10), server_default='CNY', nullable=False),
        sa.Column('pricing_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # UsageBudget
    op.create_table(
        'usage_budgets',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True, index=True),
        sa.Column('period', sa.String(20), server_default='monthly', nullable=False),
        sa.Column('budget_amount', sa.Numeric(10, 2), server_default='0', nullable=False),
        sa.Column('currency', sa.String(10), server_default='CNY', nullable=False),
        sa.Column('alert_thresholds', postgresql.JSONB, server_default=sa.text("'[80,90,100]'::jsonb"), nullable=False),
        sa.Column('hard_limit_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_by', postgresql.UUID, nullable=True),
        sa.Column('updated_by', postgresql.UUID, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # CostAlert
    op.create_table(
        'cost_alerts',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True, index=True),
        sa.Column('alert_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), server_default='warning', nullable=False),
        sa.Column('threshold_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('current_value', sa.Numeric(10, 2), nullable=True),
        sa.Column('message', sa.Text, server_default='', nullable=False),
        sa.Column('status', sa.String(20), server_default='open', nullable=False, index=True),
        sa.Column('acknowledged_by', postgresql.UUID, nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('cost_alerts')
    op.drop_table('usage_budgets')
    op.drop_table('model_pricing')
    for col in ['content_package_id','action_theme_id','gt_candidate_id','task_id','request_id','latency_ms','billable','is_retry','retry_count','error_message','error_code','estimated_cost','pricing_version','currency','output_cost','input_cost','cached_tokens','total_tokens','module_name','operation_type','model_name','provider','user_id']:
        op.drop_column('api_usage_logs', col)
