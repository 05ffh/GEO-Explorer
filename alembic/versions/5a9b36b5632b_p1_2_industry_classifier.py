"""p1_2_industry_classifier

Revision ID: 5a9b36b5632b
Revises: de5fed16ec18
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '5a9b36b5632b'
down_revision: Union[str, Sequence[str], None] = 'de5fed16ec18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'industry_classification_results',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column('run_id', postgresql.UUID, nullable=True),
        sa.Column('recommended_primary_template_id', postgresql.UUID, sa.ForeignKey("industry_templates.id"), nullable=True),
        sa.Column('recommended_secondary_template_ids', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('confidence', sa.String(20), server_default='medium', nullable=False),
        sa.Column('confidence_score', sa.Float(), server_default=sa.text('0.0'), nullable=False),
        sa.Column('alternative_templates', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('business_model_tags', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('evidence_json', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('conflicts_json', postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('needs_user_confirmation', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('user_confirmed', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('confirmed_by', postgresql.UUID, nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('industry_classification_results')
