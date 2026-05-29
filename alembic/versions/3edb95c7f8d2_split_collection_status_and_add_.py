"""split_collection_status_and_add_analysis_fields

Revision ID: 3edb95c7f8d2
Revises: 0d3178a9cc1d
Create Date: 2026-05-29 10:09:28.295545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3edb95c7f8d2'
down_revision: Union[str, Sequence[str], None] = '0d3178a9cc1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create insight_summaries table
    op.create_table('insight_summaries',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('collection_run_id', sa.UUID(), nullable=False),
        sa.Column('platform_health_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('brand_performance_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('key_findings_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('data_reliability_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('confidence_level', sa.String(length=20), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['collection_run_id'], ['collection_runs.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_insight_summaries_brand_id'), 'insight_summaries', ['brand_id'], unique=False)
    op.create_index(op.f('ix_insight_summaries_collection_run_id'), 'insight_summaries', ['collection_run_id'], unique=False)
    op.create_index(op.f('ix_insight_summaries_organization_id'), 'insight_summaries', ['organization_id'], unique=False)

    # 2. collection_runs: drop old columns, add new ones
    op.drop_column('collection_runs', 'completed_at')
    op.drop_column('collection_runs', 'status')
    op.drop_column('collection_runs', 'error_summary')

    op.add_column('collection_runs', sa.Column('collection_status', sa.String(length=50), nullable=False, server_default='pending'))
    op.add_column('collection_runs', sa.Column('analysis_status', sa.String(length=50), nullable=False, server_default='not_started'))
    op.add_column('collection_runs', sa.Column('collection_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('collection_runs', sa.Column('analysis_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('collection_runs', sa.Column('analysis_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('collection_runs', sa.Column('collection_error_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('collection_runs', sa.Column('analysis_error_message', sa.Text(), nullable=True))
    op.add_column('collection_runs', sa.Column('analysis_error_trace', sa.Text(), nullable=True))

    # 3. hallucination_results: add collection_run_id FK
    op.add_column('hallucination_results', sa.Column('collection_run_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_hallucination_results_collection_run_id'), 'hallucination_results', ['collection_run_id'], unique=False)
    op.create_foreign_key(None, 'hallucination_results', 'collection_runs', ['collection_run_id'], ['id'])

    # 4. query_results: add rate-limit fields
    op.add_column('query_results', sa.Column('rate_limited', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('query_results', sa.Column('final_error_code', sa.String(length=50), nullable=False, server_default=''))


def downgrade() -> None:
    # query_results
    op.drop_column('query_results', 'final_error_code')
    op.drop_column('query_results', 'rate_limited')

    # hallucination_results
    op.drop_constraint(None, 'hallucination_results', type_='foreignkey')
    op.drop_index(op.f('ix_hallucination_results_collection_run_id'), table_name='hallucination_results')
    op.drop_column('hallucination_results', 'collection_run_id')

    # collection_runs
    op.drop_column('collection_runs', 'analysis_error_trace')
    op.drop_column('collection_runs', 'analysis_error_message')
    op.drop_column('collection_runs', 'collection_error_summary')
    op.drop_column('collection_runs', 'analysis_completed_at')
    op.drop_column('collection_runs', 'analysis_started_at')
    op.drop_column('collection_runs', 'collection_completed_at')
    op.drop_column('collection_runs', 'analysis_status')
    op.drop_column('collection_runs', 'collection_status')

    op.add_column('collection_runs', sa.Column('error_summary', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True))
    op.add_column('collection_runs', sa.Column('status', sa.VARCHAR(length=50), server_default=sa.text("'pending'::character varying"), nullable=True))
    op.add_column('collection_runs', sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), nullable=True))

    # insight_summaries
    op.drop_index(op.f('ix_insight_summaries_organization_id'), table_name='insight_summaries')
    op.drop_index(op.f('ix_insight_summaries_collection_run_id'), table_name='insight_summaries')
    op.drop_index(op.f('ix_insight_summaries_brand_id'), table_name='insight_summaries')
    op.drop_table('insight_summaries')
