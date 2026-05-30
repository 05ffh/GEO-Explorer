"""p1_3_audit_logs

Revision ID: 321a0eb07d90
Revises: 183f525e634d
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '321a0eb07d90'
down_revision: Union[str, Sequence[str], None] = '183f525e634d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID, sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column('user_name', sa.String(255), server_default='', nullable=False),
        sa.Column('user_role', sa.String(50), server_default='', nullable=False),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('target_type', sa.String(100), nullable=False, index=True),
        sa.Column('target_id', sa.String(255), nullable=False, index=True),
        sa.Column('before_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('after_json', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('detail', postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('reason', sa.Text, server_default='', nullable=False),
        sa.Column('result', sa.String(50), server_default='success', nullable=False),
        sa.Column('error_code', sa.String(100), server_default='', nullable=False),
        sa.Column('error_message', sa.Text, server_default='', nullable=False),
        sa.Column('request_id', sa.String(100), server_default='', index=True),
        sa.Column('ip_address', sa.String(50), server_default='', nullable=False),
        sa.Column('user_agent', sa.String(500), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table('audit_logs')
