import logging
from datetime import datetime, timezone
from collections import Counter, defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

logger = logging.getLogger(__name__)
SEVERITY_ORDER = {"P0": 3, "P1": 2, "P2": 1}


async def generate_insights(
    collection_run_id: str,
    brand_id: str,
    org_id: str,
    db: AsyncSession,
) -> dict:
    from src.models.collection_run import CollectionRun
    from src.models.query_result import QueryResult
    from src.models.metrics_snapshot import MetricsSnapshot
    from src.models.hallucination import HallucinationResult
    from src.models.insight_summary import InsightSummary

    run = (await db.execute(
        select(CollectionRun).where(CollectionRun.id == collection_run_id)
    )).scalar_one_or_none()
    if not run:
        logger.error("CollectionRun %s not found for insight generation", collection_run_id)
        return {}

    metrics = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.collection_run_id == collection_run_id,
        ).order_by(MetricsSnapshot.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    hallucinations = (await db.execute(
        select(HallucinationResult).where(
            HallucinationResult.collection_run_id == collection_run_id,
        )
    )).scalars().all()

    # 加载 QueryResult id+platform 用于幻觉的 platform 查询
    query_results = (await db.execute(
        select(QueryResult.id, QueryResult.platform).where(
            QueryResult.collection_run_id == collection_run_id,
        )
    )).all()
    qr_by_id = {str(row.id): row for row in query_results}

    platform_stats = await _compute_platform_health(collection_run_id, db)
    brand_perf = _compute_brand_performance(metrics)
    findings = _compute_key_findings(hallucinations, metrics, platform_stats, qr_by_id)

    total_platforms = len(platform_stats)
    failed_platforms = sum(1 for p in platform_stats.values() if p["success_rate"] == 0)
    data_ok = (
        run.success_count >= 10
        and (total_platforms - failed_platforms) >= 2
    )
    reliability = {
        "total_queries": run.total_queries,
        "success_count": run.success_count,
        "total_platforms": total_platforms,
        "failed_platforms": failed_platforms,
        "kpi_usable": data_ok,
        "cross_platform_usable": (total_platforms - failed_platforms) >= 2,
        "p0_hallucinations": sum(1 for h in hallucinations if h.severity == "P0"),
    }

    confidence = _overall_confidence(findings)

    summary = InsightSummary(
        organization_id=org_id,
        brand_id=brand_id,
        collection_run_id=collection_run_id,
        platform_health_json=platform_stats,
        brand_performance_json=brand_perf,
        key_findings_json=findings,
        data_reliability_json=reliability,
        confidence_level=confidence,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(summary)
    await db.commit()

    return {
        "platform_health_json": platform_stats,
        "brand_performance_json": brand_perf,
        "key_findings_json": findings,
        "data_reliability_json": reliability,
        "confidence_level": confidence,
    }


async def _compute_platform_health(collection_run_id: str, db: AsyncSession) -> dict:
    from src.models.query_result import QueryResult

    rows = (await db.execute(
        select(
            QueryResult.platform,
            func.count(QueryResult.id).label("total"),
            func.sum(case((QueryResult.status == "success", 1), else_=0)).label("success"),
            func.avg(QueryResult.latency_ms).label("avg_latency"),
            func.sum(case((QueryResult.rate_limited == True, 1), else_=0)).label("rate_limited_count"),
        ).where(QueryResult.collection_run_id == collection_run_id)
        .group_by(QueryResult.platform)
    )).all()

    result = {}
    for row in rows:
        total = row.total or 0
        success = int(row.success or 0)
        latency = float(row.avg_latency) if row.avg_latency is not None else 0.0
        result[row.platform] = {
            "total": total,
            "success": success,
            "success_rate": round(success / total, 4) if total > 0 else 0,
            "avg_latency_ms": round(latency, 1),
            "rate_limited_count": int(row.rate_limited_count or 0),
        }
    return result


def _compute_brand_performance(metrics) -> dict:
    if not metrics:
        return {}
    return {
        "sov": metrics.sov,
        "first_rec_rate": metrics.first_rec_rate,
        "accuracy_rate": metrics.accuracy_rate,
        "completeness_rate": metrics.completeness_rate,
        "citation_rate": metrics.citation_rate,
        "sample_size": metrics.sample_size,
    }


def _compute_key_findings(hallucinations, metrics, platform_stats, qr_by_id) -> list:
    findings = []

    # 1. 跨平台幻觉: 同一 field_name 在多个平台出现
    field_platforms = defaultdict(list)
    for h in hallucinations:
        qr = qr_by_id.get(str(h.query_result_id))
        platform = qr.platform if qr else "unknown"
        field_platforms[h.field_name].append((h, platform))

    for field_name, items in field_platforms.items():
        platforms_involved = list(set(p for _, p in items))
        n_platforms = len(platforms_involved)
        hallucinations_list = [h for h, _ in items]
        max_sev = max(hallucinations_list, key=lambda h: SEVERITY_ORDER.get(h.severity, 0))

        if n_platforms >= 3:
            findings.append({
                "type": "cross_platform_p0_error",
                "title": f"多平台误判: {field_name}",
                "severity": max_sev.severity,
                "confidence": "high",
                "evidence": [
                    {"platform": p, "ai_claim": h.ai_claim, "ground_truth": h.ground_truth_value}
                    for h, p in items
                ],
                "interpretation": f"{n_platforms} 个平台同时出错，可能是品牌公开信息锚点不足。",
                "recommended_action": f"优先修正品牌官方渠道中的 {field_name} 信息。",
            })
        elif n_platforms >= 2:
            findings.append({
                "type": "cross_platform_p0_error",
                "title": f"部分平台误判: {field_name}",
                "severity": max_sev.severity,
                "confidence": "medium",
                "evidence": [
                    {"platform": p, "ai_claim": h.ai_claim}
                    for h, p in items
                ],
                "interpretation": "2 个平台出现同类错误。",
                "recommended_action": f"检查 {field_name} 在主流平台中的展示一致性。",
            })

    # 2. 平台差异: 引用率差异 >= 0.3
    if metrics and metrics.details:
        citation_detail = metrics.details.get("citation", {})
        platform_citations = citation_detail.get("by_platform", {})
        if platform_citations:
            rates = [(p, v.get("citation_rate", 0)) for p, v in platform_citations.items()]
            rates.sort(key=lambda x: x[1])
            if len(rates) >= 2 and rates[-1][1] - rates[0][1] > 0.3:
                findings.append({
                    "type": "platform_diff",
                    "title": f"引用率差异显著: {rates[-1][0]} vs {rates[0][0]}",
                    "severity": "P1",
                    "confidence": "medium",
                    "evidence": [{"platform": p, "citation_rate": r} for p, r in rates],
                    "interpretation": f"{rates[0][0]} 引用率显著低于其他平台。",
                    "recommended_action": f"优化 {rates[0][0]} 平台的官方链接提及策略。",
                })

    return findings


def _overall_confidence(findings: list) -> str:
    if not findings:
        return "low"
    severities = Counter(f["confidence"] for f in findings)
    if severities.get("high", 0) >= 2:
        return "high"
    if severities.get("high", 0) >= 1 or severities.get("medium", 0) >= 2:
        return "medium"
    return "low"
