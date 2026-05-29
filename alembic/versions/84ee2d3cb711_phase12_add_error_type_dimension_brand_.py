"""phase12_add_error_type_dimension_brand_mentioned_title

Revision ID: 84ee2d3cb711
Revises: 049179315f7a
Create Date: 2026-05-29 23:33:51.974858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84ee2d3cb711'
down_revision: Union[str, Sequence[str], None] = '049179315f7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 4 columns needed by Phase 12 Dashboard
    op.add_column('hallucination_results', sa.Column('error_type', sa.String(50), server_default='', nullable=False))
    op.add_column('query_results', sa.Column('dimension', sa.String(100), server_default='', nullable=False))
    op.add_column('query_results', sa.Column('brand_mentioned', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('content_packages', sa.Column('title', sa.String(255), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('content_packages', 'title')
    op.drop_column('query_results', 'brand_mentioned')
    op.drop_column('query_results', 'dimension')
    op.drop_column('hallucination_results', 'error_type')
