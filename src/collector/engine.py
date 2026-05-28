import asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.adapters import get_adapter
from src.config import settings
from src.models.brand import Brand
from src.models.query_template import QueryTemplate
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.api_usage import ApiUsage
from src.models.prompt_version import PromptVersion
from src.models.ground_truth import GroundTruthVersion

PLATFORMS = ["deepseek", "kimi", "doubao", "wenxin"]


async def run_collection(
    brand_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
    trigger_type: str = "manual",
) -> CollectionRun:
    brand = (await db.execute(
        select(Brand).where(Brand.id == brand_id, Brand.organization_id == org_id)
    )).scalar_one_or_none()
    if not brand:
        raise ValueError("Brand not found")

    templates = (await db.execute(
        select(QueryTemplate).where(
            (QueryTemplate.organization_id == org_id) | (QueryTemplate.organization_id.is_(None)),
            QueryTemplate.is_active == True,  # noqa: E712
        )
    )).scalars().all()

    active_prompt = (await db.execute(
        select(PromptVersion).where(PromptVersion.status == "active")
    )).scalars().first()

    active_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().first()

    run = CollectionRun(
        organization_id=org_id,
        brand_id=brand_id,
        prompt_version_id=active_prompt.id if active_prompt else None,
        ground_truth_version_id=active_gt.id if active_gt else None,
        trigger_type=trigger_type,
        status="running",
        started_at=datetime.utcnow(),
        total_queries=len(PLATFORMS) * len(templates),
    )
    db.add(run)
    await db.flush()

    sem = asyncio.Semaphore(settings.collector_concurrency)

    async def query_one(platform_name, tmpl):
        async with sem:
            adapter = get_adapter(platform_name)
            question = tmpl.template_text
            for alias in brand.aliases or []:
                question = question.replace(f"{{{alias}}}", alias)
            question = question.replace("{品牌}", brand.name)
            question = question.replace("{行业}", brand.industry)

            system = active_prompt.system_prompt if active_prompt else "你是一个诚实的AI助手。"
            result = await adapter.query(question, system_prompt=system)
            return result, platform_name, tmpl

    jobs = [query_one(p, t) for p in PLATFORMS for t in templates]
    responses = await asyncio.gather(*jobs, return_exceptions=True)

    for result in responses:
        if isinstance(result, Exception):
            continue
        response, platform_name, tmpl = result
        qr = QueryResult(
            brand_id=brand_id,
            organization_id=org_id,
            collection_run_id=run.id,
            platform=platform_name,
            template_id=tmpl.id,
            prompt_version_id=active_prompt.id if active_prompt else None,
            question=response.question,
            answer_text=response.answer_text,
            citations=[{"url": c.url, "type": c.type, "context": c.context}
                       for c in response.citations],
            model_name=response.model_name,
            model_version=response.model_version,
            response_raw_json=response.raw_response,
            status="error" if response.error else "success",
            error_message=response.error or "",
            latency_ms=response.latency_ms,
            collected_at=datetime.utcnow(),
        )
        db.add(qr)
        await db.flush()

        usage = ApiUsage(
            organization_id=org_id,
            brand_id=brand_id,
            collection_run_id=run.id,
            platform=platform_name,
            query_result_id=qr.id,
            prompt_tokens=len(response.question) // 4,
            completion_tokens=len(response.answer_text) // 4 if response.answer_text else 0,
            cost=0,
            status="failed" if response.error else "success",
        )
        db.add(usage)

    success_count = sum(
        1 for r in responses
        if not isinstance(r, Exception) and not r[0].error
    )
    failure_count = run.total_queries - success_count
    run.success_count = success_count
    run.failure_count = failure_count
    run.status = (
        "completed" if failure_count == 0
        else "failed" if failure_count == run.total_queries
        else "partial"
    )
    run.completed_at = datetime.utcnow()
    await db.commit()
    return run
