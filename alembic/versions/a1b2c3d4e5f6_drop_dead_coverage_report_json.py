"""drop dead coverage_report_json from collection_runs

Revision ID: a1b2c3d4e5f6
Revises: cd070fd24b65
Create Date: 2026-10-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'cd070fd24b65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop 死列 coverage_report_json（零写零读，旧系统残留；2026-10-13 核实删除）。"""
    op.drop_column('collection_runs', 'coverage_report_json')


def downgrade() -> None:
    """Restore 可空列。"""
    op.add_column('collection_runs', sa.Column(
        'coverage_report_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
