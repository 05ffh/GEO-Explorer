"""GT 采集器骨架测试（异步采集链路：事实 + 舆情）。"""

import pytest

from src.collector.gt_collector_v2 import collect_raw, collect_sentiment, group_by_field, RawMaterial


async def _mock_search(query):
    """mock 异步搜索：每条 query 返回一条携程结果。"""
    return [{"url": "https://hotels.ctrip.com/hotels/429562.html",
             "title": "携程酒店", "snippet": "广州香格里拉 五星级"}]


@pytest.mark.asyncio
async def test_collects_all_field_queries():
    materials = await collect_raw("香格里拉", "广州", _mock_search)
    fields = {m.field for m in materials}
    assert "star_rating" in fields
    assert "adr" in fields
    assert "competitors" in fields


@pytest.mark.asyncio
async def test_tier_classified():
    materials = await collect_raw("香格里拉", "广州", _mock_search)
    assert all(m.tier == "T1" for m in materials)  # 携程 URL → T1


@pytest.mark.asyncio
async def test_materials_carry_field_and_query():
    materials = await collect_raw("香格里拉", "广州", _mock_search)
    star = [m for m in materials if m.field == "star_rating"]
    assert len(star) == 3  # star_rating 有 3 个 query
    assert any("几星" in m.query for m in star)


@pytest.mark.asyncio
async def test_collect_sentiment_scopes():
    materials = await collect_sentiment("香格里拉", "广州", _mock_search)
    grouped = group_by_field(materials)
    assert "store_level" in grouped
    assert "brand_level" in grouped
    assert len(grouped["store_level"]) == 8  # 门店级 8 条 query（2026-09-01 补负面词后）
    assert len(grouped["brand_level"]) == 7  # 品牌级 7 条 query（2026-09-01 补负面词后）


def test_group_by_field():
    m = RawMaterial(field="star_rating", query="q", url="https://x.com/1")
    grouped = group_by_field([m])
    assert "star_rating" in grouped
    assert grouped["star_rating"][0] is m


@pytest.mark.asyncio
async def test_published_at_flows_to_raw_material():
    """2026-09-18 时效：collect_raw 透传 search 返回的 published_at 到 RawMaterial（供落库时效标注）。"""

    async def _mock_with_date(query):
        return [{"url": "https://hotels.ctrip.com/hotels/429562.html",
                 "title": "携程酒店", "snippet": "广州香格里拉 五星级",
                 "published_at": "2026-08-15"}]

    materials = await collect_raw("香格里拉", "广州", _mock_with_date)
    assert materials and materials[0].published_at == "2026-08-15"

    # 无 published_at 时默认空串（不报错）
    async def _mock_no_date(query):
        return [{"url": "https://x.com/a", "title": "t", "snippet": "s"}]

    m2 = await collect_raw("香格里拉", "广州", _mock_no_date)
    assert m2[0].published_at == ""
