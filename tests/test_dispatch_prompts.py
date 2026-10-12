"""子 agent 调度外壳固化（2026-09-18）：模板含关键约束，format 后可派发。"""
from src.collector.dispatch_prompts import ATTRIBUTION_DISPATCH, HIT_DISPATCH


def test_attribution_dispatch_has_core_constraints():
    p = ATTRIBUTION_DISPATCH.format(platform="kimi", path="/tmp/x.json")
    for k in ("归因劣势提取", "kimi", "/tmp/x.json", "三态裁决", "evidence", "corpus_fact",
              "逐字", "优势维度主题全覆盖", "劣势判定铁律", "只输出", "没有写文件权限"):
        assert k in p, f"调度外壳缺 {k}"


def test_hit_dispatch_has_core_constraints():
    p = HIT_DISPATCH.format(platform="deepseek", path="/tmp/y.json")
    for k in ("命中判定员", "deepseek", "/tmp/y.json", "recommendation", "hotels_recommended",
              "必须完整列出", "scene", "只输出", "没有写文件权限"):
        assert k in p, f"命中调度外壳缺 {k}"


def test_dispatch_formats_are_stable():
    """同平台同路径 format 输出恒定（防模板被会话临时改动）。"""
    a1 = ATTRIBUTION_DISPATCH.format(platform="doubao", path="/tmp/z.json")
    a2 = ATTRIBUTION_DISPATCH.format(platform="doubao", path="/tmp/z.json")
    assert a1 == a2
