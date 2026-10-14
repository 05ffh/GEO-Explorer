"""报告数据提取：从 V6 快照产出报告所需字段（纯函数，喂 mock run）。"""
from src.report.report_data import build_report_data


def _run(measurement, **extra):
    class R:
        pass
    r = R()
    r.measurement_json = measurement
    r.gt_facts_json = extra.get("gt", {})
    r.cdp_facts_json = extra.get("cdp", {})
    r.sentiment_json = extra.get("sentiment", {})
    r.positioning_json = extra.get("positioning", {})
    r.brand = extra.get("brand", "香格里拉")
    r.city = extra.get("city", "福州")
    return r


_M = {
    "overall": {"overall_hit_rate": 0.7873,
                "platform_hit_rates": {"deepseek": 0.9375, "kimi": 0.875,
                                       "doubao": 0.875, "wenxin": 0.4615}},
    "effective_visibility": 0.6917,
    "negative_rate_combined": 0.1735,
    "miss_structure": {"structural": 6, "true_disadvantage": 6},
    "competitor_visibility": {"bands": {"福州世茂洲际酒店": "main"},
                              "overall": {"main": {"status": "ok", "members": [
                                  {"name": "福州世茂洲际酒店", "overall_rate": 0.5336,
                                   "platform_rates": {"deepseek": 0.9375}}]},
                              "secondary": {"status": "ok", "members": []}}},
    "attribution_dims": {"设施": {"advantage": 22, "disadvantage": 24,
                                 "true_disadvantage": 22, "advantage_evidence": ["a"],
                                 "disadvantage_evidence": ["b"]}},
    "content_assets": [{"content": "地址：福州市鼓楼区新权南路9号", "count": 2}],
    "platforms": {"deepseek": {"judgments": [
        {"layer": "hit", "question_id": "hit_b1", "question": "福州市中心有哪些高端酒店推荐",
         "recommendation": "recommend", "has_hotel_recommendations": True,
         "hotels_recommended": ["福州香格里拉大酒店"], "referred_content": ["老牌五星，位置核心"],
         "scene": {"dim": "region", "val": "五一广场", "rank_in_scene": 1, "in_scene_count": 3}}]}},
    "question_fingerprint": ["hit_b1"],
}


def test_hit_rates_and_derived():
    d = build_report_data(_run(_M))
    assert d["hit_rate"] == 0.7873
    assert d["platform_hit_rates"]["deepseek"] == 0.9375
    assert d["effective_visibility"] == 0.6917
    assert d["negative_rate"] == 0.1735


def test_competitors_banded():
    d = build_report_data(_run(_M))
    assert d["competitors"]["main"][0]["name"] == "福州世茂洲际酒店"
    assert d["competitors"]["main"][0]["rate"] == 0.5336


def test_scenes_grouped_from_client_yaml():
    d = build_report_data(_run(_M))
    # hit_b1 归到「商旅」场景（client yaml 的 scenario 字段）
    assert any(s["name"] == "商旅" for s in d["scenes"])


def test_sentiment_and_attribution():
    d = build_report_data(_run(_M, sentiment={"store_level": {
        "rate": 0.1735, "total": 98, "negative_count": 17,
        "themes": {"hygiene": 12, "service": 3, "dining": 2, "price": 1}}}))
    assert d["sentiment"]["themes"]["卫生"] == 12
    assert d["attribution"]["设施"]["true_disadvantage"] == 22
