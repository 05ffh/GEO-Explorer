"""ReportContext builder — standardized context for all report templates."""
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from src.analyzer.enums import HallucinationVerdict
from src.reports.customer_language import (
    KPI_CUSTOMER_LANGUAGE, get_kpi_verdict, get_industry_language,
)
from src.reports.health_score import compute_health_score
from src.reports.insight_builder import build_executive_narrative, build_customer_opening_narrative


async def build_report_context(
    brand: dict,
    collection_run_id: str,
    db: AsyncSession,
    edition: str,
    industry_template=None,
) -> dict:
    """Build the full ReportContext for template rendering.

    All templates consume this context — no direct DB access.
    """
    data = await _fetch_data(brand, collection_run_id, db)
    if industry_template:
        data["industry_template"] = industry_template

    # KPI list with customer language
    kpis = _build_kpi_list(data)
    health = compute_health_score(
        kpis=kpis,
        industry_template=industry_template,
        p0_hallucination_count=data.get("p0_hall_count", 0),
        citation_rate=data.get("citation_rate"),
        sample_size=data.get("sample_size", 0),
    )

    key_findings = _build_key_findings(data)
    actions = _build_actions(data)
    industry_lang = get_industry_language(
        industry_template.industry_key if industry_template else None
    )

    context = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "template_version": "1.0",
            "language_version": "1.0",
            "locale": "zh-CN",
        },
        "brand": {
            "name": brand.get("name", ""),
            "industry": brand.get("industry", ""),
            "website": brand.get("website", ""),
        },
        "data_quality": {
            "platform_count": len(data.get("platforms", [])),
            "query_count": data.get("total_queries", 0),
            "success_count": data.get("success_count", 0),
            "failure_count": data.get("failure_count", 0),
            "partial_platforms": [
                p["platform"] for p in data.get("platforms", [])
                if p.get("ok", 0) < p.get("total", 0)
            ],
            "sample_notes": _build_sample_notes(data),
            "collected_at": str(data.get("collected_at", "")),
        },
        "health": health,
        "kpis": kpis,
        "key_findings": key_findings,
        "hallucinations": {
            "total": data.get("hall_total", 0),
            "incorrect": data.get("hall_incorrect", 0),
            "by_severity": data.get("hallucinations", []),
            "examples": data.get("hall_examples", []),
        },
        "actions": actions,
        "content_packages": data.get("content_packages", []),
        "methodology": {
            "how_we_ask": _methodology_how_we_ask(),
            "how_we_judge": _methodology_how_we_judge(),
            "how_we_score": _methodology_how_we_score(),
            "limitations": _methodology_limitations(),
        },
        "industry": industry_lang,
        "audience": _audience_profile(edition),
    }

    # Enrich with narratives
    narrative = build_executive_narrative(context)
    context["executive_narrative"] = narrative
    if edition == "customer":
        context["customer_opening"] = build_customer_opening_narrative(context)

    return context


# ── Data fetching ────────────────────────────────────────────────────────────

