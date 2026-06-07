"""Platform Health ViewModel — real-time status of AI platform collectors."""

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, case
from src.models.query_result import QueryResult
from src.models.collection_run import CollectionRun


async def build_platform_health_vm(db: AsyncSession) -> dict:
    """Build view model for the platform health dashboard."""
    from src.config import settings

    platforms = []
    all_platforms = settings.collector_platform_order or ["deepseek", "kimi", "doubao", "wenxin"]

    for p in all_platforms:
        cfg = settings.platform_rate_limits.get(p, {})
        enabled = cfg.get("enabled", True) and cfg.get("max_concurrent", 0) > 0

        # Recent success rate (last 100 queries)
        recent = (await db.execute(
            select(
                func.count().label("total"),
                func.sum(case((QueryResult.status == "success", 1), else_=0)).label("success"),
                func.avg(QueryResult.latency_ms).label("avg_latency"),
            ).where(
                QueryResult.platform == p,
                QueryResult.collected_at >= func.now() - text("INTERVAL '1 hour'"),
            )
        )).fetchone()

        total = recent.total or 0
        success = recent.success or 0
        success_rate = round(success / total * 100, 1) if total > 0 else 100.0
        avg_latency = round(recent.avg_latency or 0)

        # 429 count in last hour
        rl_count = (await db.execute(
            select(func.count()).where(
                QueryResult.platform == p,
                QueryResult.final_error_code == "platform_rate_limited",
                QueryResult.collected_at >= func.now() - text("INTERVAL '1 hour'"),
            )
        )).scalar() or 0

        # Last success
        last_ok = (await db.execute(
            select(QueryResult.collected_at).where(
                QueryResult.platform == p,
                QueryResult.status == "success",
            ).order_by(QueryResult.collected_at.desc()).limit(1)
        )).scalar_one_or_none()

        # Last error
        last_err_row = (await db.execute(
            select(QueryResult.final_error_code, QueryResult.error_message, QueryResult.collected_at).where(
                QueryResult.platform == p,
                QueryResult.status == "error",
            ).order_by(QueryResult.collected_at.desc()).limit(1)
        )).fetchone()

        status = "healthy"
        disabled_reason = ""
        if not enabled:
            status = "disabled"
            disabled_reason = cfg.get("disabled_reason", "未启用")
        elif total > 0:
            error_rate = (total - success) / total
            if rl_count > 5:
                status = "rate_limited"
            elif error_rate > 0.3:
                status = "degraded"

        platforms.append({
            "platform": p,
            "status": status,
            "enabled": enabled,
            "disabled_reason": disabled_reason,
            "max_concurrent": cfg.get("max_concurrent", 0),
            "max_rpm": cfg.get("max_requests_per_minute", None),
            "max_tpm": cfg.get("max_tokens_per_minute", None),
            "success_rate_1h": success_rate,
            "total_queries_1h": total,
            "rate_limited_count_1h": rl_count,
            "avg_latency_ms": avg_latency,
            "last_success_at": last_ok.isoformat() if last_ok else None,
            "last_error_at": last_err_row.collected_at.isoformat() if last_err_row and last_err_row.collected_at else None,
            "last_error_code": last_err_row.final_error_code if last_err_row else None,
            "last_error_message": (last_err_row.error_message or "")[:200] if last_err_row else None,
        })

    return {
        "platforms": platforms,
        "total_enabled": sum(1 for p in platforms if p["enabled"]),
        "healthy_count": sum(1 for p in platforms if p["status"] == "healthy"),
        "degraded_count": sum(1 for p in platforms if p["status"] == "degraded"),
        "rate_limited_count": sum(1 for p in platforms if p["status"] == "rate_limited"),
        "disabled_count": sum(1 for p in platforms if p["status"] == "disabled"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
