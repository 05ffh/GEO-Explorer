"""Generate actionable optimization plans as PDF reports."""

import os
import subprocess
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


def _kpi_bar(value: float, width: int = 20) -> str:
    filled = int(abs(value) * width)
    return "█" * filled + "░" * (width - filled)


async def generate_optimization_plan(
    brand_name: str,
    collection_run_id: str,
    brand_id: str,
    db: AsyncSession,
    output_dir: str = "reports",
) -> dict:
    """Generate an actionable PDF optimization plan for enterprise clients."""
    # Fetch data
    rows = await db.execute(text("""
        SELECT cr.total_queries, cr.success_count, cr.failure_count,
               cr.collection_status, cr.analysis_status,
               ms.sov, ms.first_rec_rate, ms.accuracy_rate,
               ms.completeness_rate, ms.citation_rate, ms.sample_size, ms.details
        FROM collection_runs cr
        LEFT JOIN metrics_snapshots ms ON ms.collection_run_id = cr.id
        WHERE cr.id = :rid
        ORDER BY ms.created_at DESC LIMIT 1
    """), {"rid": collection_run_id})
    row = rows.fetchone()
    if not row:
        raise ValueError(f"Collection run {collection_run_id} not found")
    d = dict(row._mapping)

    # Action plans with details
    ap_rows = await db.execute(text("""
        SELECT priority, action_type, suggested_content_type,
               ai_wrong_claims, correct_ground_truth, acceptance_criteria, status
        FROM action_plans
        WHERE brand_id = :bid AND status = 'pending'
        ORDER BY CASE priority WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 ELSE 3 END
        LIMIT 30
    """), {"bid": brand_id})
    plans = [dict(r._mapping) for r in ap_rows.fetchall()]

    # Per-platform
    plat_rows = await db.execute(text("""
        SELECT platform,
               SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) ok,
               COUNT(*) total
        FROM query_results WHERE collection_run_id=:rid
        GROUP BY platform ORDER BY platform
    """), {"rid": collection_run_id})
    platforms = [dict(r._mapping) for r in plat_rows.fetchall()]

    extended_kpis = (d.get("details") or {}).get("extended_kpis", {})

    # Hallucination counts
    hall_rows = await db.execute(text("""
        SELECT severity, COUNT(*) c FROM hallucination_results
        WHERE collection_run_id=:rid AND verdict='incorrect'
        GROUP BY severity ORDER BY severity
    """), {"rid": collection_run_id})
    hall_counts = {r.severity: r.c for r in hall_rows.fetchall()}

    # Build Markdown content
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"# {brand_name} AI 品牌认知优化方案")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")
    lines.append(f"**文档类型:** 可落地实施优化方案  ")
    lines.append(f"**品牌:** {brand_name}  ")
    lines.append(f"**生成时间:** {now}  ")
    lines.append(f"**采集状态:** {d['collection_status']} | {d['success_count']}/{d['total_queries']} 查询成功  ")
    lines.append(f"")

    # Executive Summary
    lines.append(f"## 一、执行摘要")
    lines.append(f"")
    acc = d.get("accuracy_rate", 0) or 0
    sov = d.get("sov", 0) or 0
    frr = d.get("first_rec_rate", 0) or 0
    lines.append(f"本次 GEO 诊断共覆盖 {len(platforms)} 个 AI 平台，采集 {d['total_queries']} 条查询。")
    lines.append(f"品牌声量份额 **{sov:.1%}**，准确率 **{acc:.1%}**，首次推荐率 **{frr:.1%}**。")
    lines.append(f"共发现 {sum(hall_counts.values())} 条与事实不符的 AI 声明，生成 {len(plans)} 条优化任务。")
    lines.append(f"")

    # KPI overview
    lines.append(f"## 二、KPI 评分总览")
    lines.append(f"")
    lines.append(f"| 指标 | 得分 | 评估 |")
    lines.append(f"|------|------|------|")
    kpi_items = [
        ("sov", sov, "需提升" if sov < 0.5 else "良好"),
        ("first_rec_rate", frr, "需场景化布局" if frr < 0.3 else "良好"),
        ("accuracy_rate", acc, "需纠正 AI 认知" if acc < 0.5 else "良好"),
        ("completeness_rate", d.get("completeness_rate", 0) or 0, ""),
        ("citation_rate", d.get("citation_rate", 0) or 0, ""),
    ]
    from src.schemas.ground_truth import KPI_DISPLAY_NAMES
    for key, val, note in kpi_items:
        name = KPI_DISPLAY_NAMES.get(key, key)
        lines.append(f"| {name} | {val:.1%} {_kpi_bar(val, 15)} | {note} |")
    for key, v in extended_kpis.items():
        name = KPI_DISPLAY_NAMES.get(key, key)
        val = v.get("value", 0)
        lines.append(f"| {name} | {val:.1%} {_kpi_bar(val, 15)} | |")
    lines.append(f"")

    # Platform breakdown
    lines.append(f"## 三、平台表现")
    lines.append(f"")
    lines.append(f"| 平台 | 成功率 |")
    lines.append(f"|------|--------|")
    for p in platforms:
        rate = p["ok"] / p["total"] * 100 if p["total"] else 0
        lines.append(f"| {p['platform']} | {rate:.0f}% ({p['ok']}/{p['total']}) |")
    lines.append(f"")

    # Optimization Actions
    lines.append(f"## 四、优化执行方案（共 {len(plans)} 条）")
    lines.append(f"")

    priority_groups = {"P0": [], "P1": [], "P2": []}
    for plan in plans:
        priority_groups[plan["priority"]].append(plan)

    seq = 1
    for p_level, label, desc in [("P0", "致命错误 — 立即修复", "以下问题可能导致 AI 给出严重失实的品牌描述，建议 24 小时内完成纠正。"),
                                  ("P1", "重要偏差 — 优先修复", "以下问题影响品牌在 AI 中的认知质量，建议本周内完成。"),
                                  ("P2", "改善建议 — 计划修复", "以下问题影响品牌丰富度表达，建议本月内优化。")]:
        group = priority_groups[p_level]
        if not group:
            continue
        lines.append(f"### {seq}. {label}")
        seq += 1
        lines.append(f"")
        lines.append(f"{desc}")
        lines.append(f"")
        for i, plan in enumerate(group[:10], 1):
            ai_claim = str(plan.get("ai_wrong_claims", {}).get("claim", ""))[:150]
            gt = str(plan.get("correct_ground_truth", {}).get("value", ""))[:150]
            field = plan.get("correct_ground_truth", {}).get("field", "")
            lines.append(f"#### {seq-1}.{i} {plan['action_type']}: {field}")
            lines.append(f"")
            lines.append(f"- **AI 错误描述:** {ai_claim}")
            lines.append(f"- **应修正为:** {gt}")
            lines.append(f"- **建议内容类型:** {plan.get('suggested_content_type', 'FAQ')}")
            lines.append(f"- **验收标准:** {plan.get('acceptance_criteria', '')[:150]}")
            lines.append(f"- **实施步骤:**")
            lines.append(f"  1. 在官网/百科/GMB 等权威渠道确认正确信息")
            lines.append(f"  2. 更新品牌 Ground Truth 中的 `{field}` 字段")
            lines.append(f"  3. 生成 FAQ/Schema.org JSON-LD 内容")
            lines.append(f"  4. 发布到官方网站对应页面")
            lines.append(f"  5. 重新触发 GEO 采集，验证 AI 认知改善效果")
            lines.append(f"")

    # Implementation Roadmap
    lines.append(f"## 五、实施路线图")
    lines.append(f"")
    lines.append(f"| 阶段 | 时间 | 行动 | 预期效果 |")
    lines.append(f"|------|------|------|----------|")
    lines.append(f"| 第一阶段 | 第 1 周 | 修复 {len(priority_groups['P0'])} 条 P0 致命错误，更新核心字段 GT | Accuracy 提升至 50%+")
    lines.append(f"| 第二阶段 | 第 2-3 周 | 修复 {len(priority_groups['P1'])} 条 P1 重要偏差，发布 FAQ/Schema.org | First Rec 提升至 30%+")
    lines.append(f"| 第三阶段 | 第 1-2 月 | 优化 {len(priority_groups['P2'])} 条 P2 改善项，丰富场景化内容 | SOV 提升至 80%+")
    lines.append(f"| 持续优化 | 季度 | 定期采集诊断，持续监控 KPI 变化 | 维持品牌 AI 认知健康度")
    lines.append(f"")

    # Appendix
    lines.append(f"## 附录")
    lines.append(f"")
    lines.append(f"- **GEO Explorer 版本:** Phase 10")
    lines.append(f"- **采集时间:** {d.get('collection_status', 'N/A')}")
    lines.append(f"- **数据来源:** DeepSeek, Kimi, 豆包, DuckDuckGo")
    lines.append(f"- **采集查询数:** {d['total_queries']}")
    lines.append(f"- **成功查询数:** {d['success_count']}")
    lines.append(f"")

    # Save Markdown
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    safe_name = brand_name.replace(" ", "_").replace("/", "_")
    md_filename = f"{safe_name}_{date_str}_优化方案.md"
    md_path = os.path.join(output_dir, md_filename)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # Convert to PDF via md2pdf
    pdf_filename = f"{safe_name}_{date_str}_优化方案.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)

    try:
        home = os.path.expanduser("~")
        env = {
            **os.environ,
            "HOME": home,
            "PATH": f"{home}/.nvm/versions/node/v22.22.2/bin:{os.environ.get('PATH', '')}",
            "NVM_DIR": f"{home}/.nvm",
        }
        result = subprocess.run(
            ["md2pdf", md_path, pdf_path],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if result.returncode != 0:
            logger.error("md2pdf failed: %s", result.stderr)
            pdf_path = None
    except Exception as e:
        logger.exception("md2pdf conversion failed")
        pdf_path = None

    return {
        "markdown": os.path.abspath(md_path),
        "pdf": os.path.abspath(pdf_path) if pdf_path else None,
        "action_count": len(plans),
        "p0_count": len(priority_groups["P0"]),
        "p1_count": len(priority_groups["P1"]),
        "p2_count": len(priority_groups["P2"]),
    }
