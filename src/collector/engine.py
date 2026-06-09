import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)
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
    """Build TemplateHealthReport from preflight results or QueryTemplate objects."""
    from datetime import datetime, timezone

    def _level(r):
        qt = getattr(r, 'question_type', None)
        if qt is None:
            tmpl = getattr(r, 'template', None)
            qt = getattr(tmpl, 'question_type', 'brand_definition') if tmpl else 'brand_definition'
        return TEMPLATE_LEVEL_MAP.get(qt, "important")

    total = len(preflight_results) if preflight_results else 0
    # Accept both _PreflightResult objects and plain QueryTemplate objects
    if preflight_results and hasattr(preflight_results[0], 'render_status'):
        invalid = [r for r in preflight_results if r.render_status != "ok"]
        skipped = [r for r in preflight_results if r.render_status == "skipped_missing_variable"]
    else:
        invalid = []
        skipped = []

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
    adapter_registry: dict | None = None,
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

    # P1-7: Pin template versions at collection start (P0-8 atomic pinning)
    from src.models.query_template_version import QueryTemplateVersion
    from src.services.query_template_versioning import _build_version_snapshot, CHANGE_CREATE
    _pinned = {}
    _pinned_snapshot = []
    for _t in templates:
        _ver = (await db.execute(
            select(QueryTemplateVersion).where(
                QueryTemplateVersion.template_id == _t.id,
                QueryTemplateVersion.version == _t.current_version,
            )
        )).scalar_one_or_none()
        if _ver is None:
            # Auto-heal: legacy templates missing v1 get one created on the fly
            _ver = _build_version_snapshot(_t, _t.current_version or 1, CHANGE_CREATE, _t.created_by)
            db.add(_ver)
            await db.flush()
        _pinned[_t.id] = _ver
        _pinned_snapshot.append({
            "template_id": str(_ver.template_id),
            "version": _ver.version,
            "version_id": str(_ver.id),
            "dimension": _ver.dimension,
            "question_type": _ver.question_type,
            "template_level": _ver.template_level,
            "question_scope": _ver.question_scope,
        })

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
        started_at=datetime.now(timezone.utc),
        total_queries=0,  # computed after preflight
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

    _MULTI_VALUE_VARS = {
        "{竞品}": "target_competitors",
        "{场景}": "core_scenarios",
    }

    class _PreflightResult:
        __slots__ = ("template", "render_status", "unresolved_variables", "question_type")
        def __init__(self, template, status, unresolved, qtype):
            self.template = template
            self.render_status = status
            self.unresolved_variables = unresolved
            self.question_type = qtype

    _gt_json = {}
    if active_gt:
        _gt_json = active_gt.get_flat_json() if hasattr(active_gt, "get_flat_json") else active_gt.ground_truth_json

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

    # --- P0-8: Template health blocking gate ---
    if not health_report.get("can_collect", True):
        run.collection_status = "failed"
        run.collection_completed_at = datetime.now(timezone.utc)
        run.collection_error_summary = {
            "reason": "template_health_threshold",
            "invalid_ratio": health_report["invalid_ratio"],
            "invalid_templates": health_report["invalid_templates"],
            "total_templates": health_report["total_templates"],
            "threshold": 0.20,
        }
        await db.commit()
        return run

    def _build_questions(tmpl) -> list[str]:
        """Build one or more questions from a template, expanding multi-value vars."""
        question = tmpl.template_text
        for alias in brand.aliases or []:
            question = question.replace(f"{{{alias}}}", alias)
        question = question.replace("{品牌}", brand.name)
        question = question.replace("{行业}", brand.industry or "")
        for _var, _gt_key in _GT_VAR_MAP.items():
            if _var in _MULTI_VALUE_VARS:
                continue
            _val = _gt_json.get(_gt_key, "")
            if isinstance(_val, list):
                _val = "、".join(str(v) for v in _val)
            question = question.replace(_var, str(_val) if _val else _var)
        multi_var = next((v for v in _MULTI_VALUE_VARS if v in question), None)
        if multi_var:
            gt_key = _MULTI_VALUE_VARS[multi_var]
            values = _gt_json.get(gt_key, [])
            if isinstance(values, list) and values:
                return [question.replace(multi_var, str(v)) for v in values]
        return [question]

    # Compute actual total_queries with multi-value expansion
    _total = 0
    for _t in templates:
        _total += len(_build_questions(_t))
    run.total_queries = len(PLATFORMS) * _total
    await db.flush()
    # --- End preflight ---

    # ── Concurrency control: per-platform semaphores only (no global to avoid deadlock) ──
    _platform_semaphores = {
        p: asyncio.Semaphore(settings.platform_concurrency_limits.get(p, 2))
        for p in PLATFORMS
    }

    _gt_json = {}
    if active_gt:
        _gt_json = active_gt.get_flat_json() if hasattr(active_gt, "get_flat_json") else active_gt.ground_truth_json

    system = active_prompt.system_prompt if active_prompt else "你是一个诚实的AI助手。"

    # ── Per-platform stats (logged at end of run) ──────────────────────────
    _platform_stats_accum: dict[str, dict] = {
        p: {"request_count": 0, "success_count": 0, "timeout_count": 0,
            "rate_limited_count": 0, "latencies": [], "last_error": None}
        for p in PLATFORMS
    }

    async def query_one(platform_name, tmpl, question):
        stats = _platform_stats_accum[platform_name]
        sem = _platform_semaphores[platform_name]
        retry_cfg = settings.platform_rate_limits.get(platform_name, {})
        max_retries = retry_cfg.get("max_retries", 2)
        backoff_base = retry_cfg.get("backoff_base_seconds", 15)
        backoff_max = retry_cfg.get("backoff_max_seconds", 300)

        adapter = get_adapter(platform_name, registry=adapter_registry)
        retry_count = 0
        rate_limited = False
        final_error_code = ""
        response = None

        for attempt in range(max_retries + 1):
            async with sem:
                stats["request_count"] += 1
                response = await adapter.query(question, system_prompt=system)
                stats["latencies"].append(response.latency_ms)

            if not response.error:
                stats["success_count"] += 1
                break

            code = response.error_code or ""
            stats["last_error"] = f"{code}: {str(response.error)[:100]}"
            final_error_code = response.error_message or response.error or ""

            if code in ("platform_rate_limited",) and attempt < max_retries:
                retry_count += 1
                rate_limited = True
                stats["rate_limited_count"] += 1
                delay = min(backoff_base * (2 ** attempt), backoff_max)
                jitter = random.uniform(0, delay * 0.3)
                await asyncio.sleep(delay + jitter)
            elif code in ("platform_timeout", "platform_network_error") and attempt < max_retries:
                retry_count += 1
                stats["timeout_count"] += 1
                delay = min(backoff_base * (2 ** attempt), backoff_max)
                await asyncio.sleep(delay)
            else:
                if code == "platform_timeout":
                    stats["timeout_count"] += 1
                retry_count = attempt
                break

        return response, platform_name, tmpl, {
            "retry_count": retry_count,
            "rate_limited": rate_limited,
            "final_error_code": final_error_code[:50],
        }

    jobs = [
        query_one(p, t, q)
        for p in PLATFORMS
        for t in templates
        for q in _build_questions(t)
    ]
    responses = await asyncio.gather(*jobs, return_exceptions=True)

    processed = 0
    for result in responses:
        if isinstance(result, Exception):
            processed += 1
            continue
        response, platform_name, tmpl, retry_info = result
        processed += 1
        # Update progress every 8 results (P1: frontend polling visibility)
        if processed % 8 == 0:
            run.progress_json = {"completed": processed, "total": run.total_queries,
                                 "ratio": round(processed / max(run.total_queries, 1), 3)}
            await db.flush()
        qr = QueryResult(
            brand_id=brand_id,
            organization_id=org_id,
            collection_run_id=run.id,
            platform=platform_name,
            template_id=tmpl.id,
            template_version_id=_pinned[tmpl.id].id,
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
            collected_at=datetime.now(timezone.utc),
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

    # ── Per-platform status + partial success ─────────────────────────────
    platform_stats: dict[str, dict] = {}
    for p in PLATFORMS:
        platform_stats[p] = {"success": 0, "failed": 0, "rate_limited": 0,
                             "timeout_count": 0, "error_codes": []}

    for result in responses:
        if isinstance(result, Exception):
            for p in PLATFORMS:
                platform_stats[p]["failed"] += 1
            continue
        response, platform_name, tmpl, retry_info = result
        if response.error:
            code = response.error_code or "unknown"
            platform_stats[platform_name]["failed"] += 1
            platform_stats[platform_name]["error_codes"].append(code)
            if code == "platform_rate_limited":
                platform_stats[platform_name]["rate_limited"] += 1
        else:
            platform_stats[platform_name]["success"] += 1

    success_count = sum(
        1 for r in responses
        if not isinstance(r, Exception) and not r[0].error
    )
    failure_count = run.total_queries - success_count

    # Determine overall status with platform awareness
    rate_limited_platforms = [p for p, s in platform_stats.items()
                              if s["rate_limited"] > 0]
    deferred_retry_platforms = [p for p, s in platform_stats.items()
                                if s["rate_limited"] > 0 or
                                (s["failed"] > 0 and s["success"] == 0 and
                                 any(e in ("platform_rate_limited", "platform_timeout",
                                           "platform_network_error")
                                     for e in s.get("error_codes", [])))]
    timeout_platforms = [p for p, s in platform_stats.items()
                         if s["timeout_count"] > 0 and s["success"] == 0]
    all_failed_platforms = [p for p, s in platform_stats.items() if s["success"] == 0]
    has_partial_data = any(s["success"] > 0 for s in platform_stats.values())

    if failure_count == 0:
        run.collection_status = "completed"
    elif not has_partial_data:
        run.collection_status = "failed"
    else:
        run.collection_status = "partial"

    run.success_count = success_count
    run.failure_count = failure_count
    run.collection_completed_at = datetime.now(timezone.utc)
    # ── Platform stats logging ────────────────────────────────────────────
    for p in PLATFORMS:
        s = _platform_stats_accum[p]
        latencies = s["latencies"]
        avg_lat = round(sum(latencies) / len(latencies)) if latencies else 0
        sorted_lat = sorted(latencies)
        p95_lat = sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) >= 20 else (sorted_lat[-1] if sorted_lat else 0)
        logger.info(
            f"[{p}] requests={s['request_count']} success={s['success_count']} "
            f"timeout={s['timeout_count']} rate_limited={s['rate_limited_count']} "
            f"avg_lat={avg_lat}ms p95_lat={p95_lat}ms "
            f"last_error={s['last_error'] or 'none'}"
        )

    run.platform_status_json = {
        "schema_version": "platform_status_v2",
        "platforms": platform_stats,
        "rate_limited_platforms": rate_limited_platforms,
        "timeout_platforms": timeout_platforms,
        "deferred_retry_platforms": deferred_retry_platforms,
        "all_failed_platforms": all_failed_platforms,
        "partial_success": run.collection_status == "partial",
        "has_partial_data": has_partial_data,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    run.template_version_ids = {
        "schema_version": "template_versions_snapshot_v1",
        "pinned_at": datetime.now(timezone.utc).isoformat(),
        "templates": _pinned_snapshot,
    }
    # Save status before commit — avoid MissingGreenlet on expired object
    final_status = run.collection_status
    run_id = run.id
    await db.commit()

    if auto_analyze and final_status in ("completed", "partial"):
        from src.analyzer.collection_analysis import run_analysis_for_collection
        await run_analysis_for_collection(run_id, org_id, db)

    return run
