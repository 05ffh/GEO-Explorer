"""渲染冒烟：含关键业务字符串 + 不含技术词。"""
from src.report.geo_report import render_report


_DATA = {"brand": "香格里拉", "city": "福州", "hit_rate": 0.7873, "question_count": 28,
         "platform_hit_rates": {"deepseek": 0.9375}, "competitors": {"main": [], "secondary": []},
         "scenes": [], "attribution": {}, "sentiment": {"themes": {}}, "content_assets": [],
         "effective_visibility": 0.6917, "negative_rate": 0.1735, "appendix": {}}
_NARR = {"exec_summary": {"conclusion": "结论", "highlights": [], "risks": [], "priority": []},
         "sections": {}}


def test_render_contains_brand_and_rate():
    html = render_report(_DATA, _NARR, brand="香格里拉", city="福州", date="2026-10-14")
    assert "福州香格里拉" in html and "78.7%" in html


def test_render_has_no_technical_words():
    html = render_report(_DATA, _NARR, brand="香格里拉", city="福州", date="2026-10-14")
    for bad in ("脚本", "JSON", "字段", "measurement", "judgment"):
        assert bad not in html, f"报告不应出现技术词：{bad}"
