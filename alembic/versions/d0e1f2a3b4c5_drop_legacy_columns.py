"""drop legacy columns from collection_runs (old system cleanup 阶段2)

旧 Web/Celery/KPI/报告架构遗留列——新 CLI 系统零消费（状态从 JSON 派生）。
三重验证：可达性 BFS + 全仓裸词 grep + 无动态访问（2026-10-15）。

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-10-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = postgresql.JSONB(astext_type=sa.Text())

# 列名 → 重建规格（供 downgrade 用）
_SPEC = {
    "trigger_type": lambda: sa.Column("trigger_type", sa.String(50)),
    "collection_status": lambda: sa.Column("collection_status", sa.String(50)),
    "analysis_status": lambda: sa.Column("analysis_status", sa.String(50)),
    "started_at": lambda: sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    "collection_completed_at": lambda: sa.Column("collection_completed_at", sa.DateTime(timezone=True), nullable=True),
    "analysis_started_at": lambda: sa.Column("analysis_started_at", sa.DateTime(timezone=True), nullable=True),
    "analysis_completed_at": lambda: sa.Column("analysis_completed_at", sa.DateTime(timezone=True), nullable=True),
    "total_queries": lambda: sa.Column("total_queries", sa.Integer()),
    "success_count": lambda: sa.Column("success_count", sa.Integer()),
    "failure_count": lambda: sa.Column("failure_count", sa.Integer()),
    "execution_mode": lambda: sa.Column("execution_mode", sa.String(20)),
    "collection_error_summary": lambda: sa.Column("collection_error_summary", _JSONB, nullable=True),
    "analysis_error_message": lambda: sa.Column("analysis_error_message", sa.Text(), nullable=True),
    "analysis_error_trace": lambda: sa.Column("analysis_error_trace", sa.Text(), nullable=True),
    "platform_status_json": lambda: sa.Column("platform_status_json", _JSONB),
    "progress_json": lambda: sa.Column("progress_json", _JSONB),
    "analysis_skipped_reason": lambda: sa.Column("analysis_skipped_reason", sa.Text(), nullable=True),
    "template_version_ids": lambda: sa.Column("template_version_ids", _JSONB),
    "preflight_summary_json": lambda: sa.Column("preflight_summary_json", _JSONB),
    "report_quality_summary_json": lambda: sa.Column("report_quality_summary_json", _JSONB),
    "template_health_report_json": lambda: sa.Column("template_health_report_json", _JSONB),
    "report_publishable": lambda: sa.Column("report_publishable", sa.Boolean()),
    "blocking_reasons_json": lambda: sa.Column("blocking_reasons_json", _JSONB),
}


def upgrade() -> None:
    """Upgrade schema."""
    for col in _SPEC:
        op.drop_column("collection_runs", col)


def downgrade() -> None:
    """Downgrade schema."""
    for col, make in _SPEC.items():
        op.add_column("collection_runs", make())
