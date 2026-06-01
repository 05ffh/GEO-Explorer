"""p1_6_report_artifact

Revision ID: c1d2e3f4a5b6
Revises: b1a2c3d4e5f6
Create Date: 2026-05-30

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b1a2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_artifacts',
        sa.Column('id', postgresql.UUID, primary_key=True),
        sa.Column('brand_id', postgresql.UUID, sa.ForeignKey("brands.id"), nullable=False, index=True),
        sa.Column('organization_id', postgresql.UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column('collection_run_id', postgresql.UUID, sa.ForeignKey("collection_runs.id"), nullable=False),
        sa.Column('edition', sa.String(30), nullable=False),
        sa.Column('format', sa.String(10), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('file_hash', sa.String(128), nullable=True),
        sa.Column('report_version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('template_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('language_version', sa.String(20), server_default='1.0', nullable=False),
        sa.Column('industry_template_id', postgresql.UUID, sa.ForeignKey("industry_templates.id"), nullable=True),
        sa.Column('status', sa.String(30), server_default='not_generated', nullable=False, index=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('quality_status', sa.String(20), nullable=True),
        sa.Column('quality_report_json', postgresql.JSONB, nullable=True),
        sa.Column('download_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_downloaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stale_reason', sa.String(500), nullable=True),
        sa.Column('superseded_by_report_id', postgresql.UUID, sa.ForeignKey("report_artifacts.id"), nullable=True),
        sa.Column('generation_key', sa.String(255), nullable=True, index=True),
        sa.Column('generated_by', postgresql.UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('context_snapshot', postgresql.JSONB, nullable=True),
        sa.Column('locale', sa.String(10), server_default='zh-CN', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('report_artifacts')