async def _fetch_data(brand: dict, collection_run_id: str, db: AsyncSession) -> dict:
    data = {"brand_name": brand.get("name", ""), "collection_run_id": collection_run_id}

    cr = (await db.execute(text("""
        SELECT collection_status, analysis_status, total_queries, success_count,
               failure_count, created_at, collection_completed_at
        FROM collection_runs WHERE id = :rid
    """), {"rid": collection_run_id})).fetchone()
    if cr:
        data.update(dict(cr._mapping))
        data["collected_at"] = str(cr.collection_completed_at or cr.created_at)

    ms = (await db.execute(text("""
        SELECT sov, first_rec_rate, accuracy_rate, completeness_rate, citation_rate,
               sample_size, failure_rate, details
        FROM metrics_snapshots WHERE collection_run_id = :rid
        ORDER BY created_at DESC LIMIT 1
    """), {"rid": collection_run_id})).fetchone()
    if ms:
        data.update(dict(ms._mapping))
        ek = (ms.details or {}).get("extended_kpis", {}) if hasattr(ms, 'details') else {}
        data["extended_kpis"] = ek

    plat = await db.execute(text("""
        SELECT platform, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) ok, COUNT(*) total
        FROM query_results WHERE collection_run_id=:rid GROUP BY platform ORDER BY platform
    """), {"rid": collection_run_id})
    data["platforms"] = [dict(r._mapping) for r in plat.fetchall()]

    hall = await db.execute(text("""
        SELECT severity, verdict, COUNT(*) c FROM hallucination_results
        WHERE collection_run_id=:rid GROUP BY severity, verdict ORDER BY severity, verdict
    """), {"rid": collection_run_id})
    data["hallucinations"] = [dict(r._mapping) for r in hall.fetchall()]
    data["hall_total"] = sum(h["c"] for h in data["hallucinations"])
    data["hall_incorrect"] = sum(h["c"] for h in data["hallucinations"]
                                  if h["verdict"] in (HallucinationVerdict.CONTRADICTED, HallucinationVerdict.UNSUPPORTED))
    data["p0_hall_count"] = sum(h["c"] for h in data["hallucinations"] if h["severity"] == "P0")

    # Hallucination examples for report
    hall_ex = await db.execute(text("""
        SELECT field_name, ai_claim, ground_truth_value, severity
        FROM hallucination_results
        WHERE collection_run_id=:rid AND verdict IN ('contradicted','unsupported') AND severity IN ('P0','P1')
        ORDER BY CASE severity WHEN 'P0' THEN 0 ELSE 1 END LIMIT 5
    """), {"rid": collection_run_id})
    data["hall_examples"] = [dict(r._mapping) for r in hall_ex.fetchall()]

    # P2-1: claim nature distribution
    cn_rows = await db.execute(text("""
        SELECT claim_type, severity, verdict, COUNT(*) c
        FROM hallucination_results
        WHERE collection_run_id=:rid
        GROUP BY claim_type, severity, verdict
        ORDER BY claim_type, severity, verdict
    """), {"rid": collection_run_id})
    cn_data = [dict(r._mapping) for r in cn_rows.fetchall()]
    data["claim_nature_distribution"] = cn_data
    # Build claim_nature × verdict matrix
    cn_matrix = {}
    for row in cn_data:
        cn = row["claim_type"] or "unknown"
        ver = row["verdict"]
        if cn not in cn_matrix:
            cn_matrix[cn] = {}
        cn_matrix[cn][ver] = cn_matrix[cn].get(ver, 0) + row["c"]
    data["claim_nature_verdict_matrix"] = cn_matrix

    # P2-2: evidence strength summary from quality_summary
    cr_qs = (await db.execute(text("""
        SELECT report_quality_summary_json FROM collection_runs WHERE id = :rid
    """), {"rid": collection_run_id})).scalar()
    if cr_qs and isinstance(cr_qs, dict):
        data["evidence_strength"] = cr_qs.get("evidence_strength", {})

    # Action themes
    act = await db.execute(text("""
        SELECT id, theme_name, priority, summary, target_kpis, suggested_content_type
        FROM action_themes WHERE brand_id=:bid ORDER BY
        CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, created_at DESC LIMIT 10
    """), {"bid": brand.get("id")})
    data["action_themes"] = [dict(r._mapping) for r in act.fetchall()]

    # Content packages
    cp = await db.execute(text("""
        SELECT id, content_items, schema_items, fact_check_report, publishing_checklist, status
        FROM content_packages WHERE brand_id=:bid ORDER BY created_at DESC LIMIT 10
    """), {"bid": brand.get("id")})
    data["content_packages"] = [dict(r._mapping) for r in cp.fetchall()]

    return data


# ── Builders ─────────────────────────────────────────────────────────────────

def _build_kpi_list(data: dict) -> list[dict]:
    kpis = []
    base_keys = ["sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"]
    for key in base_keys:
        value = data.get(key) or 0
        kpis.append({
            "key": key,
            "name": KPI_CUSTOMER_LANGUAGE.get(key, {}).get("label", key),
            "value": float(value),
            "sample_size": data.get("sample_size", 0),
            "customer_label": KPI_CUSTOMER_LANGUAGE.get(key, {}).get("label", ""),
            "explanation": _explain_kpi(key, float(value), data),
            "verdict": get_kpi_verdict(key, float(value)),
            "customer_advice": KPI_CUSTOMER_LANGUAGE.get(key, {}).get("action", ""),
        })
    for key, v in (data.get("extended_kpis") or {}).items():
        value = v.get("value", 0) if isinstance(v, dict) else v
        kpis.append({
            "key": key,
            "name": KPI_CUSTOMER_LANGUAGE.get(key, {}).get("label", key),
            "value": float(value) if value else 0,
            "sample_size": v.get("sample_size", 0) if isinstance(v, dict) else 0,
            "customer_label": KPI_CUSTOMER_LANGUAGE.get(key, {}).get("label", ""),
            "explanation": _explain_kpi(key, float(value or 0), data),
            "verdict": get_kpi_verdict(key, float(value or 0)),
            "customer_advice": KPI_CUSTOMER_LANGUAGE.get(key, {}).get("action", ""),
        })
    return kpis


