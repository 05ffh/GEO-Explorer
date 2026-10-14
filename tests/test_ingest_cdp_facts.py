"""接线入口 tests：CDP 中间处理层产出校验 + 落库/合并三态（gt_facts_json 第一依据）。"""
import pytest

from scripts.ingest_cdp_facts import ingest, load_cdp_facts
from src.collector.gt_entry import (
    _CDP_MIDLAYER_SPEC,
    create_collection_run,
    generate_cdp_midlayer_input,
    get_or_create_brand,
)
from src.models.organization import Organization
from src.models.search_result import SearchResultRecord


def test_load_cdp_facts_validates():
    for bad in ("{}", '{"facts": {}}', '{"facts": {"客房": []}}',
                '{"facts": {"客房": [{"fact": "  "}]}}', '{"facts": {"客房": ["裸串"]}}',
                '{"facts": {"夸房": [{"fact": "414间客房"}]}}',   # 类名 typo → 拦（否则 P4 静默丢）
                '{"facts": {"客房": [{"fact": 414}]}}'):           # 非 str fact → 拦（否则 merge 崩）
        with pytest.raises(ValueError):
            load_cdp_facts(bad)
    ok = load_cdp_facts('{"facts": {"客房": [{"fact": "414间客房", "platforms": ["携程"]}]}}')
    assert ok["facts"]["客房"][0]["fact"] == "414间客房"


@pytest.mark.asyncio
async def test_ingest_writes_and_merges(db_session):
    org = Organization(name="接线")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"客房": [{"fact": "414间客房，楼高26层"}]}}

    facts = {
        "facts": {"客房": [
            {"fact": "414间客房，楼高26层"},   # 去重（既有覆盖）
            {"fact": "行政酒廊在21-24层"},       # 补充
            {"fact": "311间客房"},               # 冲突（间客房 数字不同）
        ]},
        "consistency": {"客房": "conflict"},
    }
    summary = await ingest(db_session, run.id, facts)

    # cdp_facts_json 独立落（含 consistency）
    assert run.cdp_facts_json["facts"]["客房"][0]["fact"].startswith("414")
    assert run.cdp_facts_json["consistency"] == {"客房": "conflict"}
    # 三态：去重1 / 补充1 / 冲突1
    assert len(summary["deduped"]) == 1
    assert len(summary["added"]) == 1
    assert len(summary["conflicts"]) == 1
    # 第一依据：既有 + 补充，冲突未并入 + 留痕
    gt = [f["fact"] for f in run.gt_facts_json["facts"]["客房"]]
    assert "414间客房，楼高26层" in gt and "行政酒廊在21-24层" in gt and "311间客房" not in gt
    assert run.cdp_facts_json["merge_conflicts"][0]["cdp"] == "311间客房"


@pytest.mark.asyncio
async def test_generate_cdp_midlayer_input(db_session):
    """generate 半：拉 run 的 CDP 行 → 各平台 content_text + 内嵌固化 spec（防漂移）。"""
    org = Organization(name="中间层")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    db_session.add(SearchResultRecord(
        organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
        search_backend="cdp", query="福州香格里拉",
        url="https://hotels.ctrip.com/hotels/429558.html",
        content_text="414间客房，楼高26层", source_tier="T1"))
    # 同平台第二页（多 --hotel-id）→ 不静默丢，逐页进待处理
    db_session.add(SearchResultRecord(
        organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
        search_backend="cdp", query="福州香格里拉",
        url="https://hotels.ctrip.com/hotels/999999.html",
        content_text="行政酒廊在21-24层", source_tier="T1"))
    await db_session.flush()

    out = await generate_cdp_midlayer_input(db_session, run.id)
    assert out["spec"] == _CDP_MIDLAYER_SPEC and out["spec"]  # 内嵌固化规范（非空）
    pages = out["platforms"]["携程"]
    assert [p["content_text"] for p in pages] == ["414间客房，楼高26层", "行政酒廊在21-24层"]
    assert pages[0]["url"].startswith("https://hotels.ctrip.com")

    # 无 CDP 行 → 空 platforms（供 CLI 报"先跑 fetch_ota_cdp"）
    empty = await create_collection_run(db_session, org.id, brand.id, "厦门", None)
    assert (await generate_cdp_midlayer_input(db_session, empty.id))["platforms"] == {}


