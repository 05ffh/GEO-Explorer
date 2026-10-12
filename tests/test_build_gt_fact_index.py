"""GT 事实清单可追溯回填（2026-09-18 架构「协议+元数据」）单测。

源追溯 = 页级（事实 token 出现在哪页原文）；只认 http 真 URL（坏 URL 如
`baike.baidu.com/cvent` 不可靠 → 宁标 verified 不硬塞）。幂等（默认只补缺字段）。
"""
from scripts.build_gt_fact_index import annotate_facts


def test_annotate_traces_to_best_http_page():
    facts = {"facts": {"餐饮": [{"fact": "江南灶·融府，淮扬菜，米其林一星", "source_tier": "T0"}]}}
    rows = [
        ("https://www.shangri-la.com/fuzhou/dining/", "江南灶·融府 淮扬菜 米其林一星 12间包厢"),
        ("baike.baidu.com/cvent", "江南灶·融府 淮扬菜 米其林一星"),  # 坏 URL 不认
    ]
    new, stats = annotate_facts(facts, rows, "2026-09-18")
    it = new["facts"]["餐饮"][0]
    assert it["source_url"] == "https://www.shangri-la.com/fuzhou/dining/"
    assert it["source_kind"] == "corpus"
    assert it["captured_at"] == "2026-09-18"
    assert stats["traced"] == 1


def test_annotate_marks_verified_when_only_bad_url():
    """只有坏 URL 支撑时 → verified（不硬塞脏 URL，宁标联网/人工核验）。"""
    facts = {"facts": {"餐饮": [{"fact": "韩香馆已停业", "source_tier": "T1"}]}}
    rows = [("baike.baidu.com/cvent", "韩香馆 韩国烧烤 在营")]
    new, stats = annotate_facts(facts, rows, "2026-09-18")
    it = new["facts"]["餐饮"][0]
    assert it["source_url"] == ""
    assert it["source_kind"] == "verified"
    assert stats["untraced"] == 1


def test_annotate_idempotent_keeps_existing():
    facts = {"facts": {"餐饮": [{"fact": "x", "source_tier": "T0", "source_url": "https://a/",
                                 "source_kind": "corpus", "captured_at": "old"}]}}
    new, stats = annotate_facts(facts, [], "new")   # 无 rows 也不会覆盖已有溯源
    assert new["facts"]["餐饮"][0]["captured_at"] == "old"
    assert stats["traced"] == 1
    assert stats["untraced"] == 0
