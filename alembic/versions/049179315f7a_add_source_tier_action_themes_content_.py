"""add source_tier action_themes content_package_governance

Revision ID: 049179315f7a
Revises: 1225dbebd7ea
Create Date: 2026-05-29 22:26:53.882661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '049179315f7a'
down_revision: Union[str, Sequence[str], None] = '1225dbebd7ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create action_themes table
    op.create_table('action_themes',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('collection_run_id', sa.UUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('priority', sa.String(length=10), nullable=False),
        sa.Column('issue_type', sa.String(length=100), nullable=False),
        sa.Column('affected_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('affected_platforms', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('hallucination_result_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('action_plan_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('evidence_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('typical_ai_claims', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('recommended_content_types', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('expected_kpi_impact', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('effort_level', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['collection_run_id'], ['collection_runs.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_action_themes_brand_id'), 'action_themes', ['brand_id'], unique=False)
    op.create_index(op.f('ix_action_themes_organization_id'), 'action_themes', ['organization_id'], unique=False)

    # Extend content_packages with governance fields
    op.add_column('content_packages', sa.Column('action_theme_id', sa.UUID(), nullable=True))
    op.add_column('content_packages', sa.Column('fact_source_map', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column('content_packages', sa.Column('risk_level', sa.String(length=10), nullable=False, server_default=sa.text("'low'::varchar")))
    op.add_column('content_packages', sa.Column('publish_url', sa.Text(), nullable=False, server_default=sa.text("''::text")))
    op.add_column('content_packages', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(None, 'content_packages', 'action_themes', ['action_theme_id'], ['id'])

    # Extend gt_evidences with source tier and review fields
    op.add_column('gt_evidences', sa.Column('source_tier', sa.String(length=10), nullable=False, server_default=sa.text("'C'::varchar")))
    op.add_column('gt_evidences', sa.Column('human_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('gt_evidences', sa.Column('review_status', sa.String(length=20), nullable=False, server_default=sa.text("'pending'::varchar")))


def downgrade() -> None:
    op.drop_column('gt_evidences', 'review_status')
    op.drop_column('gt_evidences', 'human_confirmed')
    op.drop_column('gt_evidences', 'source_tier')

    op.drop_constraint(None, 'content_packages', type_='foreignkey')
    op.drop_column('content_packages', 'verified_at')
    op.drop_column('content_packages', 'publish_url')
    op.drop_column('content_packages', 'risk_level')
    op.drop_column('content_packages', 'fact_source_map')
    op.drop_column('content_packages', 'action_theme_id')

    op.drop_index(op.f('ix_action_themes_organization_id'), table_name='action_themes')
    op.drop_index(op.f('ix_action_themes_brand_id'), table_name='action_themes')
    op.drop_table('action_themes')