def _explain_kpi(key: str, value: float, data: dict) -> str:
    cfg = KPI_CUSTOMER_LANGUAGE.get(key, {})
    label = cfg.get("label", key)
    sample = data.get("sample_size", 0)
    v_pct = f"{value:.0%}"
    verdict = get_kpi_verdict(key, value)
    if verdict == "good":
        status = "表现良好"
    elif verdict == "warning":
        status = "需要关注"
    else:
        status = "需要改善"
    return f"{label}为 {v_pct}，{status}。（样本量：{sample} 条 AI 回答）"


def _build_key_findings(data: dict) -> list[dict]:
    findings = []
    for h in data.get("hall_examples", []):
        findings.append({
            "rank": len(findings) + 1,
            "title": h.get("field_name", "未知字段"),
            "severity": h.get("severity", "P2"),
            "ai_claim": str(h.get("ai_claim", ""))[:300],
            "correct_fact": str(h.get("ground_truth_value", ""))[:300],
            "source": "品牌事实库 (GT)",
            "impact_kpis": ["accuracy_rate", "citation_rate"],
            "recommendation": f"核实并更正关于「{h.get('field_name', '')}」的官方信息",
            "evidence_level": "medium",
        })
    return findings


def _build_actions(data: dict) -> list[dict]:
    actions = []
    for at in data.get("action_themes", []):
        actions.append({
            "priority": at.get("priority", "P2"),
            "problem": at.get("summary", ""),
            "target_kpi": at.get("target_kpis", [])[0] if at.get("target_kpis") else "",
            "content_asset": at.get("suggested_content_type", ""),
            "publish_location": "官网相关页面",
            "owner_role": "内容团队",
            "materials_needed": "品牌事实库对应字段",
            "review_required": "品牌负责人审核",
            "timeline": "1-2 周",
            "acceptance_criteria": f"复测时 {at.get('target_kpis', ['相关KPI'])[0] if at.get('target_kpis') else '相关指标'} 改善",
            "recheck_timing": "内容发布后 2-4 周",
            "action_theme_id": str(at.get("id", "")),
            "content_package_id": None,
        })
    return actions


def _build_sample_notes(data: dict) -> str:
    pcount = len(data.get("platforms", []))
    qcount = data.get("total_queries", 0)
    scount = data.get("success_count", 0)
    fcount = data.get("failure_count", 0)
    note = f"基于 {pcount} 个 AI 平台、{qcount} 个问题、共 {scount} 条有效 AI 回答。"
    if fcount > 0:
        note += f" {fcount} 条查询失败，部分结果可能被低估。"
    return note


def _audience_profile(edition: str) -> dict:
    profiles = {
        "executive": {
            "edition": "executive", "reader_role": "CEO / CMO / 品牌负责人",
            "reading_goal": "了解品牌在 AI 中的整体状态和最紧迫问题",
            "language_style": "简洁、结论先行、零技术术语",
            "detail_level": "low",
        },
        "implementation": {
            "edition": "implementation", "reader_role": "市场运营 / 内容团队 / SEO 团队",
            "reading_goal": "获得可立即执行的优化方案和优先级",
            "language_style": "行动导向、可操作、绑定责任和验收",
            "detail_level": "medium",
        },
        "customer": {
            "edition": "customer", "reader_role": "客户项目负责人 / 品牌团队",
            "reading_goal": "全面了解品牌 AI 认知状况、误解和优化方向",
            "language_style": "客户友好、解释充分、证据可信",
            "detail_level": "high",
        },
    }
    return profiles.get(edition, profiles["customer"])


# ── Methodology (customer-friendly) ─────────────────────────────────────────

def _methodology_how_we_ask() -> str:
    return (
        "我们通过多个主流 AI 平台，以真实用户可能提出的问题来询问 AI，"
        "观察 AI 如何描述品牌、是否推荐品牌、推荐的理由是否充分。"
    )


def _methodology_how_we_judge() -> str:
    return (
        "我们将 AI 的回答与品牌官方事实库（基于官网、官方文档等权威来源）进行比对，"
        "判断 AI 的描述是否准确、完整，以及是否存在与事实不符的信息。"
    )


def _methodology_how_we_score() -> str:
    return (
        "健康度评分综合考虑多项指标，每项指标根据行业特点赋予不同权重。"
        "评分仅反映当前采集周期的 AI 平台表现，不代表所有用户在所有场景下的体验。"
    )


def _methodology_limitations() -> str:
    return (
        "本报告基于指定时间范围内的 AI 平台回答生成，不代表所有 AI 平台或所有用户问题。"
        "AI 平台的行为可能因模型更新、训练数据变化而波动。"
        "优化效果需通过后续复测验证。"
        "报告用于品牌 AI 认知诊断和内容优化参考，不构成法律、医疗、金融、投资等专业意见。"
    )
