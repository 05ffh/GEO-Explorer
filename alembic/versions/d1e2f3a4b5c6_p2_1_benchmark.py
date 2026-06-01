"""p2_1_benchmark

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BenchmarkDefinition
    op.create_table(
        'benchmark_definitions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('sample_requirements', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('aggregation_strategy', sa.String(30), server_default='latest', nullable=False),
        sa.Column('percentile_method', sa.String(50), server_default='linear_interpolation', nullable=False),
        sa.Column('outlier_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('fallback_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('freshness_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('kpi_normalization', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('material_gap_threshold', sa.Float(), server_default='0.05', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # BenchmarkSnapshot
    op.create_table(
        'benchmark_snapshots',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('industry_key', sa.String(100), nullable=False, index=True),
        sa.Column('industry_template_id', postgresql.UUID, sa.ForeignKey("industry_templates.id"), nullable=True),
        sa.Column('industry_template_version', sa.String(20), nullable=True),
        sa.Column('industry_domain', sa.String(100), nullable=True),
        sa.Column('industry_category', sa.String(100), nullable=True),
        sa.Column('industry_subcategory', sa.String(100), nullable=True),
        sa.Column('region', sa.String(50), nullable=True),
        sa.Column('locale', sa.String(10), server_default='zh-CN', nullable=False),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column('benchmark_scope', sa.String(20), server_default='global', nullable=False),
        sa.Column('sample_brand_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sample_run_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('kpi_sample_counts', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('excluded_brand_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('excluded_reason_summary', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('deduplicated_brand_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('excluded_demo_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('excluded_unconfirmed_industry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('aggregation_strategy', sa.String(30), server_default='latest', nullable=False),
        sa.Column('kpi_p50', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('kpi_p25', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('kpi_p75', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('kpi_mean', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('kpi_confidence_intervals', postgresql.JSONB, nullable=True),
        sa.Column('quality_level', sa.String(20), server_default='insufficient', nullable=False),
        sa.Column('confidence', sa.String(20), server_default='low', nullable=False),
        sa.Column('confidence_reason', sa.Text(), nullable=True),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('freshness_status', sa.String(20), server_default='fresh', nullable=False),
        sa.Column('benchmark_definition_id', postgresql.UUID, sa.ForeignKey("benchmark_definitions.id"), nullable=True),
        sa.Column('benchmark_definition_version', sa.String(20), nullable=True),
        sa.Column('definition_snapshot_json', postgresql.JSONB, nullable=True),
        sa.Column('benchmark_key', sa.String(255), unique=True, nullable=False),
        sa.Column('version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('status', sa.String(20), server_default='computing', nullable=False, index=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('computed_by_task_id', sa.String(255), nullable=True),
        sa.Column('superseded_by_id', postgresql.UUID, sa.ForeignKey("benchmark_snapshots.id"), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # GapAttributionResult
    op.create_table(
        'gap_attribution_results',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('benchmark_snapshot_id', postgresql.UUID, sa.ForeignKey("benchmark_snapshots.id"), nullable=True),
        sa.Column('competitor_set_id', postgresql.UUID, sa.ForeignKey("competitor_sets.id"), nullable=True),
        sa.Column('competitor_set_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('metrics_snapshot_id', postgresql.UUID, sa.ForeignKey("metrics_snapshots.id"), nullable=True),
        sa.Column('kpi_key', sa.String(50), nullable=False),
        sa.Column('gap_magnitude', sa.Float(), server_default='0', nullable=False),
        sa.Column('gap_significance', sa.String(20), server_default='none', nullable=False),
        sa.Column('materiality_reason', sa.Text(), nullable=True),
        sa.Column('result_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('confidence', sa.String(20), server_default='medium', nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False, index=True),
        sa.Column('generated_by_task_id', sa.String(255), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stale_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('gap_attribution_results')
    op.drop_table('benchmark_snapshots')
    op.drop_table('benchmark_definitions')
