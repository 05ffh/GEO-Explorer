"""基线变更模式测试（spec 11.9）：问法指纹 → 同基线复用 / 问法变更新开 run + 复制 P2。"""
import pytest

from src.collector.gt_entry import (carry_forward_p2, create_collection_run, get_or_create_brand,
                                    write_measurement)
from src.collector.question_builder import fingerprint
from src.models.collection_run import CollectionRun
from src.models.organization import Organization
from scripts.run_measure import (_should_new_baseline, _latest_fingerprint, _clone_run_for_new_baseline,
                                 _resolve_measure_target, _build_measurement, _find_run)


def _questions(items):
    return [{"id": qid, "question": q} for qid, q in items]


def test_fingerprint_sorted_and_content_sensitive():
    q1 = _questions([("hit_business_generic", "福州出差住哪家酒店方便"),
                     ("hit_solo_generic", "福州一个人住哪家酒店性价比高")])
    q2 = _questions([("hit_solo_generic", "福州一个人住哪家酒店性价比高"),
                     ("hit_business_generic", "福州出差住哪家酒店方便")])
    assert fingerprint(q1) == fingerprint(q2)  # 顺序无关
    assert fingerprint(q1) == ["hit_business_generic::福州出差住哪家酒店方便",
                               "hit_solo_generic::福州一个人住哪家酒店性价比高"]
    q3 = _questions([("hit_business_generic", "福州出差住哪家酒店方便【改】"),
                     ("hit_solo_generic", "福州一个人住哪家酒店性价比高")])
    assert fingerprint(q1) != fingerprint(q3)  # 问法文本变 → 指纹变


def test_should_new_baseline():
    fp = ["hit_business_generic::福州出差住哪家酒店方便"]
    assert _should_new_baseline(None, fp) is False          # 旧数据无指纹 → 保守复用
    assert _should_new_baseline(list(fp), list(fp)) is False  # 同基线 → 复用
    assert _should_new_baseline(fp, ["hit_business_generic::改过的问法"]) is True  # 问法变更 → 新开


async def _mk_run(db, org, brand):
    run = await create_collection_run(db, org.id, brand.id, "福州", None)
    run.positioning_json = {"tier": "高端",
                            "competitors": ["福州世茂洲际酒店"],
                            "positioned_at": "2026-08-29T21:12:56"}
    run.sentiment_json = {"brand_level": {"rate": 0.14, "status": "confirmed"},
                          "store_level": {"rate": 0.15, "status": "confirmed"}}
    run.gt_facts_json = {"facts": {"客房": [{"fact": "414间客房"}]}}
    run.cdp_facts_json = {"facts": {"客房": [{"fact": "414间客房", "platforms": ["携程"]}]}}
    await db.flush()
    return run


@pytest.mark.asyncio
async def test_clone_run_copies_p2_independently(db_session):
    org = Organization(name="基线测试1")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    old = await _mk_run(db_session, org, brand)

    cloned = await _clone_run_for_new_baseline(db_session, old)
    assert cloned.id != old.id
    assert cloned.city == old.city
    assert cloned.positioning_json == old.positioning_json
    assert cloned.gt_facts_json == old.gt_facts_json        # 第一依据承接（2026-10-14 修）
    assert cloned.cdp_facts_json == old.cdp_facts_json
    assert cloned.sentiment_json == {}                      # 舆情**不承接**（测量结果，重采）

    # 深拷贝独立：改克隆的内存 dict 不影响旧 run（不同对象）
    assert cloned.positioning_json is not old.positioning_json
    assert cloned.gt_facts_json is not old.gt_facts_json
    cloned.positioning_json["tier"] = "豪华"
    assert old.positioning_json["tier"] == "高端"


@pytest.mark.asyncio
async def test_latest_fingerprint_prefers_newest_snapshot(db_session):
    org = Organization(name="基线测试2")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await _mk_run(db_session, org, brand)
    assert await _latest_fingerprint(db_session, str(run.id)) is None

    await write_measurement(db_session, run.id,
                            {"brand": "香格里拉", "city": "福州", "collected_at": "x",
                             "platforms": {}, "question_fingerprint": ["a::q1"]},
                            snapshot_type="full")
    assert await _latest_fingerprint(db_session, str(run.id)) == ["a::q1"]

    await write_measurement(db_session, run.id,
                            {"brand": "香格里拉", "city": "福州", "collected_at": "y",
                             "platforms": {}, "question_fingerprint": ["b::q2"]},
                            snapshot_type="remeasure")
    assert await _latest_fingerprint(db_session, str(run.id)) == ["b::q2"]


