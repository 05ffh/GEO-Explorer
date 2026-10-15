"""诊断入口确定性工具测试（查/建品牌、建 collection_run、写定位）。"""

import pytest

from src.models.organization import Organization
from src.collector.gt_entry import (
    get_or_create_brand, create_collection_run, write_positioning, write_search_result,
    append_competitors, write_measurement, write_cdp_facts, merge_cdp_facts_into_gt,
    append_report_artifact,
)


@pytest.mark.asyncio
async def test_gt_entry_flow(db_session):
    org = Organization(name="测试机构")
    db_session.add(org)
    await db_session.flush()

    # 查/建品牌：首次创建
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    assert brand.name == "香格里拉"

    # 复用：同名不新建
    brand2 = await get_or_create_brand(db_session, "香格里拉", org.id)
    assert brand2.id == brand.id

    # 建 collection_run（诊断单元 = 品牌 + 地区）
    run = await create_collection_run(db_session, org.id, brand.id, "广州", "天河区")
    assert run.city == "广州"
    assert run.region == "天河区"
    assert run.positioning_json == {}

    # 写定位结果
    positioning = {
        "tier": "高端",
        "tier_reason": "品牌梯队高端 + ADR 850 + 五星",
        "personas": {"商务差旅": 3, "亲子家庭": 1},
        "competitors": ["广州四季", "广州文华东方"],
    }
    await write_positioning(db_session, run.id, positioning)
    assert run.positioning_json["tier"] == "高端"
    assert run.positioning_json["competitors"] == ["广州四季", "广州文华东方"]
    assert "positioned_at" in run.positioning_json  # 定位时间戳（P3 新鲜度校验用）

    # 写原始材料到 search_results（关联 collection_run，带 tier）
    rec = await write_search_result(
        db_session, org.id, brand.id, run.id,
        search_backend="websearch",
        query="香格里拉酒店 广州 几星",
        url="https://hotels.ctrip.com/hotels/429562.html",
        title="携程-广州香格里拉",
        snippet="五星级",
        tier="T1",
    )
    assert rec.collection_run_id == run.id  # 环环相扣：原始材料关联采集运行
    assert rec.brand_id == brand.id
    assert rec.source_tier == "T1"


@pytest.mark.asyncio
async def test_append_competitors_preserves_tier(db_session):
    """主 agent 补竞品时，已有 tier 不能丢（gap 闭合的健壮性验证）。"""
    org = Organization(name="测试机构2")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)

    # run_gt_diagnosis ④½ 已写 tier
    await write_positioning(db_session, run.id, {"tier": "高端", "competitors": []})
    # 主 agent 确认竞品后补写
    await append_competitors(db_session, run.id, ["福州希尔顿"])

    assert run.positioning_json["tier"] == "高端"
    assert run.positioning_json["competitors"] == ["福州希尔顿"]
    assert "positioned_at" in run.positioning_json


@pytest.mark.asyncio
async def test_write_measurement(db_session):
    """P3 命中率结果落库到 measurement_json。"""
    org = Organization(name="测试机构3")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    assert run.measurement_json == {}

    measurement = {
        "platforms": {
            "deepseek": {"judgments": [{"hit": True, "rank": 1}], "platform_rate": {"hit_rate": 1.0}},
        },
        "overall": {"overall_hit_rate": 1.0, "platform_hit_rates": {"deepseek": 1.0}},
    }
    await write_measurement(db_session, run.id, measurement)
    assert run.measurement_json == measurement


@pytest.mark.asyncio
async def test_write_cdp_facts(db_session):
    """CDP 中间处理层产出（主 agent 判断）落 cdp_facts_json（独立存，核验后并入 gt_facts_json）。"""
    org = Organization(name="CDP事实")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    assert run.cdp_facts_json == {}

    facts = {
        "facts": {"位置交通": [{"fact": "步行约3分钟到地铁南门兜站",
                              "source_url": "https://hotels.ctrip.com/hotels/429558.html",
                              "source_kind": "corpus", "source_tier": "T1", "platforms": ["携程"]}]},
        "consistency": {"地址": "agree"},
    }
    await write_cdp_facts(db_session, run.id, facts)
    assert run.cdp_facts_json["facts"]["位置交通"][0]["fact"].startswith("步行约3分钟")
    assert run.cdp_facts_json["facts"]["位置交通"][0]["platforms"] == ["携程"]
    assert run.cdp_facts_json["consistency"]["地址"] == "agree"


