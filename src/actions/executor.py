import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.ground_truth import GroundTruthVersion
from src.models.action_plan import ActionPlan
from src.config import settings

logger = logging.getLogger(__name__)

CONTENT_PROMPT = """基于以下 Ground Truth 生成内容。只能使用已确认字段。不得虚构客户、融资、奖项。不得使用"领先""第一""最大"。涉及竞品保持客观。事实性段落标注来源字段。不确定信息省略。
GT: {active_gt_json}
生成: {content_type}"""


async def generate_content_package(
    action_plan_id: str, db: AsyncSession,
) -> dict:
    """Generate Content Package from an ActionPlan using active GT.

    Pipeline: ActionPlan → active GT → LLM content gen → fact check → schema gen → ContentPackage.
    Returns dict ready for user review.
    """
    action_plan = (await db.execute(
        select(ActionPlan).where(ActionPlan.id == action_plan_id)
    )).scalar_one_or_none()
    if not action_plan:
        raise ValueError("Action plan not found")

    active_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == action_plan.brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().first()

    if not active_gt:
        raise ValueError("No active Ground Truth found. Please complete GT before generating content.")

    # Build prompt from GT
    import json
    gt_json = json.dumps(active_gt.ground_truth_json, ensure_ascii=False)
    content_type = action_plan.suggested_content_type or "FAQ"
    prompt = CONTENT_PROMPT.format(active_gt_json=gt_json, content_type=content_type)

    # Generate content using LLM (uses first available platform from config)
    content_items = await _generate_with_llm(prompt, content_type)

    # Fact check against GT
    from src.actions.fact_checker import check_content_against_gt
    fact_check_report = check_content_against_gt(content_items, active_gt.ground_truth_json)

    # Generate Schema.org JSON-LD
    from src.actions.schema_generator import generate_jsonld
    brand_name = active_gt.ground_truth_json.get("official_name", "Unknown")
    schema_result = generate_jsonld(brand_name, active_gt.ground_truth_json, content_type)

    # Build ContentPackage
    from src.actions.content_package import build_content_package
    pkg = await build_content_package(
        action_plan_id=str(action_plan.id),
        brand_id=str(action_plan.brand_id),
        org_id=str(action_plan.organization_id),
        content_items=content_items,
        schema_items=schema_result["schemas"],
        fact_check_report=fact_check_report,
        db=db,
    )

    from src.actions.content_package import export_content_package
    return export_content_package(pkg)


async def _generate_with_llm(prompt: str, content_type: str) -> list[dict]:
    """Generate content using available AI platform adapter."""
    from src.adapters import get_adapter

    for platform in ["deepseek", "kimi", "doubao"]:
        try:
            adapter = get_adapter(platform)
            response = await adapter.query(prompt)
            if response.answer_text:
                return [{
                    "type": content_type,
                    "title": f"{content_type} Content",
                    "body": response.answer_text,
                    "platform": platform,
                }]
        except Exception as e:
            logger.warning("Content generation failed for %s: %s", platform, e)

    # Fallback: return structured placeholder
    return [{
        "type": content_type,
        "title": f"{content_type} Content",
        "body": f"Content based on Ground Truth. Type: {content_type}",
        "platform": "fallback",
    }]
