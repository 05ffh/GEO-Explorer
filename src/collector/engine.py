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

TEMPLATE_LEVEL_MAP = {
    "brand_definition": "critical",
    "brand_attribute": "critical",
    "brand_comparison": "important",
    "brand_trust": "important",
    "category_recommendation": "optional",
    "scenario_solution": "optional",
    "user_recommendation": "optional",
    "generic_advice": "optional",
}


def _build_template_health_report(preflight_results: list) -> dict:
    """Build TemplateHealthReport from preflight results with corrected counting."""
    from datetime import datetime, timezone

    def _level(r):
        qt = getattr(r, 'question_type', None)
        if qt is None:
            tmpl = getattr(r, 'template', None)
            qt = getattr(tmpl, 'question_type', 'brand_definition') if tmpl else 'brand_definition'
        return TEMPLATE_LEVEL_MAP.get(qt, "important")

    total = len(preflight_results) if preflight_results else 0
    invalid = [r for r in (preflight_results or []) if getattr(r, 'render_status', None) != "ok"]
    skipped = [r for r in (preflight_results or []) if getattr(r, 'render_status', None) == "skipped_missing_variable"]

    critical_invalid = [r for r in invalid if _level(r) == "critical"]
    important_invalid = [r for r in invalid if _level(r) == "important"]
    optional_skipped = [r for r in skipped if _level(r) == "optional"]

    invalid_ratio = len(invalid) / total if total > 0 else 0.0

    return {
        "schema_version": "template_health_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_templates": total,
        "valid_templates": total - len(invalid),
        "invalid_templates": len(invalid),
        "skipped_templates": len(skipped),
        "critical_invalid": len(critical_invalid),
        "important_invalid": len(important_invalid),
        "optional_skipped": len(optional_skipped),
        "blocking_invalid_templates": len(critical_invalid) + len(important_invalid),
        "non_blocking_skipped_templates": len(optional_skipped),
        "invalid_ratio": round(invalid_ratio, 4),
        "missing_variables": _aggregate_missing_vars(invalid),
        "can_collect": invalid_ratio <= 0.20,
        "can_publish_report": len(critical_invalid) == 0,
    }


def _aggregate_missing_vars(invalid_results: list) -> dict:
    """Aggregate unresolved variables from invalid preflight results."""
    result = {}
    for r in invalid_results:
        unresolved = getattr(r, 'unresolved_variables', [])
        for v in unresolved:
            result[v] = result.get(v, 0) + 1
    return result


