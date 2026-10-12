"""甲方页面 URL 认领守卫测试（F2 修复：空 city_en/brand_en 的 `"" in url` 恒真 bug）。"""

import pytest
from sqlalchemy import select

from src.collector.client_pages import (
    _clean, _no_page_reason, assemble_corpus, build_grounding_corpus, is_client_page_url,
    refilter_client_pages,
)


def test_matches_brand_and_city_in_url():
    assert is_client_page_url("https://www.shangri-la.com/fuzhou/", "香格里拉", "福州", "fuzhou", "shangri-la")
    assert is_client_page_url("https://hotels.ctrip.com/福州香格里拉大酒店", "香格里拉", "福州", "fuzhou")


def test_empty_city_en_does_not_claim_other_city():
    # 泉州不在拼音表 → city_en=""；旧码 `"" in url` 恒真 → 会把福州页面误认成泉州（跨城污染）
    assert not is_client_page_url(
        "https://www.shangri-la.com/fuzhou/", "香格里拉", "泉州", "", "shangri-la")


def test_empty_brand_en_does_not_claim_english_url():
    # 本地品牌无英文名 + 英文 URL → 无法认领（不能靠 brand 中文出现在英文 URL 里）
    assert not is_client_page_url(
        "https://www.example.com/fuzhou-hotel", "聚春园", "福州", "fuzhou", "")


def test_local_brand_chinese_url_ok():
    # 本地品牌走中文 URL 认领（城市在拼音表，品牌是中文）
    assert is_client_page_url(
        "https://www.dianping.com/福州聚春园酒店", "聚春园", "福州", "fuzhou")


def test_no_page_reason_hints():
    r = _no_page_reason([("u",)], "聚春园", "泉州", "", "")
    assert "brand_domains" in r and "city_pinyin" in r
    assert _no_page_reason([], "x", "福州", "fuzhou", "x").startswith("search_results")


def test_assemble_corpus_fills_budget_across_tiers():
    # 2026-09-15 修：旧版整页装不下就 break → T0 装完丢掉全部 OTA（93% 文本+白留预算）
    t0 = "\n".join(f"官网第{i}条：位于福州市中心，毗邻三坊七巷" for i in range(5))
    t1 = "整洁度8.8分，客房舒适度8.8分，设施服务8.4分"
    pages = [("T0", "https://www.shangri-la.com/cn/fuzhou/shangrila", t0),
             ("T1", "https://www.booking.com/hotel/cn/shangri-la-fuzhou.html", t1)]
    out = assemble_corpus(pages, budget_chars=250)
    assert len(out) <= 250
    assert "[T0 官网/官方]" in out
    assert "[T1 OTA平台]" in out      # 剩余预算继续填 OTA
    assert "8.8" in out


def test_assemble_corpus_labels_ugc_paths():
    pages = [("T1", "https://hk.trip.com/moments/theme/poi-shangri-la-fuzhou-1/",
              "游记：在福州香格里拉住得很开心，孩子很喜欢泳池")]
    out = assemble_corpus(pages, budget_chars=500)
    assert "游记/第三方" in out


def test_assemble_corpus_dedups_lines():
    dup = "福州香格里拉位于市中心"
    out = assemble_corpus([("T0", "u1", f"{dup}\n{dup}\n{dup}")], budget_chars=500)
    assert out.count(dup) == 1


def test_assemble_corpus_no_official_site_carries_share():
    # 本地品牌无官网（无 T0）：T0 份额必须顺延给 T1，否则只用 25% 预算（2026-09-15 对抗审查）
    t1 = "\n".join(f"OTA事实第{i}条：位于市中心，含早餐，住客评分9.0" for i in range(30))
    out = assemble_corpus([("T1", "https://www.booking.com/hotel/cn/xx.html", t1)], budget_chars=600)
    assert len(out) <= 600
    assert len(out) >= int(600 * 0.85)      # T0(60%)+T1(25%) 份额顺延 → 用到约 85%+
    assert out.count("OTA事实第") >= 15      # 仅 25% 份额只够 ~5 行；顺延后 ~19 行


def test_assemble_corpus_budget_is_hard_cap():
    long_lines = "\n".join("福州香格里拉位于鼓楼区毗邻三坊七巷交通便利" for _ in range(50))
    out = assemble_corpus([("T0", "u", long_lines)], budget_chars=300)
    assert len(out) <= 300


async def _brand_run(db, name="香格里拉", city="福州"):
    from src.collector.gt_entry import create_collection_run, get_or_create_brand
    from src.models.organization import Organization
    org = Organization(name=f"机构-{name}")
    db.add(org)
    await db.flush()
    brand = await get_or_create_brand(db, name, org.id)
    run = await create_collection_run(db, org.id, brand.id, city)
    return org, brand, run


