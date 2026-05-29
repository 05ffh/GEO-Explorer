import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.content_package import ContentPackage
from src.models.ground_truth import GroundTruthVersion

logger = logging.getLogger(__name__)

PUBLISHING_CHECKLIST = [
    "所有内容字段已从已确认的 Ground Truth 中提取",
    "无禁止性表述（领先/第一/最大等）",
    "Schema.org JSON-LD 格式有效",
    "事实性声明有 GT 字段支撑",
    "内容符合品牌风格和语调",
    "所有链接已验证可访问",
]


async def build_content_package(
    action_plan_id: str,
    brand_id: str,
    org_id: str,
    content_items: list[dict],
    schema_items: list[dict],
    fact_check_report: dict,
    db: AsyncSession,
) -> ContentPackage:
    """Build a ContentPackage from generated content, schemas, and fact-check results."""

    # Verify active GT exists
    active_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().first()

    if not active_gt:
        raise ValueError("No active Ground Truth found for this brand")

    pkg = ContentPackage(
        action_plan_id=action_plan_id,
        organization_id=org_id,
        brand_id=brand_id,
        content_items=content_items,
        schema_items=schema_items,
        publishing_checklist=[{"item": c, "checked": False} for c in PUBLISHING_CHECKLIST],
        fact_check_report=fact_check_report,
        status="draft",
    )
    db.add(pkg)
    await db.commit()
    return pkg


def export_content_package(pkg: ContentPackage) -> dict:
    """Export ContentPackage as Markdown + JSON-LD + Checklist."""
    md_parts = []
    for item in pkg.content_items:
        if isinstance(item, dict):
            title = item.get("title", item.get("type", "Content"))
            body = item.get("body", "")
            md_parts.append(f"## {title}\n\n{body}\n")

    return {
        "markdown": "\n".join(md_parts),
        "json_ld": pkg.schema_items,
        "checklist": pkg.publishing_checklist,
        "fact_check": pkg.fact_check_report,
        "status": pkg.status,
    }
