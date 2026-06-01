"""Health score engine — weighted scoring with industry weights, risk adjustments."""
import logging

logger = logging.getLogger(__name__)

DEFAULT_KPI_WEIGHTS = {
    "accuracy_rate": 0.25,
    "citation_rate": 0.20,
    "sov": 0.15,
    "completeness_rate": 0.10,
    "first_rec_rate": 0.10,
    "scenario_recall": 0.05,
    "differentiation": 0.05,
    "cross_platform_consistency": 0.05,
    "recommendation_quality": 0.05,
    "semantic_stability": 0.05,
}

GRADE_THRESHOLDS = [
    (80, "健康", "green"),
    (60, "需关注", "yellow"),
    (40, "需行动", "orange"),
    (0, "高风险", "red"),
]


def compute_health_score(
    kpis: list[dict],
    industry_template=None,
    p0_hallucination_count: int = 0,
    citation_rate: float | None = None,
    sample_size: int = 0,
) -> dict:
    """Compute health score from KPI values with industry weights and risk adjustments.

    Args:
        kpis: [{"key": "accuracy_rate", "value": 0.72, "sample_size": 50}, ...]
        industry_template: optional IndustryTemplate with kpi_weights override
        p0_hallucination_count: number of P0 hallucinations for penalty
        citation_rate: separate citation rate for credibility adjustment
        sample_size: total sample size for confidence assessment

    Returns:
        {score, grade, color, confidence, confidence_reason, score_breakdown, risk_adjustments}
    """
    kpi_map = {k["key"]: k for k in kpis}

    # Resolve weights — prefer industry template weights
    base_weights = dict(DEFAULT_KPI_WEIGHTS)
    if industry_template and hasattr(industry_template, "kpi_weights"):
        industry_weights = industry_template.kpi_weights or {}
        if isinstance(industry_weights, dict):
            for k, w in industry_weights.items():
                if k in base_weights and isinstance(w, (int, float)):
                    base_weights[k] = float(w)

    # Filter to available KPIs and normalize
    available = {k: w for k, w in base_weights.items() if k in kpi_map}
    if not available:
        return {
            "score": 0, "grade": "未知", "color": "gray",
            "confidence": "low", "confidence_reason": "无可用 KPI 数据",
            "score_breakdown": [], "risk_adjustments": [],
        }

    weight_sum = sum(available.values())
    normalized = {k: w / weight_sum for k, w in available.items()}

    # Weighted score
    breakdown = []
    total_score = 0.0
    for kpi_key, weight in normalized.items():
        value = kpi_map[kpi_key].get("value", 0) or 0
        contribution = round(value * 100 * weight, 1)
        total_score += contribution
        breakdown.append({
            "kpi": kpi_key,
            "score": round(value * 100, 1),
            "weight": round(weight, 3),
            "contribution": contribution,
        })

    # Risk adjustments
    adjustments = []
    if p0_hallucination_count > 0:
        penalty = min(p0_hallucination_count * 5, 15)
        total_score -= penalty
        adjustments.append({
            "type": "p0_hallucination",
            "points": -penalty,
            "reason": f"存在 {p0_hallucination_count} 条高风险错误信息",
        })

    if citation_rate is not None and citation_rate < 0.20:
        total_score -= 5
        adjustments.append({
            "type": "low_citation",
            "points": -5,
            "reason": "官方来源引用率偏低，影响整体可信度",
        })

    total_score = max(0, min(100, total_score))

    # Grade
    grade, color = "未知", "gray"
    for threshold, g, c in GRADE_THRESHOLDS:
        if total_score >= threshold:
            grade, color = g, c
            break

    # Confidence
    missing_count = len(base_weights) - len(available)
    confidence, confidence_reason = "high", ""
    if missing_count > 5 or sample_size < 30:
        confidence = "low"
        confidence_reason = f"样本量不足（{sample_size} 条）" if sample_size < 30 else f"缺失 {missing_count} 项指标"
    elif missing_count > 2:
        confidence = "medium"
        confidence_reason = f"缺失 {missing_count} 项指标，结果仅供参考"

    return {
        "score": round(total_score),
        "grade": grade,
        "color": color,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "score_breakdown": breakdown,
        "risk_adjustments": adjustments,
    }
