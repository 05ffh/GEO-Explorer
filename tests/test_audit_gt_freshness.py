"""GT 时效性审计脚本（2026-09-18 韩香馆教训）单测。"""
from datetime import date

from scripts.audit_gt_freshness import build_report, _days_since


def _gj(last_verified="2026-09-18"):
    return {
        "brand": "香格里拉", "city": "福州", "last_verified_at": last_verified,
        "volatile_categories": ["餐饮", "配套", "荣誉"],
        "facts": {
            "餐饮": [
                {"fact": "江南灶·融府（2025、2026米其林一星）", "source_tier": "T0"},
                {"fact": "韩香馆（韩国烧烤）（已停业）", "source_tier": "T1"},
            ],
            "配套": [{"fact": "八匚汇购物中心", "source_tier": "T0"}],
            "客房": [{"fact": "414间客房，2005年开业", "source_tier": "T0"}],   # 非易过时
        },
    }


def test_volatile_filtered_physical_skipped():
    """只列易过时类别；客房（物理属性）不进清单。"""
    text, n, _ = build_report(_gj(), 180, "run1", today=date(2026, 9, 18))
    assert "江南灶·融府" in text
    assert "八匚汇购物中心" in text
    assert "414间客房" not in text       # 非易过时类别跳过
    assert "韩香馆" not in text          # 已停业 → 跳过
    assert n == 2                        # 江南灶 + 八匚汇


def test_stale_detection():
    """last_verified_at 超阈值 → 超期；否则在时效内。"""
    _, _, stale_recent = build_report(_gj("2026-09-18"), 180, "r", today=date(2026, 9, 18))
    assert stale_recent is False
    _, _, stale_old = build_report(_gj("2025-01-01"), 180, "r", today=date(2026, 9, 18))
    assert stale_old is True
    _, _, stale_none = build_report(_gj(None), 180, "r", today=date(2026, 9, 18))
    assert stale_none is True            # 未记录 = 需复核


def test_per_fact_age_flag():
    """逐条时效：易变类别事实距 last_seen_at（或回退 captured_at）超阈 → 打 ⏳；未超阈不打。"""
    gj = {
        "brand": "香格里拉", "city": "福州", "last_verified_at": "2026-09-18",
        "volatile_categories": ["餐饮"],
        "facts": {"餐饮": [
            {"fact": "江南灶·融府", "source_tier": "T1", "last_seen_at": "2026-01-01"},  # 260 天前
            {"fact": "榕城厝里", "source_tier": "T1", "captured_at": "2026-09-01"},       # 17 天前（回退 captured_at）
        ]},
    }
    text, n, _ = build_report(gj, 180, "r", today=date(2026, 9, 18))
    assert n == 2
    js_line = [l for l in text.splitlines() if "江南灶·融府" in l][0]
    rl_line = [l for l in text.splitlines() if "榕城厝里" in l][0]
    assert "⏳" in js_line and "260" in js_line       # 超阈 → 逐条标 ⏳
    assert "⏳" not in rl_line                         # 未超阈


def test_days_since():
    assert _days_since("2026-09-18", date(2026, 9, 18)) == 0
    assert _days_since("2026-09-01", date(2026, 9, 18)) == 17
    assert _days_since(None) is None
    assert _days_since("bad-date") is None
