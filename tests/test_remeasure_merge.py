"""补测合并测试：--platforms 子集重测只更新目标平台，其他平台（含主 agent 回填）不混淆。

platform_rate / agent_tasks / status 由 finalize_measurement 从 judgments 单一来源重建，
补测只替换目标平台 judgments。
"""
from src.collector.hit_rate import finalize_measurement
from scripts.run_measure import _remeasure_merge


def _judgment(qid, hit=None, rank=None, needs_agent=False):
    return {"question_id": qid, "question": f"题{qid}", "answer": "",
            "hit": hit, "rank": rank, "brand_count": None, "needs_agent": needs_agent}


def _platform(judgments):
    return {"judgments": judgments, "agent_notes": "地区语境复核"}


def test_remeasure_keeps_other_platforms_and_agent_fill():
    # 旧 measurement：deepseek 主 agent 已判（complete），doubao 有 error 题未判
    existing = {
        "status": "complete", "collected_at": "2026-08-29T10:00:00",
        "platforms": {
            "deepseek": {"judgments": [_judgment("hit_business_generic", True, 1)]},
            "doubao": {"judgments": [_judgment("hit_business_generic", None, None)]},
        },
        "agent_tasks": [], "agent_notes": [],
    }
    new_doubao = _platform([_judgment("hit_business_generic", False, None)])

    m = _remeasure_merge(existing, {"doubao": new_doubao}, ["doubao"])
    remaining = finalize_measurement(m)

    # 其他平台原样保留（主 agent 回填的 hit/rank 不丢）
    ds = m["platforms"]["deepseek"]["judgments"][0]
    assert ds["hit"] is True and ds["rank"] == 1
    # 目标平台被替换
    assert m["platforms"]["doubao"]["judgments"][0]["hit"] is False
    # 无 needs_agent → complete
    assert remaining == 0
    assert m["status"] == "complete"
    assert m["agent_tasks"] == []


def test_remeasure_new_needs_agent_returns_partial_and_tasks():
    existing = {
        "status": "complete", "collected_at": "2026-08-29T10:00:00",
        "platforms": {
            "deepseek": {"judgments": [_judgment("hit_business_generic", True, 1)]},
            "doubao": {"judgments": [_judgment("hit_business_generic", None, None)]},
        },
        "agent_tasks": [], "agent_notes": [],
    }
    # 补测后豆包新回答是自然段式 → needs_agent
    new_doubao = _platform([_judgment("hit_business_generic", None, None, needs_agent=True)])

    m = _remeasure_merge(existing, {"doubao": new_doubao}, ["doubao"])
    remaining = finalize_measurement(m)

    assert remaining == 1
    assert m["status"] == "partial"
    assert [t["question_id"] for t in m["agent_tasks"]] == ["hit_business_generic"]


def test_remeasure_clears_stale_agent_task():
    # 旧 measurements：deepseek 一题待判（agent_tasks 有它），补测只碰 doubao，
    # 该 deepseek 题在保留的 judgments 里已判 → agent_tasks 重建后不再出现
    existing = {
        "status": "partial", "collected_at": "2026-08-29T10:00:00",
        "platforms": {
            "deepseek": {"judgments": [_judgment("hit_solo_price", False, None)]},
            "doubao": {"judgments": [_judgment("hit_business_generic", None, None)]},
        },
        "agent_tasks": [{"question_id": "hit_solo_price", "question": "题", "task": "旧残留"}],
        "agent_notes": [],
    }
    new_doubao = _platform([_judgment("hit_business_generic", None, None, needs_agent=True)])

    m = _remeasure_merge(existing, {"doubao": new_doubao}, ["doubao"])
    remaining = finalize_measurement(m)

    # deepseek 题已判（保留 judgments 里 needs_agent=False）→ 不进 agent_tasks
    assert [t["question_id"] for t in m["agent_tasks"]] == ["hit_business_generic"]
    assert remaining == 1
    assert m["status"] == "partial"


def test_remeasure_rebuilds_tasks_from_all_platforms():
    # 重建后 agent_tasks 覆盖所有平台当前 needs_agent（deepseek 保留待判 + doubao 新待判）
    existing = {
        "status": "partial", "collected_at": "2026-08-29T10:00:00",
        "platforms": {
            "deepseek": {"judgments": [_judgment("hit_solo_price", None, None, needs_agent=True)]},
            "doubao": {"judgments": [_judgment("hit_business_generic", None, None)]},
        },
        "agent_tasks": [], "agent_notes": [],
    }
    new_doubao = _platform([_judgment("hit_business_generic", None, None, needs_agent=True)])

    m = _remeasure_merge(existing, {"doubao": new_doubao}, ["doubao"])
    finalize_measurement(m)

    ids = [t["question_id"] for t in m["agent_tasks"]]
    assert ids == ["hit_solo_price", "hit_business_generic"]
    assert len(ids) == len(set(ids))
