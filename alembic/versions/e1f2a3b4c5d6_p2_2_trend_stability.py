"""p2_2_trend_stability

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TrendAnalysisDefinition
    op.create_table(
        'trend_analysis_definitions',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('sampling_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('quality_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('cliff_detection_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('sustained_trend_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('stability_score_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('change_scope_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('dedupe_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('resolved_policy', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # TrendInsight
    op.create_table(
        'trend_insights',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('insight_key', sa.String(255), unique=True, nullable=False),
        sa.Column('insight_type', sa.String(50), nullable=False, index=True),
        sa.Column('kpi_key', sa.String(50), nullable=True, index=True),
        sa.Column('severity', sa.String(20), server_default='info', nullable=False),
        sa.Column('status', sa.String(20), server_default='open', nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('evidence_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('sample_point_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('required_point_count', sa.Integer(), server_default='6', nullable=False),
        sa.Column('data_coverage_ratio', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('data_quality_level', sa.String(20), server_default='medium', nullable=False),
        sa.Column('confidence', sa.String(20), server_default='medium', nullable=False),
        sa.Column('confidence_reason', sa.Text(), nullable=True),
        sa.Column('change_scope', sa.String(50), nullable=True),
        sa.Column('evidence_strength', sa.String(20), server_default='moderate', nullable=False),
        sa.Column('evidence_strength_reason', sa.Text(), nullable=True),
        sa.Column('analysis_definition_id', postgresql.UUID, sa.ForeignKey("trend_analysis_definitions.id"), nullable=True),
        sa.Column('analysis_definition_version', sa.String(20), nullable=True),
        sa.Column('definition_snapshot_json', postgresql.JSONB, nullable=True),
        sa.Column('algorithm_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_reason', sa.Text(), nullable=True),
        sa.Column('resolved_evidence_json', postgresql.JSONB, nullable=True),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('acknowledged_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stale_reason', sa.Text(), nullable=True),
        sa.Column('superseded_by_id', postgresql.UUID, sa.ForeignKey("trend_insights.id"), nullable=True),
        sa.Column('parent_insight_id', postgresql.UUID, sa.ForeignKey("trend_insights.id"), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # TrendInsightEvent
    op.create_table(
        'trend_insight_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('trend_insight_id', postgresql.UUID, sa.ForeignKey("trend_insights.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('old_status', sa.String(20), nullable=True),
        sa.Column('new_status', sa.String(20), nullable=True),
        sa.Column('old_severity', sa.String(20), nullable=True),
        sa.Column('new_severity', sa.String(20), nullable=True),
        sa.Column('message', sa.Text(), server_default='', nullable=False),
        sa.Column('metadata_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # PlatformTrendIncident
    op.create_table(
        'platform_trend_incidents',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('platform', sa.String(50), nullable=False, index=True),
        sa.Column('kpi_key', sa.String(50), nullable=False),
        sa.Column('incident_type', sa.String(50), nullable=False),
        sa.Column('affected_brand_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('affected_industry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('severity', sa.String(20), server_default='warning', nullable=False),
        sa.Column('evidence_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('status', sa.String(20), server_default='active', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # ImpactEvent
    op.create_table(
        'impact_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column('platform', sa.String(50), nullable=True),
        sa.Column('event_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confidence', sa.String(20), server_default='medium', nullable=False),
        sa.Column('source_id', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # ModelEvent
    op.create_table(
        'model_events',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('platform', sa.String(50), nullable=False, index=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('event_end_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('affected_region', sa.String(50), nullable=True),
        sa.Column('affected_model_version_before', sa.String(50), nullable=True),
        sa.Column('affected_model_version_after', sa.String(50), nullable=True),
        sa.Column('impact_scope', sa.String(50), server_default='unknown', nullable=False),
        sa.Column('source', sa.String(50), server_default='observed', nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('confidence', sa.String(20), server_default='low', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('model_events')
    op.drop_table('impact_events')
    op.drop_table('platform_trend_incidents')
    op.drop_table('trend_insight_events')
    op.drop_table('trend_insights')
    op.drop_table('trend_analysis_definitions')
