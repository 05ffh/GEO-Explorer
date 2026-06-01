"""phase_a_quality_fields

Revision ID: 700124a47f1c
Revises: 84ee2d3cb711
Create Date: 2026-06-01 18:39:58.497324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '700124a47f1c'
down_revision: Union[str, Sequence[str], None] = '84ee2d3cb711'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CollectionRun columns
    op.add_column(
        'collection_runs',
        sa.Column('report_quality_summary_json', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False)
    )
    op.add_column(
        'collection_runs',
        sa.Column('template_health_report_json', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'{}'::jsonb"), nullable=False)
    )
    op.add_column(
        'collection_runs',
        sa.Column('report_publishable', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False)
    )
    op.add_column(
        'collection_runs',
        sa.Column('blocking_reasons_json', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'[]'::jsonb"), nullable=False)
    )
    op.create_index('ix_collection_runs_report_publishable', 'collection_runs', ['report_publishable'])

    # QueryTemplate columns
    op.add_column(
        'query_templates',
        sa.Column('template_level', sa.String(20),
                  server_default='important', nullable=False)
    )
    op.add_column(
        'query_templates',
        sa.Column('question_scope', sa.String(30), nullable=True)
    )
    # question_type column may already exist in some databases (added directly);
    # use IF NOT EXISTS to make the migration idempotent across environments.
    op.execute(
        "ALTER TABLE query_templates ADD COLUMN IF NOT EXISTS "
        "question_type VARCHAR(50)"
    )
    op.create_index('ix_query_templates_question_type', 'query_templates', ['question_type'])
    op.create_index('ix_query_templates_template_level', 'query_templates', ['template_level'])

    # HallucinationResult columns
    op.add_column(
        'hallucination_results',
        sa.Column('claim_text', sa.Text(),
                  server_default='', nullable=False)
    )
    op.add_column(
        'hallucination_results',
        sa.Column('subject_type', sa.String(50),
                  server_default='', nullable=False)
    )
    op.add_column(
        'hallucination_results',
        sa.Column('matched_gt_field', sa.String(100),
                  server_default='', nullable=False)
    )
    op.add_column(
        'hallucination_results',
        sa.Column('reason', sa.Text(),
                  server_default='', nullable=False)
    )
    op.add_column(
        'hallucination_results',
        sa.Column('needs_human_review', sa.Boolean(),
                  server_default=sa.text('false'), nullable=False)
    )
    op.create_index('ix_hallucination_results_subject_type', 'hallucination_results', ['subject_type'])
    op.create_index('ix_hallucination_results_severity', 'hallucination_results', ['severity'])


def downgrade() -> None:
    # HallucinationResult indexes and columns
    op.drop_index('ix_hallucination_results_severity', table_name='hallucination_results')
    op.drop_index('ix_hallucination_results_subject_type', table_name='hallucination_results')
    op.drop_column('hallucination_results', 'needs_human_review')
    op.drop_column('hallucination_results', 'reason')
    op.drop_column('hallucination_results', 'matched_gt_field')
    op.drop_column('hallucination_results', 'subject_type')
    op.drop_column('hallucination_results', 'claim_text')

    # QueryTemplate indexes and columns
    op.drop_index('ix_query_templates_template_level', table_name='query_templates')
    op.drop_index('ix_query_templates_question_type', table_name='query_templates')
    op.drop_column('query_templates', 'question_scope')
    op.drop_column('query_templates', 'template_level')

    # CollectionRun indexes and columns
    op.drop_index('ix_collection_runs_report_publishable', table_name='collection_runs')
    op.drop_column('collection_runs', 'blocking_reasons_json')
    op.drop_column('collection_runs', 'report_publishable')
    op.drop_column('collection_runs', 'template_health_report_json')
    op.drop_column('collection_runs', 'report_quality_summary_json')