@pytest.mark.asyncio
async def test_write_positioning_preserves_fields_on_partial_update(db_session):
    """finalize_tier/personas 场景：读 positioning → 只改目标字段 → 写回，保留其余（环环相扣）。"""
    org = Organization(name="部分更新")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    await db_session.flush()

    await write_positioning(db_session, run.id, {
        "tier": "高端", "personas": {"商务差旅": 3}, "competitors": ["福州希尔顿"],
    })
    first_pos = run.positioning_json["positioned_at"]
    # finalize_tier 场景：读 positioning，只改 tier，写回
    positioning = dict(run.positioning_json)
    positioning["tier"] = "豪华"
    await write_positioning(db_session, run.id, positioning)
    assert run.positioning_json["tier"] == "豪华"
    assert run.positioning_json["personas"] == {"商务差旅": 3}
    assert run.positioning_json["competitors"] == ["福州希尔顿"]
    # 精修保留原 positioned_at（不掩盖过时定位，P3 新鲜度校验不被绕过）
    assert run.positioning_json["positioned_at"] == first_pos
    # finalize_personas 场景：只改 personas
    positioning2 = dict(run.positioning_json)
    positioning2["personas"] = {"商务差旅": 2, "亲子家庭": 1}
    await write_positioning(db_session, run.id, positioning2)
    assert run.positioning_json["personas"] == {"商务差旅": 2, "亲子家庭": 1}
    assert run.positioning_json["tier"] == "豪华"
    assert run.positioning_json["competitors"] == ["福州希尔顿"]


@pytest.mark.asyncio
async def test_sentiment_materials_write_search_results(db_session):
    """舆情采集材料（含 URL）写 search_results，供主 agent 负面终判追溯（spec 4.5）。"""
    from sqlalchemy import select
    from src.collector.gt_collector_v2 import collect_sentiment
    from src.models.search_result import SearchResultRecord

    org = Organization(name="舆情写库")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    await db_session.flush()

    async def fake_search(query):
        return [{"url": f"https://example.com/{abs(hash(query)) % 100000}",
                 "title": f"t-{query[:12]}", "snippet": "服务态度差 投诉 卫生问题", "provider": "mock"}]

    senti = await collect_sentiment("香格里拉", "福州", fake_search)
    assert senti, "舆情搜索词应采到材料（含负面倾向词）"

    for m in senti:
        await write_search_result(db_session, org.id, brand.id, run.id,
                                  m.provider, m.query, m.url, m.title, m.snippet, m.tier)
    await db_session.flush()

    rows = (await db_session.execute(
        select(SearchResultRecord).where(SearchResultRecord.collection_run_id == run.id)
    )).scalars().all()
    assert len(rows) == len(senti)
    assert all(r.url.startswith("https://example.com/") for r in rows)  # 负面材料带 URL 落库


@pytest.mark.asyncio
async def test_merge_cdp_facts_three_state(db_session):
    """合并三态：去重（互相包含跳过）/ 补充（新事实追加）/ 冲突（数字不同、默认不并入）。"""
    org = Organization(name="合并三态")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"客房": [
        {"fact": "414间客房及套房，楼高26层，2005年开业"}]}}
    await write_cdp_facts(db_session, run.id, {"facts": {"客房": [
        {"fact": "414间客房及套房，楼高26层，2005年开业"},   # 去重（完全重复）
        {"fact": "房型含豪华客房/豪华阁/天际房/行政套房"},      # 补充（新事实）
        {"fact": "311间客房，楼高30层"},                      # 冲突（间/层 单位共享、数字不同）
    ]}})

    summary = await merge_cdp_facts_into_gt(db_session, run.id)

    facts = run.gt_facts_json["facts"]["客房"]
    assert len(facts) == 2  # 1 既有 + 1 补充（去重跳过、冲突不并入）
    assert any("豪华阁" in f["fact"] for f in facts)
    assert len(summary["deduped"]) == 1
    assert len(summary["added"]) == 1
    assert len(summary["conflicts"]) == 1
    # 冲突留痕待核验（第一依据不静默改）
    assert run.cdp_facts_json["merge_conflicts"][0]["cdp"] == "311间客房，楼高30层"


@pytest.mark.asyncio
async def test_merge_cdp_facts_apply_conflicts(db_session):
    """apply_conflicts=True：冲突也并入，但仍在 summary 留痕（可审计）。"""
    org = Organization(name="合并强制")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"客房": [{"fact": "414间客房，楼高26层"}]}}
    await write_cdp_facts(db_session, run.id, {"facts": {"客房": [{"fact": "311间客房，楼高30层"}]}})

    summary = await merge_cdp_facts_into_gt(db_session, run.id, apply_conflicts=True)

    assert len(run.gt_facts_json["facts"]["客房"]) == 2
    assert len(summary["added"]) == 1
    assert len(summary["conflicts"]) == 1  # 已并入但仍留痕


@pytest.mark.asyncio
async def test_merge_cdp_facts_no_false_conflict_or_loss(db_session):
    """对抗审查修复回归：① 更丰富的 CDP 事实不被去重丢弃；② 不同属性共享单位不误报冲突。"""
    org = Organization(name="合并边界")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"客房": [{"fact": "414间客房"}, {"fact": "楼高26层"}]}}
    await write_cdp_facts(db_session, run.id, {"facts": {"客房": [
        {"fact": "414间客房及套房，楼高26层，2005年开业"},  # 更丰富（既有 ⊂ CDP）→ 补充，不丢信息
        {"fact": "7间多功能厅"},                          # 共享"间"但属性不同（间客房≠间多功能厅）→ 补充
        {"fact": "豪华双床房6-20层"},                      # 共享"层"但属性不同（楼高层≠层）→ 补充
    ]}})

    summary = await merge_cdp_facts_into_gt(db_session, run.id)

    facts = [f["fact"] for f in run.gt_facts_json["facts"]["客房"]]
    assert len(facts) == 5  # 2 既有 + 3 补充
    assert "414间客房及套房，楼高26层，2005年开业" in facts  # 信息未丢
    assert summary["deduped"] == [] and summary["conflicts"] == []
    assert len(summary["added"]) == 3


