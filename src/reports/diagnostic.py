"""Generate Markdown diagnostic reports from GEO collection data."""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from src.schemas.ground_truth import KPI_DISPLAY_NAMES


def _kpi_bar(value: float, width: int = 20) -> str:
    filled = int(abs(value) * width)
    return "█" * filled + "░" * (width - filled)


async def generate_diagnostic_report(
    brand_name: str,
    collection_run_id: str,
    brand_id: str,
    db: AsyncSession,
    output_dir: str = "reports",
) -> str:
    """Generate a full Markdown diagnostic report for a brand collection run."""
    rows = await db.execute(text("""
        SELECT
            cr.collection_status, cr.analysis_status,
            cr.total_queries, cr.success_count, cr.failure_count,
            cr.collection_completed_at, cr.created_at,
            ms.sov, ms.first_rec_rate, ms.accuracy_rate,
            ms.completeness_rate, ms.citation_rate,
            ms.sample_size, ms.failure_rate, ms.details
        FROM collection_runs cr
        LEFT JOIN metrics_snapshots ms ON ms.collection_run_id = cr.id
        WHERE cr.id = :rid
        ORDER BY ms.created_at DESC LIMIT 1
    """), {"rid": collection_run_id})
    row = rows.fetchone()
    if not row:
        raise ValueError(f"Collection run {collection_run_id} not found")
    d = dict(row._mapping)

    # Per-platform breakdown
    plat_rows = await db.execute(text("""
        SELECT platform, COUNT(*) total,
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) ok
        FROM query_results WHERE collection_run_id=:rid
        GROUP BY platform ORDER BY platform
    """), {"rid": collection_run_id})
    platforms = [dict(r._mapping) for r in plat_rows.fetchall()]

    # Hallucination summary
    hall_rows = await db.execute(text("""
        SELECT severity, verdict, COUNT(*) c
        FROM hallucination_results WHERE collection_run_id=:rid
        GROUP BY severity, verdict ORDER BY severity, verdict
    """), {"rid": collection_run_id})
    hallucinations = [dict(r._mapping) for r in hall_rows.fetchall()]
    total_hall = sum(h["c"] for h in hallucinations)

    # Action plans
    ap_rows = await db.execute(text("""
        SELECT priority, status, COUNT(*) c
        FROM action_plans WHERE brand_id=:bid
        GROUP BY priority, status ORDER BY priority
    """), {"bid": brand_id})
    action_plans = [dict(r._mapping) for r in ap_rows.fetchall()]
    total_ap = sum(a["c"] for a in action_plans)

    # Extended KPIs
    details = d["details"] or {}
    extended_kpis = details.get("extended_kpis", {})

    # Build Markdown
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"# {brand_name} GEO 诊断报告")
    lines.append(f"")
    lines.append(f"**生成时间:** {now}  ")
    lines.append(f"**采集状态:** {d['collection_status']} / 分析: {d['analysis_status']}  ")
    lines.append(f"**查询统计:** {d['success_count']}/{d['total_queries']} 成功, {d['failure_count']} 失败  ")
    lines.append(f"**采集耗时:** {d['collection_completed_at'] or d['created_at']}  ")
    lines.append(f"")

    # Platform table
    lines.append(f"## 平台采集概况")
    lines.append(f"")
    lines.append(f"| 平台 | 成功 | 总数 | 成功率 |")
    lines.append(f"|------|------|------|--------|")
    for p in platforms:
        rate = p["ok"] / p["total"] * 100 if p["total"] else 0
        lines.append(f"| {p['platform']} | {p['ok']} | {p['total']} | {rate:.0f}% |")
    lines.append(f"")

    # KPI scores
    lines.append(f"## 10 项 KPI 评分")
    lines.append(f"")
    lines.append(f"| 指标 | 得分 | 可视化 | 样本量 |")
    lines.append(f"|------|------|--------|--------|")

    base_kpis = [
        ("sov", d.get("sov", 0) or 0),
        ("first_rec_rate", d.get("first_rec_rate", 0) or 0),
        ("accuracy_rate", d.get("accuracy_rate", 0) or 0),
        ("completeness_rate", d.get("completeness_rate", 0) or 0),
        ("citation_rate", d.get("citation_rate", 0) or 0),
    ]
    for key, value in base_kpis:
        name = KPI_DISPLAY_NAMES.get(key, key)
        lines.append(f"| {name} | {value:.1%} | {_kpi_bar(value)} | {d.get('sample_size', 0)} |")

    for key, v in extended_kpis.items():
        name = KPI_DISPLAY_NAMES.get(key, key)
        value = v.get("value", 0)
        n = v.get("sample_size", 0)
        lines.append(f"| {name} | {value:.1%} | {_kpi_bar(value)} | {n} |")
    lines.append(f"")

    # Hallucinations
    lines.append(f"## 幻觉检测: {total_hall} 条")
    lines.append(f"")
    if hallucinations:
        lines.append(f"| 严重度 | 判定 | 数量 |")
        lines.append(f"|--------|------|------|")
        sev_label = {"P0": "致命", "P1": "重要", "P2": "改善"}
        v_label = {
            "supported": "✓ 支持", "contradicted": "✗ 矛盾", "unsupported": "? 无支撑",
            "not_about_brand": "— 非品牌", "generic_statement": "— 通用陈述",
            "template_invalid": "⚠ 模板错误", "gt_insufficient": "? GT不足",
            "ambiguous": "? 模糊", "not_checkable": "— 不可核验",
            "incorrect": "✗ 错误", "correct": "✓ 正确", "uncertain": "? 不确定",
        }
        for h in hallucinations:
            sl = sev_label.get(h["severity"], h["severity"])
            vl = v_label.get(h["verdict"], h["verdict"])
            lines.append(f"| {sl} | {vl} | {h['c']} |")
    lines.append(f"")

    # Action Plans
    lines.append(f"## 优化 Action Plans: {total_ap} 条")
    lines.append(f"")
    if action_plans:
        lines.append(f"| 优先级 | 状态 | 数量 |")
        lines.append(f"|--------|------|------|")
        for a in action_plans:
            lines.append(f"| {a['priority']} | {a['status']} | {a['c']} |")
    lines.append(f"")

    # Top P0 issues
    p0_rows = await db.execute(text("""
        SELECT field_name, ai_claim, ground_truth_value, severity
        FROM hallucination_results
        WHERE collection_run_id=:rid AND verdict IN ('contradicted','unsupported') AND severity='P0'
        LIMIT 10
    """), {"rid": collection_run_id})
    p0s = [dict(r._mapping) for r in p0_rows.fetchall()]
    if p0s:
        lines.append(f"## Top 10 P0 致命错误")
        lines.append(f"")
        for i, p in enumerate(p0s, 1):
            lines.append(f"### {i}. {p['field_name']}")
            lines.append(f"")
            lines.append(f"**AI 错误声称:**  ")
            lines.append(f"> {str(p['ai_claim'])[:200]}")
            lines.append(f"")
            lines.append(f"**GT 事实:**  ")
            lines.append(f"> {str(p['ground_truth_value'])[:200]}")
            lines.append(f"")

    # Key findings
    lines.append(f"## 关键发现与建议")
    lines.append(f"")

    sov = d.get("sov", 0) or 0
    frr = d.get("first_rec_rate", 0) or 0
    acc = d.get("accuracy_rate", 0) or 0
    ss = extended_kpis.get("semantic_stability", {}).get("value", 0)

    lines.append(f"1. **声量份额 (SOV)**: {sov:.1%} — {'品牌在 AI 平台中被频繁提及，声量健康' if sov > 0.5 else '品牌提及率偏低，需要增加内容曝光'}")
    lines.append(f"2. **首次推荐率**: {frr:.1%} — {'AI 倾向于优先推荐该品牌' if frr > 0.3 else '在非品牌场景中很少被优先推荐，需要场景化内容布局'}")
    lines.append(f"3. **准确率**: {acc:.1%} — {'AI 描述与品牌事实高度一致' if acc > 0.5 else 'AI 描述与 GT 存在显著差异，需要纠正'}")
    lines.append(f"4. **语义锚点稳定度**: {ss:.1%} — {'各平台对品牌描述一致' if ss > 0.5 else '各平台对品牌认知碎片化严重，需要统一品牌信息投放'}")
    lines.append(f"5. **幻觉检测**: 共发现 {total_hall} 条声明，其中 {sum(h['c'] for h in hallucinations if h['verdict'] in ('contradicted','unsupported'))} 条与事实不符")
    lines.append(f"")

    # Save
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    safe_name = brand_name.replace(" ", "_").replace("/", "_")
    filename = f"{safe_name}_{date_str}_诊断报告.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
