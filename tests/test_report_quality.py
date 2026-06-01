"""Tests for report quality checker (P1-6)."""
from src.reports.report_quality import check_report_quality


class TestReportQuality:
    def test_passes_clean_executive(self):
        md = """# Test
## 一句话结论
一切正常。
## 关键数字
| 指标 | 值 |
## 最大风险
无。
## 建议行动
继续保持。"""
        result = check_report_quality(md, "executive")
        assert result["status"] in ("passed", "warning")

    def test_fails_on_forbidden_terms(self):
        md = "品牌一定会在 AI 中被推荐"
        result = check_report_quality(md, "executive")
        violations = [v for v in result["violations"] if v["check"] == "forbidden_absolute_terms"]
        assert len(violations) > 0

    def test_fails_on_empty_placeholder(self):
        md = "品牌 {{ name }} 报告"
        result = check_report_quality(md, "customer")
        violations = [v for v in result["violations"] if v["check"] == "empty_placeholder"]
        assert len(violations) > 0

    def test_executive_required_sections(self):
        md = "空报告"
        result = check_report_quality(md, "executive")
        violations = [v for v in result["violations"] if v["check"] == "missing_section"]
        assert len(violations) > 0

    def test_implementation_requires_action_table(self):
        md = "# 执行方案\n无表格。"
        result = check_report_quality(md, "implementation")
        violations = [v for v in result["violations"] if v["check"] == "missing_action_table"]
        assert len(violations) > 0

    def test_executive_technical_term_fails(self):
        md = "SOV 较低，需要关注"
        result = check_report_quality(md, "executive")
        violations = [v for v in result["violations"] if v["check"] == "technical_term_in_executive"]
        assert len(violations) > 0

    def test_customer_few_kpi_explanations(self):
        md = "# 报告\n得分: 50"
        result = check_report_quality(md, "customer")
        violations = [v for v in result["violations"] if v["check"] == "few_kpi_explanations"]
        assert len(violations) > 0

    def test_quality_status_scoring(self):
        md = "完全通过的干净报告。\n## 一句话结论\nOK\n## 关键数字\nOK\n## 最大风险\nOK\n## 建议行动\nOK"
        result = check_report_quality(md, "executive")
        assert result["status"] in ("passed", "warning")
        assert 0 <= result["score"] <= 100