@pytest.mark.asyncio
async def test_baseline_decision_same_keeps_run_changed_clones(db_session):
    org = Organization(name="基线测试3")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await _mk_run(db_session, org, brand)
    fp_old = ["hit_business_generic::福州出差住哪家酒店方便"]
    await write_measurement(db_session, run.id,
                            {"brand": "香格里拉", "city": "福州", "collected_at": "x",
                             "platforms": {}, "question_fingerprint": fp_old},
                            snapshot_type="full")

    row = await db_session.get(CollectionRun, run.id)
    latest = await _latest_fingerprint(db_session, str(run.id))
    assert _should_new_baseline(latest, fp_old) is False  # 同指纹 → 复用

    current = ["hit_business_generic::福州出差住哪家酒店方便【改】"]
    assert _should_new_baseline(latest, current) is True  # 异指纹 → 新开
    new_run = await _clone_run_for_new_baseline(db_session, row)
    assert new_run.id != run.id
    assert new_run.positioning_json == row.positioning_json
    assert new_run.sentiment_json == {}                    # 舆情不承接（测量结果，重采）


@pytest.mark.asyncio
async def test_resolve_measure_target_multibaseline(db_session):
    """多基线并行：模拟消费者基线 A + 甲方词基线 B 都存在时，
    复测各自问法 → 复用各自基线（不误开新 run）；全新问法 → 才新开。"""
    org = Organization(name="基线测试4")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run_a = await _mk_run(db_session, org, brand)
    fp_a = ["hit_business_generic::福州出差住哪家酒店方便"]
    await write_measurement(db_session, run_a.id,
                            {"brand": "香格里拉", "city": "福州", "collected_at": "x",
                             "platforms": {}, "question_fingerprint": fp_a},
                            snapshot_type="full")

    # 甲方词基线 B：从 A 克隆（模拟基线变更流程）+ 甲方词测量
    row_a = await db_session.get(CollectionRun, run_a.id)
    run_b = await _clone_run_for_new_baseline(db_session, row_a)
    fp_b = ["client_kw::甲方指定词"]
    await write_measurement(db_session, run_b.id,
                            {"brand": "香格里拉", "city": "福州", "collected_at": "y",
                             "platforms": {}, "question_fingerprint": fp_b},
                            snapshot_type="full")

    # 复测模拟消费者问法 → 应选中 A（即使 _find_run 会先选最新的 B）
    target, is_new = await _resolve_measure_target(db_session, row_a, fp_a)
    assert target == str(run_a.id) and is_new is False
    # 复测甲方词问法 → 应选中 B
    target_b, is_new_b = await _resolve_measure_target(db_session, row_a, fp_b)
    assert target_b == str(run_b.id) and is_new_b is False
    # 全新问法 → 新开（不落到 A 或 B）
    target_c, is_new_c = await _resolve_measure_target(db_session, row_a, ["client_kw2::又一个新词"])
    assert is_new_c is True
    assert target_c != str(run_a.id) and target_c != str(run_b.id)
    # 新开的 run 承接甲方事实（定位/gt/cdp）；舆情不承接（测量结果，重采）
    new_run = await db_session.get(CollectionRun, target_c)
    assert new_run.positioning_json == row_a.positioning_json
    assert new_run.sentiment_json == {}
    assert new_run.gt_facts_json == row_a.gt_facts_json
    assert new_run.cdp_facts_json == row_a.cdp_facts_json


@pytest.mark.asyncio
async def test_carry_forward_p2_skip(db_session):
    """承接原语：默认全量承接甲方级 P2；skip 的字段不承接（重建 P2 时舆情重采）；深拷贝独立。"""
    org = Organization(name="承接测试")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    src = await _mk_run(db_session, org, brand)
    dst = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    carried = await carry_forward_p2(db_session, src, dst, skip=("sentiment_json",))
    assert set(carried) == {"positioning_json", "gt_facts_json", "cdp_facts_json"}
    assert dst.positioning_json == src.positioning_json
    assert dst.gt_facts_json == src.gt_facts_json
    assert dst.cdp_facts_json == src.cdp_facts_json
    assert dst.sentiment_json == {}                      # skip → 不承接（重采）
    assert dst.gt_facts_json is not src.gt_facts_json    # 深拷贝独立