@pytest.mark.asyncio
async def test_merge_cdp_facts_conflict_with_leading_context(db_session):
    """H1 回归（对抗审查 2026-10-12）：GT 事实数字前有领字（「酒店共有414间客房」）时，
    仍须与「311间客房」判为冲突——旧 _kv 键含前文（「共有间客房」≠「间客房」）致同属性漏报。"""
    org = Organization(name="领字冲突")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {"客房": [{"fact": "酒店共有414间客房"}]}}
    await write_cdp_facts(db_session, run.id, {"facts": {"客房": [{"fact": "311间客房"}]}})

    summary = await merge_cdp_facts_into_gt(db_session, run.id)

    assert len(summary["conflicts"]) == 1        # 领字不掩盖同属性冲突
    assert len(run.gt_facts_json["facts"]["客房"]) == 1  # 默认不并入，第一依据未被污染


@pytest.mark.asyncio
async def test_merge_no_false_conflict_on_distinct_similar_facts(db_session):
    """真数据回归（2026-10-12）：模板同构但主语不同的**不同事实**（大床房/双床房）不得判冲突；
    同骨架仅数字不同（步行3分钟/步行5分钟）须判冲突——冲突 = 同属性数字不同，②兜底用骨架全等非 Jaccard。"""
    org = Organization(name="同构异主语")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    run.gt_facts_json = {"facts": {
        "客房": [{"fact": "豪华大床房-尽览榕城繁华城景（1张2米特大床｜40平方米|6-20层）"}],
        "位置交通": [{"fact": "步行3分钟到地铁南门兜站"}]}}
    await write_cdp_facts(db_session, run.id, {"facts": {
        "客房": [{"fact": "豪华双床房-尽览榕城繁华城景（2张1.2米单人床｜40平方米|6-20层）"}],
        "位置交通": [{"fact": "步行5分钟到地铁南门兜站"}]}})

    summary = await merge_cdp_facts_into_gt(db_session, run.id)

    assert len(summary["added"]) == 1 and summary["added"][0]["fact"].startswith("豪华双床房")  # 同构异主语 → 补充
    assert len(summary["conflicts"]) == 1                                                        # 同骨架异数字 → 冲突
    assert summary["conflicts"][0]["cdp"] == "步行5分钟到地铁南门兜站"


@pytest.mark.asyncio
async def test_merge_cdp_facts_injects_provenance(db_session):
    """M2 回归（对抗审查 2026-10-12）：并入第一依据的 CDP 事实**由系统补溯源**
    （source_url/tier/captured_at=captured，§545 可信=可追溯）；cdp_facts_json 保原始产出。"""
    from datetime import datetime, timezone
    from src.models.search_result import SearchResultRecord

    org = Organization(name="溯源注入")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    db_session.add(SearchResultRecord(
        organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
        search_backend="cdp", url="https://hotels.ctrip.com/hotels/429558.html",
        source_tier="T1", collected_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
        content_text="414间客房"))
    await write_cdp_facts(db_session, run.id, {"facts": {"客房": [
        {"fact": "414间客房", "platforms": ["携程"]}]}})
    await db_session.flush()

    await merge_cdp_facts_into_gt(db_session, run.id)

    merged = run.gt_facts_json["facts"]["客房"][0]
    assert merged["source_url"] == "https://hotels.ctrip.com/hotels/429558.html"
    assert merged["source_tier"] == "T1" and merged["source_kind"] == "corpus"
    assert merged["captured_at"] == "2026-10-12"
    # cdp_facts_json 保原始（未原地注入）
    assert "source_url" not in run.cdp_facts_json["facts"]["客房"][0]


@pytest.mark.asyncio
async def test_append_report_artifact_accumulates(db_session):
    """报告写侧接入：append 溯源记录（出生快照号/产物 sha256），历史累积不覆盖。"""
    org = Organization(name="报告溯源测试")
    db_session.add(org)
    await db_session.flush()
    brand = await get_or_create_brand(db_session, "香格里拉", org.id)
    run = await create_collection_run(db_session, org.id, brand.id, "福州", None)
    assert run.report_json == {}
    await append_report_artifact(db_session, run.id, {"snapshot_no": 4, "html_sha256": "a"})
    await append_report_artifact(db_session, run.id, {"snapshot_no": 4, "html_sha256": "b"})
    assert [x["html_sha256"] for x in run.report_json["artifacts"]] == ["a", "b"]
    assert [x["snapshot_no"] for x in run.report_json["artifacts"]] == [4, 4]