async def run_collection(
    brand_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
    trigger_type: str = "manual",
    auto_analyze: bool = True,
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
        collection_status="running",
        started_at=datetime.utcnow(),
        total_queries=len(PLATFORMS) * len(templates),
    )
    db.add(run)
    await db.flush()

    # --- Preflight: template health + coverage ---
    from src.analyzer.hallucination import _UNRESOLVED_VAR_RE

    # GT-derived variable expansion
    _GT_VAR_MAP = {
        "{品类}": "category",
        "{竞品}": "target_competitors",
        "{场景}": "core_scenarios",
        "{目标用户}": "target_users",
    }

    class _PreflightResult:
        __slots__ = ("template", "render_status", "unresolved_variables", "question_type")
        def __init__(self, template, status, unresolved, qtype):
            self.template = template
            self.render_status = status
            self.unresolved_variables = unresolved
            self.question_type = qtype

    _gt_json = {}
    if active_gt and active_gt.ground_truth_json:
        _gt_json = active_gt.ground_truth_json

    def _expand_vars(text: str) -> str:
        for alias in brand.aliases or []:
            text = text.replace(f"{{{alias}}}", alias)
        text = text.replace("{品牌}", brand.name)
        text = text.replace("{行业}", brand.industry or "")
        for _var, _gt_key in _GT_VAR_MAP.items():
            _val = _gt_json.get(_gt_key, "")
            if isinstance(_val, list):
                _val = "、".join(str(v) for v in _val)
            text = text.replace(_var, str(_val) if _val else _var)
        return text

    preflight_results = []
    for _t in templates:
        _question = _expand_vars(_t.template_text)
        _unresolved = _UNRESOLVED_VAR_RE.findall(_question)
        _status = "ok" if not _unresolved else "missing_variable"
        preflight_results.append(_PreflightResult(
            template=_t, status=_status,
            unresolved=_unresolved,
            qtype=getattr(_t, "question_type", "brand_definition"),
        ))

    health_report = _build_template_health_report(preflight_results)
    run.template_health_report_json = health_report

    # Coverage: count templates by question_type and platform
    qtype_counts = {}
    for _t in templates:
        _qt = getattr(_t, "question_type", "brand_definition")
        qtype_counts[_qt] = qtype_counts.get(_qt, 0) + 1
    active_platforms = settings.platform_concurrency_limits or {
        "deepseek": 3, "kimi": 3, "doubao": 2, "wenxin": 1,
    }
    platform_coverage = {
        p: len(templates) for p in active_platforms
    }
    total_templates = len(templates)
    valid_templates = health_report.get("valid_templates", total_templates)
    run.coverage_report_json = {
        "raw_coverage": total_templates / max(total_templates, 1),
        "valid_answer_coverage": valid_templates / max(total_templates, 1),
        "metric_eligible_coverage": valid_templates / max(total_templates, 1),
        "platform_coverage": platform_coverage,
        "qtype_distribution": qtype_counts,
    }
    await db.flush()
    # --- End preflight ---

    _platform_semaphores = {
        p: asyncio.Semaphore(settings.platform_concurrency_limits.get(p, 4))
        for p in PLATFORMS
    }

    _gt_json = {}
    if active_gt and active_gt.ground_truth_json:
        _gt_json = active_gt.ground_truth_json

    def _build_question(tmpl):
        question = tmpl.template_text
        for alias in brand.aliases or []:
            question = question.replace(f"{{{alias}}}", alias)
        question = question.replace("{品牌}", brand.name)
        question = question.replace("{行业}", brand.industry or "")
        for _var, _gt_key in _GT_VAR_MAP.items():
            _val = _gt_json.get(_gt_key, "")
            if isinstance(_val, list):
                _val = "、".join(str(v) for v in _val)
            question = question.replace(_var, str(_val) if _val else _var)
        return question

    system = active_prompt.system_prompt if active_prompt else "你是一个诚实的AI助手。"

    async def query_one(platform_name, tmpl):
        sem = _platform_semaphores[platform_name]
        retry_cfg = settings.platform_retry_config.get(
            platform_name, {"max_retries": 2, "backoff_seconds": [1, 2]}
        )
        max_retries = retry_cfg["max_retries"]
        backoffs = retry_cfg["backoff_seconds"]

        adapter = get_adapter(platform_name)
        question = _build_question(tmpl)

        retry_count = 0
        rate_limited = False
        final_error_code = ""
        response = None

        for attempt in range(max_retries + 1):
            async with sem:
                response = await adapter.query(question, system_prompt=system)

            if not response.error:
                break
            if "Error code: 429" in (response.error or "") and attempt < max_retries:
                retry_count += 1
                rate_limited = True
                final_error_code = response.error[:50]
                wait = backoffs[min(attempt, len(backoffs) - 1)]
                await asyncio.sleep(wait)
            else:
                retry_count = attempt
                if response.error:
                    final_error_code = response.error[:50]
                break

        return response, platform_name, tmpl, {
            "retry_count": retry_count,
            "rate_limited": rate_limited,
            "final_error_code": final_error_code,
        }

    jobs = [query_one(p, t) for p in PLATFORMS for t in templates]
    responses = await asyncio.gather(*jobs, return_exceptions=True)

    for result in responses:
        if isinstance(result, Exception):
            continue
        response, platform_name, tmpl, retry_info = result
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
            retry_count=retry_info["retry_count"],
            rate_limited=retry_info["rate_limited"],
            final_error_code=retry_info["final_error_code"],
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
    run.collection_status = (
        "completed" if failure_count == 0
        else "failed" if failure_count == run.total_queries
        else "partial"
    )
    run.collection_completed_at = datetime.utcnow()
    await db.commit()

    if auto_analyze and run.collection_status in ("completed", "partial"):
        from src.analyzer.collection_analysis import run_analysis_for_collection
        await run_analysis_for_collection(run.id, org_id, db)

    return run
