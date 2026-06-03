"""Phase A quality module — ReportQualitySummary builder and publishable gate."""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.models.hallucination import HallucinationResult

logger = logging.getLogger(__name__)

HARD_BLOCK_CODES = {
    "CRITICAL_TEMPLATE_INVALID": "存在 critical 模板无效",
    "CANNOT_COLLECT": "模板健康度判定 can_collect=false",
    "METRIC_COVERAGE_LOW": "metric_eligible_coverage < 60%",
    "COVERAGE_DATA_MISSING": "缺少覆盖率数据",
    "TEMPLATE_HEALTH_MISSING": "缺少模板健康度数据",
    # P2-1: claim nature thresholds
    "HIGH_SPECULATION_RATIO": "推测声明占比过高",
    "EXCESSIVE_SPECULATION": "推测声明超过阻断阈值",
    "HIGH_OPINION_RATIO": "观点声明占比过高",
    "HIGH_UNKNOWN_RATIO": "无法分类声明占比过高",
    # P1-10: sample sufficiency
    "NO_DATA": "无成功 QueryResult，采集完全失败",
    "SAMPLE_TOTAL_TOO_LOW": "有效样本总数不足",
    "SAMPLE_PLATFORM_TOO_LOW": "成功平台数不足",
    "SAMPLE_QTYPE_TOO_LOW": "关键问题类型样本不足",
    "SAMPLE_KPI_TOO_LOW": "关键 KPI 分母不足",
    "SAMPLE_CRITICAL_PLATFORM_MISSING": "关键平台无数据",
    "METRIC_DATA_MISSING": "缺少 KPI 指标数据",
    "QUALITY_SCHEMA_MISSING": "quality_summary 缺少 schema_version",
    "TEMPLATE_ERROR_AS_P0": "template_error 被计入 P0",
    "GENERIC_AS_P0": "generic_statement 被计入 P0",
    "GT_INSUFFICIENT_AS_P0": "gt_insufficient 被计入 P0",
    "CORE_KPI_ZERO_DENOMINATOR": "核心 KPI denominator=0",
    "P0_MISSING_GT_EVIDENCE": "P0 hallucination 缺少 GT evidence",
    "MAPPING_INVALID": "metric_template_mapping 校验失败",
}


