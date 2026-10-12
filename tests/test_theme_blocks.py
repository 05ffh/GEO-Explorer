"""P4 主题块渲染 + 注水校验测试（2026-09-22 build）。"""
from src.gt.theme_blocks import (
    check_fact_coverage,
    check_untraceable_numbers,
    render_theme_blocks,
)

F = {
    "facts": {
        "位置交通": [{"fact": "步行约3分钟到地铁南门兜站", "source_tier": "T0", "source_kind": "corpus",
                      "source_url": "https://www.shangri-la.com/", "captured_at": "2026-09-18"}],
        "康体设施": [{"fact": "理疗中心（德国巴登进口理疗产品 + 瑞典式按摩；按摩服务 10:00-23:00）", "source_tier": "T2",
                      "source_kind": "verified", "source_url": "", "captured_at": "2026-09-18"}],
        "餐饮": [{"fact": "韩香馆（韩国烧烤）（已停业，2026-09-18 核实）", "source_tier": "T1", "source_kind": "corpus",
                   "source_url": "", "captured_at": "2026-09-18"},
                 {"fact": "江南灶·融府（2楼，淮扬菜，2025、2026 连续两年米其林一星）", "source_tier": "T1",
                  "source_kind": "corpus", "source_url": "https://hk.trip.com/", "captured_at": "2026-09-18"}],
    }
}


def test_render_excludes_closed_and_groups():
    blocks, closed = render_theme_blocks(F, "福州香格里拉")
    all_text = "\n".join(f["text"] for b in blocks for f in b["facts"])
    assert "韩香馆" not in all_text            # 已停业排除
    assert "韩香馆" in closed[0]               # 进已停业清单
    loc = next(b for b in blocks if b["id"] == "location")
    assert "南门兜" in loc["facts"][0]["text"]  # 原文一字不改


def test_weak_verified_flagged():
    blocks, _ = render_theme_blocks(F)
    well = next(b for b in blocks if b["id"] == "wellness")
    assert well["facts"][0]["weak"] is True     # verified 无 URL = 弱证据


def test_untraceable_numbers_caught():
    facts = ["步行约3分钟到地铁南门兜站", "江南灶·融府 2026 米其林一星"]
    assert check_untraceable_numbers("机场班车每25分钟一班", facts) == ["25"]
    assert check_untraceable_numbers("步行约3分钟即达地铁站", facts) == []  # 3 可溯源


def test_fact_coverage_caught():
    facts = ["25米室内恒温泳池（附按摩池）", "距长乐机场约45分钟车程"]
    assert check_fact_coverage("酒店有25米恒温泳池", facts) == ["距长乐机场约45分钟车程"]
    assert check_fact_coverage("有25米室内恒温泳池和45分钟车程的机场", facts) == []
