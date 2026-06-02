"""P1-10: Sample sufficiency assessor — 4-tier valid samples, 3D breakdown, state machine."""
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.query_template import QueryTemplate
from src.models.query_template_version import QueryTemplateVersion
from src.schemas.sample_sufficiency import (
    SampleSufficiencyConfig, SampleSufficiencyResult, SampleSufficiencyAction,
)

logger = logging.getLogger(__name__)

EXCLUDED_ERRORS_FOR_VALID = {"template_invalid", "empty_response", "content_filtered", "system_error"}


async def compute_valid_query_counts(
    db: AsyncSession, run: CollectionRun,
) -> dict:
    """Compute 4-tier counts for a CollectionRun (P0-1)."""
    qrs = (await db.execute(
        select(QueryResult).where(QueryResult.collection_run_id == run.id)
    )).scalars().all()

    raw = len(qrs)
    successful = [q for q in qrs if q.status == "success"]
    valid = [q for q in successful
             if q.error_code not in EXCLUDED_ERRORS_FOR_VALID
             and q.answer_text and len(q.answer_text.strip()) > 0]
    metric_eligible = [q for q in valid
                       if _is_metric_eligible(q)]

    return {
        "raw_count": raw,
        "success_count": len(successful),
        "valid_count": len(valid),
        "eligible_count": len(metric_eligible),
        "valid_qrs": valid,
        "eligible_qrs": metric_eligible,
        "all_qrs": qrs,
    }


async def assess_sample_sufficiency(
    db: AsyncSession,
    run: CollectionRun,
    config: SampleSufficiencyConfig,
    config_source: dict | None = None,
) -> SampleSufficiencyResult:
    """Full 3D sample sufficiency assessment (P0-7 state machine)."""
    now = datetime.now(timezone.utc).isoformat()
    counts = await compute_valid_query_counts(db, run)

    result = SampleSufficiencyResult(
        generated_at=now,
        config_snapshot=config.model_dump(),
        config_source=config_source or {},
        total_raw_queries=counts["raw_count"],
        total_successful_queries=counts["success_count"],
        total_valid_queries=counts["valid_count"],
        total_metric_eligible_queries=counts["eligible_count"],
    )

    # Build breakdowns
    result.platform_breakdown = _build_platform_breakdown(counts["all_qrs"], config)
    result.qtype_breakdown = await _build_qtype_breakdown(db, counts["valid_qrs"], config)
    result.kpi_breakdown = _build_kpi_breakdown(run, config)

    result.total_platforms = len(result.platform_breakdown)
    result.enabled_platforms = sum(1 for p in result.platform_breakdown.values() if p.get("enabled"))
    result.successful_platforms = sum(1 for p in result.platform_breakdown.values() if p.get("status") == "ok")

    # State machine
    result.data_status = _compute_data_status(result, config)

    # Blocking/warnings/actions
    _compute_reasons_and_actions(result, config)

    return result


def _build_platform_breakdown(all_qrs: list, config: SampleSufficiencyConfig) -> dict:
    breakdown = {}
    platforms = {}
    for q in all_qrs:
        if q.platform not in platforms:
            platforms[q.platform] = {"raw": 0, "success": 0, "valid": 0, "eligible": 0, "errors": {}}
        p = platforms[q.platform]
        p["raw"] += 1
        if q.status == "success":
            p["success"] += 1
        if q.status == "success" and q.answer_text and q.error_code not in EXCLUDED_ERRORS_FOR_VALID:
            p["valid"] += 1
        if q.error_message:
            err_type = "rate_limited" if "429" in (q.error_message or "") else q.error_code or "unknown"
            p["errors"][err_type] = p["errors"].get(err_type, 0) + 1

    for plat, p in platforms.items():
        min_req = config.min_queries_by_platform.get(plat, config.min_queries_per_platform)
        sufficient = p["valid"] >= min_req
        status = "ok" if sufficient else ("no_valid_answer" if p["valid"] == 0 else "insufficient")
        if any("429" in str(e) for e in p["errors"]):
            status = "rate_limited"
        breakdown[plat] = {
            "enabled": True, "attempted": True,
            "raw_queries": p["raw"], "success_queries": p["success"],
            "valid_answer_queries": p["valid"], "metric_eligible_queries": p["eligible"],
            "error_queries": p["raw"] - p["success"],
            "error_breakdown": p["errors"],
            "sufficient": sufficient, "min_required": min_req, "status": status,
        }
    return breakdown


async def _build_qtype_breakdown(db: AsyncSession, valid_qrs: list, config: SampleSufficiencyConfig) -> dict:
    """P0-5: Use template_version snapshot for qtype, fallback to legacy."""
    qtypes = {}
    for q in valid_qrs:
        qt = "unknown"
        # Priority: template_version → legacy QueryTemplate
        if q.template_version_id:
            tv = (await db.execute(
                select(QueryTemplateVersion).where(QueryTemplateVersion.id == q.template_version_id)
            )).scalar_one_or_none()
            if tv:
                qt = tv.question_type
        if qt == "unknown" or qt == "unknown":
            tmpl = (await db.execute(
                select(QueryTemplate).where(QueryTemplate.id == q.template_id)
            )).scalar_one_or_none()
            if tmpl:
                qt = tmpl.question_type

        if qt not in qtypes:
            qtypes[qt] = 0
        qtypes[qt] += 1

    breakdown = {}
    for qt, count in qtypes.items():
        min_req = config.min_queries_by_qtype.get(qt, config.min_queries_per_qtype)
        sufficient = count >= min_req
        breakdown[qt] = {
            "valid_queries": count, "min_required": min_req,
            "sufficient": sufficient,
            "is_critical": qt in config.critical_qtypes,
        }
    return breakdown


