"""add_gt_candidate_evidence_review_content_package

Revision ID: 1225dbebd7ea
Revises: 3edb95c7f8d2
Create Date: 2026-05-29 13:51:06.096539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1225dbebd7ea'
down_revision: Union[str, Sequence[str], None] = '3edb95c7f8d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('content_packages',
        sa.Column('action_plan_id', sa.UUID(), nullable=True),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('content_items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('schema_items', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('publishing_checklist', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fact_check_report', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['action_plan_id'], ['action_plans.id'], ),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_content_packages_brand_id'), 'content_packages', ['brand_id'], unique=False)
    op.create_index(op.f('ix_content_packages_organization_id'), 'content_packages', ['organization_id'], unique=False)

    op.create_table('gt_candidates',
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('collection_run_id', sa.UUID(), nullable=True),
        sa.Column('candidate_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('confidence_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('overall_confidence', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewer_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['collection_run_id'], ['collection_runs.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gt_candidates_brand_id'), 'gt_candidates', ['brand_id'], unique=False)
    op.create_index(op.f('ix_gt_candidates_organization_id'), 'gt_candidates', ['organization_id'], unique=False)

    op.create_table('gt_evidences',
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('source_name', sa.String(length=255), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=False),
        sa.Column('source_quality', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.String(length=20), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['gt_candidates.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gt_evidences_candidate_id'), 'gt_evidences', ['candidate_id'], unique=False)

    op.create_table('gt_reviews',
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('reviewer_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('field_changes_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('review_notes', sa.Text(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['gt_candidates.id'], ),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gt_reviews_candidate_id'), 'gt_reviews', ['candidate_id'], unique=False)

    op.add_column('ground_truth_versions', sa.Column('required_fields_complete', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('ground_truth_versions', sa.Column('user_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('ground_truth_versions', sa.Column('high_risk_fields_reviewed', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('ground_truth_versions', sa.Column('gt_coverage_rate', sa.Float(), nullable=False, server_default=sa.text('0.0')))


def downgrade() -> None:
    op.drop_column('ground_truth_versions', 'gt_coverage_rate')
    op.drop_column('ground_truth_versions', 'high_risk_fields_reviewed')
    op.drop_column('ground_truth_versions', 'user_confirmed')
    op.drop_column('ground_truth_versions', 'required_fields_complete')

    op.drop_index(op.f('ix_gt_reviews_candidate_id'), table_name='gt_reviews')
    op.drop_table('gt_reviews')
    op.drop_index(op.f('ix_gt_evidences_candidate_id'), table_name='gt_evidences')
    op.drop_table('gt_evidences')
    op.drop_index(op.f('ix_gt_candidates_organization_id'), table_name='gt_candidates')
    op.drop_index(op.f('ix_gt_candidates_brand_id'), table_name='gt_candidates')
    op.drop_table('gt_candidates')
    op.drop_index(op.f('ix_content_packages_organization_id'), table_name='content_packages')
    op.drop_index(op.f('ix_content_packages_brand_id'), table_name='content_packages')
    op.drop_table('content_packages')