def _page(org, brand, run, url, content_text, layer, raw=""):
    from src.models.search_result import SearchResultRecord
    return SearchResultRecord(
        organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
        search_backend="tavily", query="福州香格里拉", url=url,
        content_text=content_text, raw_content=raw or None, content_layer=layer, source_tier="T3")


@pytest.mark.asyncio
async def test_grounding_corpus_reads_only_fact_layer(db_session):
    """下游唯一入口只读 fact 层——opinion 行长着 content_text 也不得进归因语料。

    触发场景（2026-09-17 对抗审查，HIGH）：refilter_client_pages 旧版重过滤全部行，
    把 UGC 页正文灌回 content_text，第三方观点重新漏进语料。
    """
    org, brand, run = await _brand_run(db_session)
    db_session.add_all([
        _page(org, brand, run, "https://www.shangri-la.com/fuzhou/",
              "福州香格里拉位于鼓楼区，毗邻三坊七巷", "fact"),
        _page(org, brand, run, "https://hk.trip.com/moments/x/",
              "游记：住得还行但不如隔壁竞对", "opinion"),
    ])
    await db_session.flush()
    corpus = await build_grounding_corpus(db_session, brand.id, "福州")
    assert "毗邻三坊七巷" in corpus
    assert "不如隔壁竞对" not in corpus


@pytest.mark.asyncio
async def test_refilter_relayers_and_clears_opinion(db_session):
    """refilter 按 URL 重新分层：/review/ 页（旧版分层器漏判）content_text 置空。"""
    from src.models.search_result import SearchResultRecord
    org, brand, run = await _brand_run(db_session)
    db_session.add(_page(org, brand, run, "https://hotels.ctrip.com/review/123.html",
                         "旧值", "fact", raw="游记：住得还行，泳池不错，早餐丰富，位置方便"))
    await db_session.flush()
    await refilter_client_pages(db_session, brand.id)
    await db_session.flush()
    rec = (await db_session.execute(select(SearchResultRecord))).scalars().one()
    assert rec.content_layer == "opinion"
    assert rec.content_text == ""


def test_clean_converts_traditional_to_simplified():
    # 2026-09-18 繁→简链路改造：_clean（raw_content 源头层）也转简体，简体输入幂等
    raw = "位於福州市鼓樓區新權南路9號，毗鄰五一廣場。\n\n\n行政樓層  接站服務"
    out = _clean(raw)
    assert "位于福州市鼓楼区新权南路9号，毗邻五一广场" in out
    assert "行政楼层" in out
    assert "接站服务" in out
    assert "樓" not in out and "區" not in out and "廣" not in out
    assert _clean("简体输入保持不变") == "简体输入保持不变"


def test_assemble_corpus_stale_url_deprioritized():
    """2026-09-18 时效：营销活动页/年份 URL（offer/campaign/20XX）同 tier 内排最后——
    预算不够时旧活动页先被丢（其内容多为过期营销，非甲方长期资产）。"""
    from src.collector.client_pages import _STALE_URL, assemble_corpus
    assert _STALE_URL.search("https://www.shangri-la.com/cn/campaign-rooms-2025laborday/")
    assert _STALE_URL.search("https://www.shangri-la.com/cn/fuzhou/shangrila/offer-detail/family-room/")
    assert _STALE_URL.search("https://www.fuzhou.gov.cn/.../201912/t20...")
    assert not _STALE_URL.search("https://www.shangri-la.com/cn/fuzhou/shangrila/")
    assert not _STALE_URL.search("https://www.booking.com/hotel/cn/shangri-la-fuzhou.html")
    # 同 tier 内 stale 活动页排**最后**：语料中 normal 资料内容出现在 stale 营销内容之前
    normal = "\n".join("福州香格里拉大酒店位于鼓楼区毗邻五一广场和地铁南门兜站" for _ in range(3))
    stale = "\n".join("2025劳动节优惠：连住2晚8折含双早快闪特惠" for _ in range(3))
    out = assemble_corpus(
        [("T0", "https://www.shangri-la.com/cn/fuzhou/shangrila/", normal),
         ("T0", "https://www.shangri-la.com/cn/campaign-rooms-2025laborday/", stale)],
        budget_chars=800)
    assert out.index("五一广场") < out.index("2025劳动节"), "stale 活动页应排在资料页之后"


def test_published_at_flows_through_search_all():
    """2026-09-18 时效：search_all_backends 透传 published_at（从后端 SearchResult）。"""
    import asyncio
    from src.search import SearchBackend, SearchResult
    from src.search.search_all import search_all_backends

    class _Mock(SearchBackend):
        name = "mock"

        async def search(self, query, num=5):
            return [SearchResult(title="t", snippet="s", url="https://x.com/a",
                                 published_at="2026-09-01")]

    out = asyncio.run(search_all_backends("q", backends=[_Mock()], limiters={}))
    assert out and out[0]["published_at"] == "2026-09-01"
