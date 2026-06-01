"""Report quality checker — per-edition hard gates (P1-6)."""
from src.reports.customer_language import (
    TECH_TERM_REPLACEMENTS, FORBIDDEN_ABSOLUTE_TERMS, contains_forbidden_terms,
)

EXECUTIVE_REQUIRED_SECTIONS = ["一句话结论", "关键数字", "最大风险", "建议行动"]
IMPLEMENTATION_REQUIRED_SECTIONS = ["当前状态", "优先级行动清单", "审核要求", "复测验证计划"]
CUSTOMER_REQUIRED_SECTIONS = ["品牌 AI 认知仪表盘", "AI 对品牌的主要误解", "数据质量说明", "优化建议", "附录：方法论"]


def check_report_quality(md_content: str, edition: str) -> dict:
    """Check report against edition-specific quality gates.

    Returns {"status": "passed"|"warning"|"failed", "violations": [...], "score": 0-100}.
    """
    violations = []
    score = 100

    # 1. Forbidden absolute terms (all editions)
    forbidden = contains_forbidden_terms(md_content)
    if forbidden:
        score -= len(forbidden) * 5
        violations.append({
            "level": "error", "check": "forbidden_absolute_terms",
            "message": f"报告包含绝对承诺词: {', '.join(forbidden)}",
        })

    # 2. Empty placeholders
    if "{{" in md_content or "}}" in md_content:
        score -= 10
        violations.append({
            "level": "error", "check": "empty_placeholder",
            "message": "报告包含未填充的模板占位符",
        })

    # 3. Required sections
    required = {
        "executive": EXECUTIVE_REQUIRED_SECTIONS,
        "implementation": IMPLEMENTATION_REQUIRED_SECTIONS,
        "customer": CUSTOMER_REQUIRED_SECTIONS,
    }.get(edition, [])

    for section in required:
        if section not in md_content:
            score -= 10
            violations.append({
                "level": "error", "check": "missing_section",
                "message": f"缺少必要章节: {section}",
            })

    # 4. Edition-specific: Executive technical term strict check
    if edition == "executive":
        for term in TECH_TERM_REPLACEMENTS:
            if term in md_content and _not_in_skip_region(md_content, term):
                score -= 5
                violations.append({
                    "level": "error", "check": "technical_term_in_executive",
                    "message": f"高管摘要包含技术术语: {term}",
                })

    # 5. Edition-specific: Implementation must have action table
    if edition == "implementation":
        if "|" not in md_content or "内容资产" not in md_content:
            score -= 15
            violations.append({
                "level": "error", "check": "missing_action_table",
                "message": "执行版缺少行动清单表格",
            })

    # 6. Edition-specific: Customer must have KPI explanations
    if edition == "customer":
        kpi_count = md_content.count("得分:")
        if kpi_count < 3:
            score -= 10
            violations.append({
                "level": "warning", "check": "few_kpi_explanations",
                "message": f"客户版仅包含 {kpi_count} 项 KPI 解释",
            })

    # Determine status
    if score >= 80:
        status = "passed"
    elif score >= 60:
        status = "warning"
    else:
        status = "failed"

    return {"status": status, "violations": violations, "score": score}


def _not_in_skip_region(text: str, term: str) -> bool:
    """Check if term appears outside skip regions (code blocks, URLs, etc.)."""
    import re
    idx = text.find(term)
    if idx == -1:
        return False
    # Simple check: if it's inside ``` blocks
    code_blocks = list(re.finditer(r'```[\s\S]*?```', text))
    for cb in code_blocks:
        if cb.start() <= idx < cb.end():
            return False
    # If inside URL
    urls = list(re.finditer(r'https?://\S+', text))
    for u in urls:
        if u.start() <= idx < u.end():
            return False
    return True
