"""报告叙述 lint：只查表征层（结构/数字/引述/技术词），非语义验证。"""
from src.report.narrative import _NARRATIVE_SPEC, answer_corpus, lint_narrative

_DATA = {"scenes": [{"name": "商旅"}, {"name": "餐饮"}, {"name": "亲子"}, {"name": "婚宴会议"}],
         "hit_rate": 0.7873, "effective_visibility": 0.7214, "negative_rate": 0.1196,
         "hit_question_count": 18, "gt_facts_count": 139}
_ANSWER = "鼓楼区中心，俯瞰五一广场、乌山和于山。设施**明显**老化，房间有点旧。"


def _narrative(**over):
    base = {
        "exec_summary": {"conclusion": "综合命中率 78.7%，有效可见度 72.1%。",
                         "highlights": [], "risks": [], "priority": []},
        "hit_rate_explain": "基于 18 个高频问题。",
        "scenes": {n["name"]: {"summary": "s", "quotes": []} for n in _DATA["scenes"]},
        "competitors": {"summary": "c"}, "sentiment": {"summary": "s"},
        "assets": {"summary": "139 条事实。"}, "attribution": {"key_quotes": []},
        "directions": [{"title": "t", "text": "d"}], "method": "m",
    }
    base.update(over)
    return base


def _answers(*texts):
    return answer_corpus({"platforms": {"deepseek": {"judgments": [{"answer": t} for t in texts]}}})


def _codes(problems, level):
    return [p["code"] for p in problems if p["level"] == level]


def test_spec_is_substantive_guidance():
    assert "受众" in _NARRATIVE_SPEC and "AI 原话" in _NARRATIVE_SPEC


def test_good_narrative_no_error():
    assert _codes(lint_narrative(_DATA, _narrative(), _answers(_ANSWER)), "error") == []


def test_structure_missing_key_blocks():
    n = _narrative()
    del n["method"]
    assert "structure" in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "error")


def test_structure_missing_scene_blocks():
    n = _narrative(scenes={"商旅": {"summary": "s", "quotes": []}})   # 缺 3 场景
    assert "structure" in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "error")


def test_quote_verbatim_with_markdown_norm():
    n = _narrative(scenes={k: {"summary": "s", "quotes": ["设施明显老化"]}   # 原文含 **
                           for k in ("商旅", "餐饮", "亲子", "婚宴会议")})
    assert "quote" not in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "error")


def test_quote_fabricated_warns_not_blocks():
    """引述核对只 warn（忠实拼接允许，脚本分不清拼接与编造 → 交主 agent 确认）。"""
    n = _narrative(scenes={k: {"summary": "s", "quotes": ["设施严重老化"]}   # 非原话
                           for k in ("商旅", "餐饮", "亲子", "婚宴会议")})
    p = lint_narrative(_DATA, n, _answers(_ANSWER))
    assert "quote" in _codes(p, "warn")
    assert "quote" not in _codes(p, "error")


def test_quote_faithful_reassembly_ok():
    """忠实拼接：叙述把 AI 分处两句的原话拼成一句 → 分段各自命中 → 无 warn。"""
    n = _narrative(attribution={"key_quotes": ["米其林一星餐厅「江南灶·融府」（酒店2楼）"]})
    ans = _answers("米其林一星餐厅「江南灶·融府」，商务设施完善", "餐厅位置：酒店2楼")
    assert "quote" not in _codes(lint_narrative(_DATA, n, ans), "warn")


def test_quote_ellipsis_segments():
    n = _narrative(attribution={"key_quotes": ["鼓楼区中心…房间有点旧"]})
    assert "quote" not in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "error")


def test_quote_mark_and_punct_variant_ok():
    """叙述用全角引号/标点，AI 原文用半角——归一后应判为原话（防假阳性）。"""
    n = _narrative(attribution={"key_quotes": ["有人觉得“老旧”但保养好"]})
    ans = _answers('有人觉得"老旧"但保养好')
    assert "quote" not in _codes(lint_narrative(_DATA, n, ans), "error")


def test_techword_warn_and_url_excluded():
    n = _narrative(method="用脚本渲染生成的。")
    assert "techword" in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "warn")
    n2 = _narrative(method="http://example.com/script-api")
    assert "techword" not in _codes(lint_narrative(_DATA, n2, _answers(_ANSWER)), "warn")


def test_number_labeled_mismatch_blocks():
    n = _narrative(exec_summary={"conclusion": "综合命中率 82.0%。", "highlights": [],
                                 "risks": [], "priority": []})
    e = lint_narrative(_DATA, n, _answers(_ANSWER))
    assert "number" in _codes(e, "error")
    assert any("78.7%" in p["msg"] for p in e if p["code"] == "number")


def test_number_count_mismatch_blocks():
    n = _narrative(assets={"summary": "140 条事实。"})
    assert "number" in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "error")


def test_unlabeled_number_not_checked():
    """未标指标名的数字脚本判不了 → 不报（交主 agent 读）。"""
    n = _narrative(competitors={"summary": "它的命中率（53.4%）已反超。"})
    assert "number" not in _codes(lint_narrative(_DATA, n, _answers(_ANSWER)), "error")
