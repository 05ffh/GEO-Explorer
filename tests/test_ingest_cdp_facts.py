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
