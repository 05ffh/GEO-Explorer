"""export_answers 命中题判定块渲染（场景容错，2026-10-14：rank 缺时降级不显示 null）。"""
from scripts.export_answers import judge_block


def _hit_j(**kw):
    j = {"layer": "hit", "question_id": "hit_b1", "recommendation": "recommend",
         "same_tier_pushed": False, "referred_content": [], "has_hotel_recommendations": True}
    j.update(kw)
    return j


def test_scene_with_rank_renders_full():
    out = judge_block(_hit_j(scene={"dim": "region", "val": "五一广场",
                                    "rank_in_scene": 1, "in_scene_count": 8}))
    assert "区域「五一广场」rank 1/8" in out


def test_scene_without_rank_degrades_not_null():
    """rank 缺（子 agent 未给）→ 显示 维度「场景名」，不显示 null。"""
    out = judge_block(_hit_j(scene={"dim": "region", "val": "五一广场"}))
    assert "区域「五一广场」" in out and "null" not in out


def test_scene_absent_shows_null():
    out = judge_block(_hit_j(recommendation="absent", scene=None))
    assert "场景**：null" in out