async def build_report_quality_summary(
    collection_run_id: str,
    template_health: dict | None,
    coverage_report: dict | None,
    db: AsyncSession,
) -> dict:
    """Aggregate hallucination + template health + coverage -> ReportQualitySummary.

    Input contracts:
    - template_health=None -> template_issue marked unknown
    - coverage_report=None -> coverage warnings
    - Empty HallucinationResult -> all hallucination counts 0
    Always returns a dict. Does not raise for missing data.
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    p0_count = 0; p1_count = 0; p2_count = 0; confirmed = 0
    generic_count = 0; irrelevant_count = 0
    unsupported_count = 0; gt_insufficient_count = 0
    template_invalid_count = 0
    # P2-1: claim nature counts
    fact_count = 0; opinion_count = 0; speculation_count = 0; unknown_count = 0
    total_claim_count = 0
    claim_type_breakdown = {"fact": {}, "opinion": {}, "speculation": {}, "unknown": {}}

    try:
        rows = (await db.execute(
            select(
                HallucinationResult.verdict,
                HallucinationResult.severity,
                HallucinationResult.subject_type,
                func.count().label("cnt"),
            ).where(
                HallucinationResult.collection_run_id == collection_run_id,
            ).group_by(
                HallucinationResult.verdict,
                HallucinationResult.severity,
                HallucinationResult.subject_type,
            )
        )).fetchall()

        for verdict, severity, subject_type, cnt in rows:
            if verdict == "contradicted" and subject_type == "target_brand":
                confirmed += cnt
                if severity == "P0": p0_count += cnt
                elif severity == "P1": p1_count += cnt
                elif severity == "P2": p2_count += cnt
            if verdict == "generic_statement": generic_count += cnt
            if verdict == "not_about_brand": irrelevant_count += cnt
            if verdict == "unsupported": unsupported_count += cnt
            if verdict == "gt_insufficient": gt_insufficient_count += cnt
            if verdict == "template_invalid": template_invalid_count += cnt
    except Exception:
        logger.warning("Failed to aggregate hallucination results for %s", collection_run_id, exc_info=True)

    # P2-1: claim type breakdown (separate query to avoid disrupting existing aggregation)
    try:
        ct_rows = (await db.execute(
            select(
                HallucinationResult.claim_type,
                HallucinationResult.severity,
                func.count().label("cnt"),
            ).where(
                HallucinationResult.collection_run_id == collection_run_id,
                HallucinationResult.verdict == "contradicted",
                HallucinationResult.subject_type == "target_brand",
            ).group_by(
                HallucinationResult.claim_type,
                HallucinationResult.severity,
            )
        )).fetchall()

        for ct, sev, cnt in ct_rows:
            ct_val = ct or "unknown"
            if ct_val == "fact":
                fact_count += cnt
            elif ct_val == "opinion":
                opinion_count += cnt
            elif ct_val == "speculation":
                speculation_count += cnt
            else:
                unknown_count += cnt
            if ct_val not in claim_type_breakdown:
                claim_type_breakdown[ct_val] = {}
            claim_type_breakdown[ct_val][sev or "Info"] = cnt
        total_claim_count = fact_count + opinion_count + speculation_count + unknown_count
    except Exception:
        logger.warning("Failed to aggregate claim type for %s", collection_run_id, exc_info=True)

    th = template_health or {}
    summary = {
        "schema_version": "report_quality_summary_v1",
        "generated_at": generated_at,
        "ai_hallucination": {
            "p0_count": p0_count, "p1_count": p1_count, "p2_count": p2_count,
            "confirmed_claim_count": confirmed,
            "p0_explanation": "仅统计目标品牌核心事实与 GT 明确冲突的声明",
            "excluded_explanation": "模板问题、GT 不足、回答无关不计入 AI 幻觉",
        },
        "template_issue": {
            "invalid_template_count": th.get("invalid_templates", 0),
            "unresolved_variable_count": len(th.get("missing_variables", {})),
            "affected_query_count": template_invalid_count,
        },
        "gt_insufficient": {
            "unsupported_claim_count": unsupported_count + gt_insufficient_count,
            "missing_gt_fields": [],
        },
        "not_about_brand": {
            "generic_statement_count": generic_count,
            "irrelevant_response_count": irrelevant_count,
        },
        # P2-1: claim nature breakdown
        "claim_nature": {
            "fact_count": fact_count,
            "opinion_count": opinion_count,
            "speculation_count": speculation_count,
            "unknown_count": unknown_count,
            "total_classified": total_claim_count,
            "breakdown": claim_type_breakdown,
        },
        "report_publishable": False,
        "blocking_reasons": [],
    }
    return summary


def compute_report_publishable(
    template_health: dict | None,
    coverage_report: dict | None,
    quality_summary: dict,
    metric_results: dict | None,
) -> tuple[bool, list[dict]]:
    """Apply 8 hard blocks + 4 soft warnings -> (publishable, blocking_reasons).

    Input contracts:
    - coverage_report must have metric_eligible_coverage, else hard block
    - template_health=None -> hard block TEMPLATE_HEALTH_MISSING
    """
    blocking: list[dict] = []

    def _block(code: str, severity: str = "block"):
        blocking.append({"code": code, "message": HARD_BLOCK_CODES.get(code, code), "severity": severity})

    th = template_health or {}
    cov = coverage_report or {}
    metrics = metric_results or {}
    qs = quality_summary or {}

    if not qs.get("schema_version"):
        _block("QUALITY_SCHEMA_MISSING")

    if not template_health:
        _block("TEMPLATE_HEALTH_MISSING")
    elif th.get("critical_invalid", 0) > 0:
        _block("CRITICAL_TEMPLATE_INVALID")
    elif th.get("can_collect") is False:
        _block("CANNOT_COLLECT")

    if not coverage_report or "metric_eligible_coverage" not in cov:
        _block("COVERAGE_DATA_MISSING")
    elif cov.get("metric_eligible_coverage", 0) < 0.60:
        _block("METRIC_COVERAGE_LOW")

    if not metrics:
        _block("METRIC_DATA_MISSING")
    else:
        core_kpis = ["information_accuracy", "completeness_rate", "citation_rate"]
        for kpi in core_kpis:
            denom = metrics.get(kpi, {}).get("denominator", 1)
            if denom == 0:
                _block("CORE_KPI_ZERO_DENOMINATOR")
                break

    if th.get("optional_skipped", 0) > 0:
        _block("OPTIONAL_SKIPPED", severity="warning")
    platform_cov = cov.get("platform_coverage", {})
    if any(v < 0.50 for v in platform_cov.values()):
        _block("PLATFORM_LOW_COVERAGE", severity="warning")
    qs_gt = qs.get("gt_insufficient", {})
    if qs_gt.get("unsupported_claim_count", 0) > 100:
        _block("HIGH_GT_UNSUPPORTED", severity="warning")

    # P2-1: claim nature ratio checks
    cn = qs.get("claim_nature", {})
    total_cn = cn.get("total_classified", 0)
    if total_cn > 0:
        spec_ratio = cn.get("speculation_count", 0) / total_cn
        opin_ratio = cn.get("opinion_count", 0) / total_cn
        unknown_ratio = cn.get("unknown_count", 0) / total_cn

        # Read thresholds from industry config if available
        thresholds = metrics.get("_claim_nature_thresholds", {}) if metrics else {}
        max_spec = thresholds.get("max_speculation_ratio", 0.30)
        spec_block = thresholds.get("speculation_block_threshold", 0.50)
        max_opin = thresholds.get("max_opinion_ratio", 0.60)
        max_unknown = thresholds.get("max_unknown_ratio", 0.20)

        if spec_ratio > spec_block:
            _block("EXCESSIVE_SPECULATION")
        elif spec_ratio > max_spec:
            _block("HIGH_SPECULATION_RATIO", severity="warning")

        if opin_ratio > max_opin:
            _block("HIGH_OPINION_RATIO", severity="warning")

        if unknown_ratio > max_unknown:
            _block("HIGH_UNKNOWN_RATIO", severity="warning")

    has_hard_block = any(b["severity"] == "block" for b in blocking)
    return (not has_hard_block, blocking)
