"""Report insight builder — generates conclusions, top risks, top actions from ReportContext."""
from src.reports.customer_language import (
    KPI_CUSTOMER_LANGUAGE, get_kpi_verdict, replace_terms_for_customer_language,
)


def build_one_line_summary(context: dict) -> str:
    """Generate a one-sentence executive summary from health + top findings."""
    health = context.get("health", {})
    score = health.get("score", 0)
    grade = health.get("grade", "未知")
    kpis = context.get("kpis", [])
    findings = context.get("key_findings", [])

    worst_kpis = [k for k in kpis if k.get("verdict") == "bad"]
    top_risk = findings[0] if findings else None

    parts = []
    if score >= 80:
        parts.append(f"品牌在 AI 平台中的整体认知健康度良好（{score} 分，{grade}）。")
    elif score >= 60:
        parts.append(f"品牌在 AI 平台中已具备一定基础可见度，但部分指标仍需关注（{score} 分，{grade}）。")
    else:
        parts.append(f"品牌在 AI 平台中的认知健康度需要重点关注（{score} 分，{grade}）。")

    if worst_kpis:
        worst_labels = [KPI_CUSTOMER_LANGUAGE.get(k["key"], {}).get("label", k["key"]) for k in worst_kpis[:2]]
        parts.append(f"主要薄弱项为{' 和 '.join(worst_labels)}。")

    if top_risk:
        parts.append(f"最紧迫的问题是「{top_risk.get('title', '')}」。")

    result = "".join(parts)
    return replace_terms_for_customer_language(result, "executive", "strict")


def select_top_risks(context: dict, limit: int = 3) -> list[dict]:
    """Select and order top risks by severity × impact."""
    findings = context.get("key_findings", [])
    scored = []
    for f in findings:
        score = _risk_score(f)
        scored.append((score, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:limit]]


def _risk_score(finding: dict) -> float:
    """Score a finding by severity × KPI impact × P0 flag × industry × evidence."""
    s = 1.0
    sev = finding.get("severity", "P2")
    if sev == "P0":
        s *= 3
    elif sev == "P1":
        s *= 2

    kpis = finding.get("impact_kpis", [])
    s *= max(1, len(kpis))

    ev = finding.get("evidence_level", "low")
    if ev == "high":
        s *= 1.5
    elif ev == "medium":
        s *= 1.2

    return s


def select_top_action(context: dict) -> dict | None:
    """Select the single most important action from the context."""
    actions = context.get("actions", [])
    if not actions:
        return None

    scored = []
    for a in actions:
        score = _action_score(a)
        scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def _action_score(action: dict) -> float:
    """Score an action by severity × feasibility × impact × re-testability."""
    s = 1.0
    pri = action.get("priority", "P2")
    if pri == "P0":
        s *= 3
    elif pri == "P1":
        s *= 2

    if action.get("content_asset"):
        s *= 1.5  # has concrete asset
    if action.get("recheck_timing"):
        s *= 1.3  # re-testable
    if action.get("acceptance_criteria"):
        s *= 1.2  # has measurable criteria

    return s


def build_executive_narrative(context: dict) -> dict:
    """Build the full executive narrative: one-line, top risks, top action, data note."""
    return {
        "one_line": build_one_line_summary(context),
        "top_risks": select_top_risks(context, limit=3),
        "top_action": select_top_action(context),
        "data_note": _build_data_note(context),
    }


def build_customer_opening_narrative(context: dict) -> str:
    """Build the opening paragraph for Customer edition."""
    health = context.get("health", {})
    score = health.get("score", 0)
    grade = health.get("grade", "未知")
    dq = context.get("data_quality", {})
    industry = context.get("industry", {})
    opening = industry.get("opening_frame", "")

    lines = [
        f"本次 AI 品牌认知诊断显示，{context.get('brand', {}).get('name', '您的品牌')}",
        f"在 {dq.get('platform_count', 0)} 个主流 AI 平台中的综合认知健康度为 **{score} 分（{grade}）**。",
    ]
    if dq.get("sample_notes"):
        lines.append(dq["sample_notes"])
    if opening:
        lines.append(opening)
    result = " ".join(lines)
    return replace_terms_for_customer_language(result, "customer", "lenient")


def _build_data_note(context: dict) -> str:
    dq = context.get("data_quality", {})
    parts = [
        f"本次诊断基于 {dq.get('platform_count', 0)} 个 AI 平台、",
        f"{dq.get('query_count', 0)} 个问题、共 {dq.get('success_count', 0)} 条有效 AI 回答。",
    ]
    if dq.get("failure_count", 0) > 0:
        parts.append(f"有 {dq['failure_count']} 条查询失败，部分结果可能受影响。")
    return "".join(parts)