def _j(qid):
    return {"question_id": qid, "question": f"题{qid}"}


def test_build_measurement_new_baseline_remeasure_uses_only_measured_platforms():
    """补测 + 基线变更：新基线第一版只用本次平台，不合并旧基线其他平台（防污染）。"""
    platform_results = {"deepseek": {"judgments": [_j("hit_business_generic")], "agent_notes": "a"}}
    existing = {"collected_at": "old", "platforms": {"deepseek": {"judgments": [_j("old")]},
                                                     "kimi": {"judgments": [_j("旧问法")]}}}
    m, st = _build_measurement("香格里拉", "福州", True, ["deepseek"], platform_results, existing)
    assert st == "full"
    assert list(m["platforms"].keys()) == ["deepseek"]  # 不合并 kimi 旧问法


def test_build_measurement_same_baseline_remeasure_merges():
    """同基线补测：只替换目标平台，其他平台保留。"""
    platform_results = {"deepseek": {"judgments": [_j("hit_business_generic")], "agent_notes": "a"}}
    existing = {"collected_at": "old",
                "platforms": {"deepseek": {"judgments": [_j("old")]}, "kimi": {"judgments": [_j("kimi题")]}}}
    m, st = _build_measurement("香格里拉", "福州", False, ["deepseek"], platform_results, existing)
    assert st == "remeasure"
    assert set(m["platforms"].keys()) == {"deepseek", "kimi"}  # 保留其他平台


@pytest.mark.asyncio
async def test_find_run_rejects_mismatched_run_id(db_session):
    """显式 run_id 也校验品牌/城市一致：跨单元传 run_id → 拒绝（P2 需重建，不误用别单元定位）。"""
    org = Organization(name="基线测试5")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await _mk_run(db_session, org, brand)  # 福州香格里拉

    # 品牌/城市任一不匹配 → None（拒绝，防止 P2 错配）
    assert await _find_run(db_session, "万豪", "广州", str(run.id)) is None
    assert await _find_run(db_session, "香格里拉", "广州", str(run.id)) is None
    # 完全匹配 → 返回 run
    assert (await _find_run(db_session, "香格里拉", "福州", str(run.id))).id == run.id


@pytest.mark.asyncio
async def test_carry_p2_on_rebuild(db_session):
    """重建 P2（run_gt_diagnosis）承接：同品牌+城市最近 run 的 gt/cdp/positioning 承接；
    sentiment 不承接（重采）；换城市（新诊断单元）不承接。"""
    from scripts.run_gt_diagnosis import _carry_p2_on_rebuild
    org = Organization(name="重建承接")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "重建承接品牌", org.id)
    prev = await _mk_run(db_session, org, brand)          # 有 gt/cdp/positioning/sentiment

    new = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    carried_pos = await _carry_p2_on_rebuild(db_session, brand.id, "福州", new)
    assert new.gt_facts_json == prev.gt_facts_json        # 第一依据承接
    assert new.cdp_facts_json == prev.cdp_facts_json
    assert new.sentiment_json == {}                       # 重采（不承接）
    assert carried_pos == prev.positioning_json           # 承接 positioning（供 tier 合并）

    # 换城市 = 新诊断单元 → 无前序 run → 不承接
    other = await create_collection_run(db_session, org.id, brand.id, "厦门", None)
    assert await _carry_p2_on_rebuild(db_session, brand.id, "厦门", other) == {}
    assert other.gt_facts_json == {}


def test_parse_args_refresh_sentiment_flag():
    """run_measure --refresh-sentiment 开关解析（刷舆情融入链路，spec ⑨）。"""
    from scripts.run_measure import _parse_args
    assert _parse_args(["香格里拉", "福州", "--refresh-sentiment"])[4] is True
    assert _parse_args(["香格里拉", "福州"])[4] is False
