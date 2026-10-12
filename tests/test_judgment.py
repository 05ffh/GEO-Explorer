"""judgment 结构 schema 测试（A-1.5）：枚举契约 + 骨架默认值 + scene 结构。"""

from src.collector import judgment as J


def test_layer_enums():
    assert J.LAYER_HIT == "hit"
    assert J.LAYER_ATTRIBUTION == "attribution"
    assert set(J.LAYER_VALUES) == {"hit", "attribution"}


def test_recommendation_enums():
    assert J.RECOMMEND == "recommend"
    assert J.MENTION == "mention"
    assert J.EXCLUDE == "exclude"
    assert J.ABSENT == "absent"
    assert len(J.RECOMMENDATION_VALUES) == 4
    assert "顶奢" not in J.RECOMMENDATION_VALUES


def test_scene_dims():
    assert J.SCENE_DIM_REGION == "region"
    assert J.SCENE_DIM_TIER == "tier"
    assert J.SCENE_DIM_TOPIC == "topic"
    assert J.SCENE_DIM_CATEGORY == "category"
    assert J.SCENE_DIM_BUDGET == "budget"
    assert len(J.SCENE_DIMS) == 5


def test_answer_forms():
    assert J.ANSWER_FORM_LIST == "list"
    assert J.ANSWER_FORM_PROSE == "prose"
    assert J.ANSWER_FORM_TABLE == "table"


def test_new_judgment_defaults():
    j = J.new_judgment("hit_family_facility", J.LAYER_HIT, "deepseek")
    assert j["question_id"] == "hit_family_facility"
    assert j["layer"] == J.LAYER_HIT
    assert j["platform"] == "deepseek"
    # 语义字段默认 None/空，待子 agent 填
    assert j["recommendation"] is None
    assert j["scene"] is None
    assert j["same_tier_pushed"] is None
    assert j["answer_tier_distribution"] is None
    assert j["referred_content"] == []
    assert j["has_hotel_recommendations"] is None
    # 默认全 needs_agent（recommendation 语义判定不默认）
    assert j["needs_agent"] is True
    assert j["hit"] is None
    assert j["judge_source"] == "agent"


def test_new_judgment_keeps_question_answer():
    j = J.new_judgment("q1", J.LAYER_HIT, "kimi", question="福州带娃住哪家酒店好", answer="推荐悦华…")
    assert j["question"] == "福州带娃住哪家酒店好"
    assert j["answer"] == "推荐悦华…"


def test_new_judgment_error_override():
    j = J.new_judgment("q1", J.LAYER_HIT, "doubao")
    j["needs_agent"] = False
    j["reason"] = "error"
    assert j["needs_agent"] is False
    assert j["reason"] == "error"
