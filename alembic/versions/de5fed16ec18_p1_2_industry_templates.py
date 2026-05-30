"""p1_2_industry_templates

Revision ID: de5fed16ec18
Revises: 4ce0b24f328e
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'de5fed16ec18'
down_revision: Union[str, Sequence[str], None] = '4ce0b24f328e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IndustryTemplate
    op.create_table(
        'industry_templates',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('slug', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text, server_default='', nullable=False),
        sa.Column('parent_id', postgresql.UUID, nullable=True),
        sa.Column('level', sa.String(50), server_default='domain', nullable=False),
        sa.Column('domain', sa.String(100), server_default='', nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('subcategory', sa.String(100), nullable=True),
        sa.Column('version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('status', sa.String(20), server_default='draft', nullable=False),
        sa.Column('region', sa.String(50), server_default='CN', nullable=False),
        sa.Column('locale', sa.String(10), server_default='zh-CN', nullable=False),
        sa.Column('business_model_tags', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('required_gt_fields', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('optional_gt_fields', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('high_risk_gt_fields', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('industry_specific_fields', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('field_evidence_requirements', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('gt_field_weights', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('kpi_weights', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('competitor_rules', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('risk_rules', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('compliance_constraints', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('action_rules', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('content_templates', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('review_rules', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_by', postgresql.UUID, nullable=True),
        sa.Column('updated_by', postgresql.UUID, nullable=True),
        sa.Column('change_log', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # IndustryQueryTemplate
    op.create_table(
        'industry_query_templates',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('industry_template_id', postgresql.UUID, sa.ForeignKey("industry_templates.id"), nullable=False, index=True),
        sa.Column('dimension', sa.String(100), server_default='', nullable=False),
        sa.Column('intent', sa.String(100), server_default='', nullable=False),
        sa.Column('question_text', sa.Text, nullable=False),
        sa.Column('uses_brand_name', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('target_kpis', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('target_gt_fields', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('risk_level', sa.String(10), server_default='P1', nullable=False),
        sa.Column('weight', sa.Float(), server_default=sa.text('1.0'), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    # Brand industry fields
    op.add_column('brands', sa.Column('primary_industry_template_id', postgresql.UUID, nullable=True))
    op.add_column('brands', sa.Column('secondary_industry_template_ids', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.add_column('brands', sa.Column('industry_template_version', sa.String(20), nullable=True))
    op.add_column('brands', sa.Column('industry_template_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('brands', sa.Column('industry_template_changed_by', postgresql.UUID, nullable=True))
    op.add_column('brands', sa.Column('industry_template_change_reason', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column('brands', 'industry_template_change_reason')
    op.drop_column('brands', 'industry_template_changed_by')
    op.drop_column('brands', 'industry_template_changed_at')
    op.drop_column('brands', 'industry_template_version')
    op.drop_column('brands', 'secondary_industry_template_ids')
    op.drop_column('brands', 'primary_industry_template_id')
    op.drop_table('industry_query_templates')
    op.drop_table('industry_templates')