def test_load_cdp_facts_stale_facts():
    """stale_facts（过时/停业项）可选；结构非法（非 dict/类名错/非 str fact）则拦。"""
    ok = load_cdp_facts('{"facts": {"餐饮": [{"fact": "江南灶·融府"}]}, '
                        '"stale_facts": {"餐饮": [{"fact": "夏宫中餐厅", "reason": "已改造为江南灶·融府"}]}}')
    assert ok["stale_facts"]["餐饮"][0]["fact"] == "夏宫中餐厅"
    for bad in ('{"facts": {"餐饮": [{"fact": "x"}]}, "stale_facts": []}',
                '{"facts": {"餐饮": [{"fact": "x"}]}, "stale_facts": {"夸房": [{"fact": "y"}]}}',
                '{"facts": {"餐饮": [{"fact": "x"}]}, "stale_facts": {"餐饮": [{"fact": 1}]}}'):
        with pytest.raises(ValueError):
            load_cdp_facts(bad)


@pytest.mark.asyncio
async def test_stale_facts_not_merged_into_gt(db_session):
    """过时项进 stale_facts：留档但不掺入 gt_facts_json（merge 只读 facts）——防污染第一依据。"""
    org = Organization(name="过时")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {}}
    facts = {"facts": {"餐饮": [{"fact": "江南灶·融府"}]},
             "stale_facts": {"餐饮": [{"fact": "夏宫中餐厅", "reason": "已改造为江南灶·融府"}]}}
    await ingest(db_session, run.id, facts)
    gt = [f["fact"] for f in run.gt_facts_json["facts"].get("餐饮", [])]
    assert "江南灶·融府" in gt
    assert "夏宫中餐厅" not in gt                                              # 过时项不掺入第一依据
    assert run.cdp_facts_json["stale_facts"]["餐饮"][0]["fact"] == "夏宫中餐厅"  # 但留档供 P4


@pytest.mark.asyncio
async def test_dedup_refreshes_last_seen_at(db_session):
    """去重命中时刷新「最近观测」锚点（重抓重合并=复核）——否则时效审计误报过时。"""
    org = Organization(name="复核")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"客房": [{"fact": "414间客房，楼高26层"}]}}
    db_session.add(SearchResultRecord(
        organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
        search_backend="cdp", query="福州香格里拉",
        url="https://hotels.ctrip.com/hotels/429558.html",
        content_text="414间客房，楼高26层", source_tier="T1"))
    await db_session.flush()

    summary = await ingest(db_session, run.id, {
        "facts": {"客房": [{"fact": "414间客房，楼高26层", "platforms": ["携程"]}]}})
    assert len(summary["deduped"]) == 1
    entry = run.gt_facts_json["facts"]["客房"][0]
    assert entry.get("last_seen_at")            # 观测=复核：刷新最近观测锚点
    assert "captured_at" not in entry           # 既有基线事实的首次捕获锚点不被覆盖


@pytest.mark.asyncio
async def test_generate_includes_stale_reference(db_session):
    """generate 注入 GT 已确认过时项（停业/改造）→ 供主 agent 判 CDP 页面过时描述（如夏宫）。"""
    org = Organization(name="参照")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"餐饮": [
        {"fact": "江南灶·融府— 由原「夏宫」中餐厅改造"},   # 「改造」无「已」前缀 → 仍应入参照
        {"fact": "韩香馆（韩国烧烤）（已停业）"},
        {"fact": "大堂酒廊·榕城厝里"},                      # 在营 → 不入参照
    ]}}
    db_session.add(SearchResultRecord(
        organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
        search_backend="cdp", query="福州香格里拉",
        url="https://hotel.alitrip.com/hotel_detail2.htm?shid=10015487",
        content_text="酒店介绍…夏宫…", source_tier="T1"))
    await db_session.flush()

    ref = (await generate_cdp_midlayer_input(db_session, run.id))["stale_reference"]
    assert any("夏宫" in r for r in ref)
    assert any("韩香馆" in r for r in ref)
    assert not any("榕城厝里" in r for r in ref)
