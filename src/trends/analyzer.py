"""Trend analysis engine — cliff detection, sustained trend, stability, platform volatility (P2-2)."""
import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

MIN_POINTS = {
    "cliff_drop": 4,
    "sustained_trend": 6,
    "stability_score": 6,
    "platform_volatility": 5,
    "seasonality": 24,
    "model_update_impact": 6,  # 3 before + 3 after
}


def resample_metric_series(snapshots: list, granularity: str = "weekly",
                           aggregation: str = "median") -> list[dict]:
    """Unified time-series resampling. Buckets data by granularity, aggregates duplicate periods."""
    if not snapshots:
        return []
    from collections import defaultdict
    buckets = defaultdict(list)
    for s in snapshots:
        key = _bucket_key(s.get("date") or s.get("week_start"), granularity)
        val = s.get("value")
        if val is not None:
            buckets[key].append(val)
    result = []
    for key in sorted(buckets.keys()):
        vals = buckets[key]
        if aggregation == "median":
            svals = sorted(vals)
            nv = len(svals)
            if nv % 2 == 0:
                agg = (svals[nv // 2 - 1] + svals[nv // 2]) / 2
            else:
                agg = svals[nv // 2]
        elif aggregation == "latest":
            agg = vals[-1]
        else:
            agg = sum(vals) / len(vals)
        result.append({"period": key, "value": agg, "point_count": len(vals)})
    return result


def _bucket_key(dt, granularity: str) -> str:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt[:10])
    if not isinstance(dt, datetime):
        # date object → convert to datetime
        dt = datetime(dt.year, dt.month, dt.day)
    if granularity == "daily":
        return dt.strftime("%Y-%m-%d")
    if granularity == "monthly":
        return dt.strftime("%Y-%m")
    # weekly: ISO week
    return f"{dt.year}-W{dt.isocalendar()[1]:02d}"


def compute_stability_score(series: list[float], missing_ratio: float = 0.0,
                             cliff_count: int = 0, platform_cv_spread: float = 0.0) -> dict:
    """Compute stability score 0-100 with component breakdown."""
    n = len(series)
    if n < 2:
        return {"score": 0, "grade": "数据不足", "components": {}, "confidence": "low",
                "reason": "数据点不足，无法计算稳定性"}

    mean_val = sum(series) / n
    variance = sum((x - mean_val) ** 2 for x in series) / n
    cv = (variance ** 0.5) / mean_val if mean_val > 0 else 1.0

    volatility_penalty = min(cv * 100, 40)
    cliff_penalty = min(cliff_count * 15, 30)
    missing_penalty = min(missing_ratio * 20, 20)
    platform_penalty = min(platform_cv_spread * 20, 20)

    score = max(0, 100 - volatility_penalty - cliff_penalty - missing_penalty - platform_penalty)

    if score >= 80:
        grade = "稳定"
    elif score >= 60:
        grade = "轻微波动"
    elif score >= 40:
        grade = "明显波动"
    else:
        grade = "不稳定"

    return {
        "score": round(score),
        "grade": grade,
        "components": {
            "volatility_penalty": round(volatility_penalty, 1),
            "cliff_penalty": round(cliff_penalty, 1),
            "missing_penalty": round(missing_penalty, 1),
            "platform_inconsistency_penalty": round(platform_penalty, 1),
        },
        "confidence": "high" if n >= 12 else "medium" if n >= 6 else "low",
        "reason": f"过去 {n} 个周期数据{'整体稳定' if score >= 80 else '存在一定波动' if score >= 60 else '波动较大'}。",
    }


def detect_cliff_drops(series: list[float], dates: list[str]) -> list[dict]:
    """Detect cliff drops: z-score ≤ -2 AND absolute drop ≥ 0.10 AND relative drop ≥ 20%."""
    n = len(series)
    if n < MIN_POINTS["cliff_drop"]:
        return []

    mean_val = sum(series) / n
    variance = sum((x - mean_val) ** 2 for x in series) / n
    std = variance ** 0.5 if variance > 0 else 0.01

    cliffs = []
    for i in range(1, n):
        drop = series[i] - series[i - 1]
        if drop >= 0:
            continue
        abs_drop = abs(drop)
        relative_drop = abs_drop / series[i - 1] if series[i - 1] > 0 else 0
        z_score = (series[i] - mean_val) / std if std > 0 else 0

        if relative_drop >= 0.20 and abs_drop >= 0.10 and z_score <= -2:
            severity = "critical" if abs_drop >= 0.20 else "warning"
            cliffs.append({
                "date": dates[i] if i < len(dates) else str(i),
                "from_value": round(series[i - 1], 4),
                "to_value": round(series[i], 4),
                "drop_abs": round(abs_drop, 4),
                "drop_pct": round(relative_drop * 100, 1),
                "z_score": round(z_score, 2),
                "severity": severity,
            })
    return cliffs


def detect_sustained_trend(series: list[float]) -> dict | None:
    """Detect sustained trend: consecutive uni-directional movement, simplified Mann-Kendall-like check."""
    n = len(series)
    if n < MIN_POINTS["sustained_trend"]:
        return None

    # Simple monotonic check: count ups vs downs
    ups = sum(1 for i in range(1, n) if series[i] > series[i - 1])
    downs = sum(1 for i in range(1, n) if series[i] < series[i - 1])
    total = ups + downs
    if total < 1:
        return None

    trend_strength = abs(ups - downs) / total
    slope = (series[-1] - series[0]) / (n - 1) if n > 1 else 0
    overall_change = series[-1] - series[0]

    # Simplified p-value check: binomial test approximation
    # For 6+ points with all same direction, p < 0.05
    all_same_direction = (ups == 0 and downs > 0) or (downs == 0 and ups > 0)
    statistically_significant = all_same_direction and total >= 5

    abs_slope = abs(slope)
    business_significant = abs_slope >= 0.02 and abs(overall_change) >= 0.08

    if statistically_significant and business_significant:
        direction = "improvement" if overall_change > 0 else "decline"
        return {
            "direction": "改善" if direction == "improvement" else "恶化",
            "trend_strength": round(trend_strength, 2),
            "slope_per_period": round(slope, 4),
            "overall_change": round(overall_change, 4),
            "statistically_significant": True,
            "business_significant": True,
            "periods": n,
        }
    if statistically_significant:
        direction = "improvement" if overall_change > 0 else "decline"
        return {
            "direction": "改善" if direction == "improvement" else "恶化",
            "trend_strength": round(trend_strength, 2),
            "statistically_significant": True,
            "business_significant": False,
            "periods": n,
        }
    return None


def analyze_platform_volatility(platform_kpi_data: dict) -> dict:
    """Analyze per-platform KPI volatility. Input: {platform: {kpi: [values]}}"""
    result = {}
    for platform, kpis in platform_kpi_data.items():
        result[platform] = {}
        for kpi_key, values in kpis.items():
            n = len(values)
            if n < MIN_POINTS["platform_volatility"]:
                result[platform][kpi_key] = {"mean": 0, "cv": None, "is_volatile": False, "insufficient_data": True}
                continue
            mean_v = sum(values) / n
            variance = sum((x - mean_v) ** 2 for x in values) / n
            cv = (variance ** 0.5) / mean_v if mean_v > 0 else 0
            result[platform][kpi_key] = {
                "mean": round(mean_v, 4), "cv": round(cv, 4),
                "is_volatile": cv > 0.30,
                "insufficient_data": False,
            }
    return result


def determine_change_scope(brand_id: str, kpi_key: str, affected_platforms: list[str],
                           competitor_data: dict, industry_data: dict) -> str:
    """Determine if a change is brand-specific, platform-specific, or industry-wide."""
    if not affected_platforms:
        return "unknown"

    # Single platform affected → platform_specific
    if len(affected_platforms) == 1 and not competitor_data.get("changed"):
        return "platform_specific"

    # All platforms + competitors also changed → industry_wide
    if competitor_data.get("changed") and industry_data.get("changed"):
        return "industry_wide"

    # Only brand changed, competitors stable → brand_specific
    if not competitor_data.get("changed"):
        return "brand_specific"

    # Competitors also changed → competitor_shared
    return "competitor_shared"


def _compute_cv(values: list[float]) -> float:
    n = len(values)
    mean_v = sum(values) / n if n > 0 else 0
    if mean_v == 0:
        return 0
    variance = sum((x - mean_v) ** 2 for x in values) / n
    return (variance ** 0.5) / mean_v
