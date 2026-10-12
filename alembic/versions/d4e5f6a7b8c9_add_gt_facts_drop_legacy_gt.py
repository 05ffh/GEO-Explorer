"""add collection_runs.gt_facts_json; drop legacy GT tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-16

用户 2026-09-16：GT 事实重新整理（方案 C）——新系统 GT 事实用 search_results.content_text +
结构化清单存 collection_runs.gt_facts_json；旧系统 GT 事实表（ground_truth_versions/
gt_candidates/gt_evidences/gt_reviews，均 0 行空表）删除。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新系统结构化 GT 事实清单（诊断单元级，与 positioning/sentiment 同级）
    op.add_column('collection_runs',
                  sa.Column('gt_facts_json', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    # 旧系统 GT 外键（全 NULL）→ 去列
    op.drop_column('collection_runs', 'ground_truth_version_id')
    # 删旧 GT 事实表（CASCADE 处理仍指向它们的 FK：hallucination/metrics_snapshot/api_usage）
    for t in ('gt_reviews', 'gt_evidences', 'gt_candidates', 'ground_truth_versions'):
        op.execute(f'DROP TABLE IF EXISTS {t} CASCADE')


def downgrade() -> None:
    # 重建旧 GT 表（空结构，旧系统残留，无数据可恢复）
    op.create_table(
        'ground_truth_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('brand_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('brands.id'), nullable=False),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('ground_truth_json', postgresql.JSONB(), default=dict),
        sa.Column('source_urls', postgresql.ARRAY(sa.Text()), default=list),
        sa.Column('reviewer', sa.String(255), default=''),
        sa.Column('status', sa.String(50), default='draft'),
        sa.Column('required_fields_complete', sa.Boolean(), default=False),
        sa.Column('user_confirmed', sa.Boolean(), default=False),
        sa.Column('high_risk_fields_reviewed', sa.Boolean(), default=False),
        sa.Column('gt_coverage_rate', sa.Float(), default=0.0),
        sa.Column('gt_schema_version', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'gt_candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('brand_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('brands.id'), nullable=False),
        sa.Column('collection_run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('collection_runs.id'), nullable=True),
        sa.Column('candidate_json', postgresql.JSONB(), default=dict),
        sa.Column('confidence_summary', postgresql.JSONB(), default=dict),
        sa.Column('overall_confidence', sa.String(20), default='unverified'),
        sa.Column('status', sa.String(50), default='pending_review'),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'gt_evidences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('gt_candidates.id'), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('value', sa.Text(), default=''),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('source_name', sa.String(255), default=''),
        sa.Column('source_url', sa.Text(), default=''),
        sa.Column('excerpt', sa.Text(), default=''),
        sa.Column('source_tier', sa.String(10), default='T3'),
        sa.Column('source_quality', sa.String(20), default='low'),
        sa.Column('confidence', sa.String(20), default='unverified'),
        sa.Column('human_confirmed', sa.Boolean(), default=False),
        sa.Column('review_status', sa.String(20), default='pending'),
        sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'gt_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('gt_candidates.id'), nullable=False),
        sa.Column('reviewer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('field_changes_json', postgresql.JSONB(), default=dict),
        sa.Column('review_notes', sa.Text(), default=''),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column('collection_runs',
                  sa.Column('ground_truth_version_id', postgresql.UUID(as_uuid=True),
                            sa.ForeignKey('ground_truth_versions.id'), nullable=True))
    op.drop_column('collection_runs', 'gt_facts_json')
