"""drop legacy tables (old system cleanup)

Revision ID: cd070fd24b65
Revises: b8c9d0e1f2a3
Create Date: 2026-10-12 21:03:43.567913

删除旧系统（web/SaaS：内容工厂 / 幻觉 / KPI / 报告投递 / RBAC / 用户 / 模板）遗留的
22 张表 + 保留 model 上残留的旧外键列（brands.created_by/updated_by、
collection_runs.prompt_version_id）。这些表/列新系统零使用（实测：代码零引用、
FK 列从不写、旧表 0 行数据）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cd070fd24b65'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 旧系统遗留表（全部 0 行、新系统零引用）
_LEGACY_TABLES = (
    "content_publish_records", "cost_alerts", "prompt_versions", "users",
    "query_template_versions", "hallucination_results", "content_packages",
    "query_templates", "api_usage_logs", "usage_budgets", "model_pricing",
    "recheck_records", "action_plans", "content_library", "report_brandings",
    "metrics_snapshots", "action_themes", "competitor_sets", "query_results",
    "audit_logs", "insight_summaries", "diagnostic_runs",
)


def upgrade() -> None:
    """删旧表 + 保留 model 上的旧外键列。"""
    # 保留 model 上的旧 FK 列（brands→users、collection_runs→prompt_versions）
    op.drop_constraint("brands_updated_by_fkey", "brands", type_="foreignkey")
    op.drop_constraint("brands_created_by_fkey", "brands", type_="foreignkey")
    op.drop_column("brands", "updated_by")
    op.drop_column("brands", "created_by")
    op.drop_constraint("collection_runs_prompt_version_id_fkey", "collection_runs", type_="foreignkey")
    op.drop_column("collection_runs", "prompt_version_id")
    # 一次 CASCADE 清全部旧表（表间互相 FK，逐张删需按序；CASCADE 一次到位）
    op.execute("DROP TABLE IF EXISTS " + ", ".join(_LEGACY_TABLES) + " CASCADE")


def downgrade() -> None:
    """不可逆：旧表已删除（model 也删了），如需恢复从基线迁移重建。"""
    raise NotImplementedError("drop legacy tables 不可逆；恢复请从基线迁移 c0221e24d7d4 重建")
