"""final_ship_deletion_receipt

Revision ID: 0da168569f6d
Revises: b1c2d3e4f5a6
Create Date: 2026-05-31

Covers all 收尾轮 model changes:
- DeletionReceipt table
- DataDeletionRequest: failed_table, failed_reason, last_processed_id, retry_count, status VARCHAR(30)
- User: email_verified
- server_default fixes for Organization and User
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0da168569f6d'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── DataDeletionRequest: new columns + status resize ──
    op.add_column('data_deletion_requests',
                  sa.Column('failed_table', sa.String(100), nullable=True))
    op.add_column('data_deletion_requests',
                  sa.Column('failed_reason', sa.Text(), nullable=True))
    op.add_column('data_deletion_requests',
                  sa.Column('last_processed_id', sa.String(255), nullable=True))
    op.add_column('data_deletion_requests',
                  sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False))
    op.alter_column('data_deletion_requests', 'status',
                    existing_type=sa.String(20), type_=sa.String(30), existing_nullable=False)

    # ── DeletionReceipt table ──
    op.create_table('deletion_receipts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('deletion_request_id', sa.UUID(), nullable=False),
        sa.Column('organization_id', sa.UUID(), nullable=False),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=True),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('approved_by', sa.UUID(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('affected_tables_json', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('deleted_counts_json', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('anonymized_counts_json', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('retained_items_json', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('file_deleted_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('file_failed_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed_assets_json', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('backup_expiry_note', sa.Text(), server_default='Backups will expire according to backup retention policy.', nullable=False),
        sa.Column('receipt_hash', sa.String(64), nullable=False),
        sa.Column('audit_log_refs_json', postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ),
        sa.ForeignKeyConstraint(['deletion_request_id'], ['data_deletion_requests.id'], ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deletion_request_id', name='uq_deletion_receipt_request'),
    )
    op.create_index('ix_receipt_org', 'deletion_receipts', ['organization_id'])

    # ── User: email_verified ──
    op.add_column('users',
                  sa.Column('email_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False))

    # ── Organization: server_default fixes (columns already exist in prod via b1c2d3e4f5a6) ──
    op.alter_column('organizations', 'brand_count', server_default=sa.text('0'))
    op.alter_column('organizations', 'user_count', server_default=sa.text('0'))
    op.alter_column('organizations', 'onboarding_step', server_default=sa.text('0'))
    op.alter_column('organizations', 'plan', server_default=sa.text("'free'"))
    op.alter_column('organizations', 'is_active', server_default=sa.text('true'))

    # ── User: platform field server_default fixes ──
    op.alter_column('users', 'platform_mfa_required', server_default=sa.text('false'))
    op.alter_column('users', 'platform_access_enabled', server_default=sa.text('true'))


def downgrade() -> None:
    # ── User platform fields ──
    op.alter_column('users', 'platform_access_enabled', server_default=None)
    op.alter_column('users', 'platform_mfa_required', server_default=None)

    # ── Organization server_default removal ──
    op.alter_column('organizations', 'is_active', server_default=None)
    op.alter_column('organizations', 'plan', server_default=None)
    op.alter_column('organizations', 'onboarding_step', server_default=None)
    op.alter_column('organizations', 'user_count', server_default=None)
    op.alter_column('organizations', 'brand_count', server_default=None)

    # ── User email_verified ──
    op.drop_column('users', 'email_verified')

    # ── DeletionReceipt table ──
    op.drop_index('ix_receipt_org', table_name='deletion_receipts')
    op.drop_table('deletion_receipts')

    # ── DataDeletionRequest columns ──
    op.alter_column('data_deletion_requests', 'status',
                    existing_type=sa.String(30), type_=sa.String(20), existing_nullable=False)
    op.drop_column('data_deletion_requests', 'retry_count')
    op.drop_column('data_deletion_requests', 'last_processed_id')
    op.drop_column('data_deletion_requests', 'failed_reason')
    op.drop_column('data_deletion_requests', 'failed_table')