def _build_kpi_breakdown(run: CollectionRun, config: SampleSufficiencyConfig) -> dict:
    """P0-6: Reuse MetricResult.denominator_json or report_quality_summary."""
    summary = run.report_quality_summary_json or {}
    kpi_data = summary.get("kpi_summary", {})
    if not kpi_data:
        kpi_data = summary.get("metrics", {})

    breakdown = {}
    for kpi_name in ["accuracy", "completeness", "citation", "sov", "first_rec"]:
        kpi_info = kpi_data.get(kpi_name, {})
        denominator = kpi_info.get("denominator", 0) if isinstance(kpi_info, dict) else 0
        min_req = config.min_queries_by_kpi.get(kpi_name, config.min_queries_per_kpi_default)
        breakdown[kpi_name] = {
            "denominator": denominator,
            "min_required": min_req,
            "sufficient": denominator >= min_req,
            "is_critical": kpi_name in config.critical_kpis,
        }
    return breakdown


def _compute_data_status(result: SampleSufficiencyResult, config: SampleSufficiencyConfig) -> str:
    """P0-7: State machine."""
    if result.total_valid_queries == 0:
        return "no_data"
    if result.total_valid_queries < config.min_total_queries:
        return "insufficient"
    if result.successful_platforms < config.min_platforms:
        return "insufficient"
    if config.require_all_platforms and result.successful_platforms < result.enabled_platforms:
        return "insufficient"
    for qt, info in result.qtype_breakdown.items():
        if qt in config.critical_qtypes and not info["sufficient"]:
            return "insufficient"
    for kpi, info in result.kpi_breakdown.items():
        if kpi in config.critical_kpis and not info["sufficient"]:
            return "insufficient"
    for plat in config.critical_platforms:
        pb = result.platform_breakdown.get(plat, {})
        if not pb.get("sufficient", False):
            return "insufficient"
    # partial check
    any_insufficient = any(not p.get("sufficient", True) for p in result.platform_breakdown.values()) or \
                       any(not qi["sufficient"] for qi in result.qtype_breakdown.values())
    if any_insufficient:
        return "partial"
    return "ok"


def _compute_reasons_and_actions(result: SampleSufficiencyResult, config: SampleSufficiencyConfig):
    """P0-9 + P0-10: blocking reasons, warnings, recommended actions."""
    if result.data_status == "no_data":
        result.blocking_dimensions.append({
            "code": "NO_DATA", "message": "无成功 QueryResult",
            "severity": "block", "dimension": "all",
        })
        result.recommended_actions.append({
            "action_type": "collect_more", "target": None,
            "reason": "采集完全失败, 检查平台 Key 和任务状态", "priority": "high",
        })
        result.recommendation_summary = "采集失败, 需重新执行采集"
        return

    if result.total_valid_queries < config.min_total_queries:
        _add_block(result, "SAMPLE_TOTAL_TOO_LOW", "total", result.total_valid_queries, config.min_total_queries)
        result.recommended_actions.append({
            "action_type": "collect_more", "target": None,
            "reason": f"总有效样本不足, 实际{result.total_valid_queries}, 要求{config.min_total_queries}",
            "priority": "high",
        })

    for plat, info in result.platform_breakdown.items():
        if not info["sufficient"] and plat in config.critical_platforms:
            _add_block(result, "SAMPLE_CRITICAL_PLATFORM_MISSING", f"platform:{plat}", info["valid_answer_queries"], info["min_required"])

    for qt, info in result.qtype_breakdown.items():
        if not info["sufficient"] and qt in config.critical_qtypes:
            _add_block(result, "SAMPLE_QTYPE_TOO_LOW", f"qtype:{qt}", info["valid_queries"], info["min_required"])

    for kpi, info in result.kpi_breakdown.items():
        if not info["sufficient"] and kpi in config.critical_kpis:
            _add_block(result, "SAMPLE_KPI_TOO_LOW", f"kpi:{kpi}", info["denominator"], info["min_required"])

    if result.data_status == "partial":
        result.warnings.append({"code": "SAMPLE_PARTIAL_PLATFORM", "message": "非关键维度样本不足, 可酌情发布", "severity": "warning"})

    result.recommendation_summary = _build_summary(result)


def _add_block(result: SampleSufficiencyResult, code: str, dimension: str, actual: int, required: int):
    result.blocking_dimensions.append({
        "code": code, "dimension": dimension,
        "actual": actual, "required": required,
        "severity": "block", "message": f"{dimension} 样本不足: 实际{actual}, 要求{required}",
    })


def _is_metric_eligible(qr: QueryResult) -> bool:
    """Check if a QueryResult is eligible for KPI metric calculation."""
    if not qr.answer_text or len(qr.answer_text.strip()) == 0:
        return False
    return True


def _build_summary(result: SampleSufficiencyResult) -> str:
    if result.data_status == "ok":
        return "样本充分度达标，诊断结果可信"
    if result.data_status == "no_data":
        return "样本为零，无法进行诊断。请检查采集任务状态"
    if result.data_status == "insufficient":
        dims = [d["dimension"] for d in result.blocking_dimensions]
        return f"样本不充分（{', '.join(dims)}），当前数据不足以支撑正式诊断。样本不足不等于品牌表现差"
    if result.data_status == "partial":
        return "部分维度样本不足，报告可酌情发布。样本不足不等于品牌表现差"
    return ""
