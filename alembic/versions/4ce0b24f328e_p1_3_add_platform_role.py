"""p1_3_add_platform_role

Revision ID: 4ce0b24f328e
Revises: 321a0eb07d90
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '4ce0b24f328e'
down_revision: Union[str, Sequence[str], None] = '321a0eb07d90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('platform_role', sa.String(50), nullable=True))
    # system_owner / system_admin / system_operator / None(=org member)
    op.create_index('ix_users_platform_role', 'users', ['platform_role'])


def downgrade() -> None:
    op.drop_index('ix_users_platform_role', 'users')
    op.drop_column('users', 'platform_role')
