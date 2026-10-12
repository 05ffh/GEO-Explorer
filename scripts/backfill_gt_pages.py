"""补抓甲方资产页（spec 2026-09-16 方案 C）：联网查证证实甲方真有、但抓取 0 命中的资产
（网球场/理疗中心/商务中心/八匚汇配套）→ 抓权威页 → 存 search_results raw+content_text
→ build_grounding_corpus 自然补全。

用户 2026-09-16 驱动：GT 验证发现官网 services-facilities 页只列服务类、没列康体设施，
语料缺甲方核心资产 → 归因会误判真劣势。补抓权威第三方页（百科/携程/官网最新餐饮页）。

用法：python scripts/backfill_gt_pages.py <brand> <city>
"""
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.client_pages import fetch_pages
from src.collector.content_filter import filter_client_facts
from src.config import settings

# 补抓页：联网查证发现的语料缺口资产来源（tier 按来源性质，query 含城市供 build_grounding_corpus 消费）
PAGES = [
    {"url": "https://baike.baidu.com/item/福州香格里拉大酒店/6843496", "tier": "T2",
     "query": "福州 香格里拉酒店 设施 网球场 水疗 会议", "title": "福州香格里拉大酒店_百度百科"},
    {"url": "https://hotels.ctrip.com/hotels/429558.html", "tier": "T1",
     "query": "福州 香格里拉酒店 设施 餐饮 评价", "title": "福州香格里拉大酒店_携程"},
    {"url": "https://www.shangri-la.com/cn/restaurants-bars/fuzhou/shangrila/jiangnan-wok-rong/", "tier": "T0",
     "query": "福州 香格里拉 江南灶 融府 餐厅", "title": "江南灶·融府 中餐丨福州香格里拉"},
    {"url": "http://www.linkshop.com/news/2024514139.shtml", "tier": "T3",
     "query": "福州 香格里拉 八匚汇 商场 开业", "title": "香格里拉全新购物中心品牌八匚汇在福州首发"},
]


async def main():
    brand, city = sys.argv[1], sys.argv[2]
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        row = (await db.execute(text(
            "SELECT b.id, b.organization_id, "
            "(SELECT id FROM collection_runs WHERE brand_id=b.id AND city=:c ORDER BY created_at DESC LIMIT 1) "
            "FROM brands b WHERE b.name=:n"), {"n": brand, "c": city})).fetchone()
        if not row:
            print(f"错误: 品牌 {brand} 不存在"); await engine.dispose(); sys.exit(1)
        brand_id, org_id, run_id = row[0], row[1], row[2]

        urls = [p["url"] for p in PAGES]
        fetched = await fetch_pages(urls)
        n_ins = 0
        for p in PAGES:
            raw = (fetched.get(p["url"]) or "").strip()
            if not raw:
                print(f"  ⚠️ 抓取失败/空: {p['url']}")
                continue
            ct = filter_client_facts(raw)
            # 幂等：同 brand+url 已存在则更新，否则插入
            exists = (await db.execute(text(
                "SELECT id FROM search_results WHERE brand_id=:b AND url=:u"), {"b": brand_id, "u": p["url"]})).fetchone()
            if exists:
                await db.execute(text(
                    "UPDATE search_results SET raw_content=:r, content_text=:c, source_tier=:t WHERE id=:i"),
                    {"r": raw, "c": ct, "t": p["tier"], "i": exists[0]})
            else:
                await db.execute(text("""
                    INSERT INTO search_results
                    (id, brand_id, organization_id, collection_run_id, search_backend, query, title, url, snippet,
                     source_tier, content_text, raw_content, rank, collected_at)
                    VALUES (gen_random_uuid(), :b, :o, :run, 'tavily_extract', :q, :title, :u, '', :t, :c, :r, 0, now())
                """), {"b": brand_id, "o": org_id, "run": run_id, "q": p["query"],
                      "title": p["title"], "u": p["url"], "t": p["tier"], "c": ct, "r": raw})
            n_ins += 1
            print(f"  ✅ {p['tier']} {p['url'][:55]} raw {len(raw)}字 → 过滤 {len(ct)}字")
        await db.commit()
        # 复核：康体设施关键词是否已进 content_text
        full = "\n".join(r[0] for r in (await db.execute(text(
            "SELECT content_text FROM search_results WHERE brand_id=:b AND content_text<>''"), {"b": brand_id})).fetchall())
        for kw in ["网球", "理疗", "桑拿", "健身", "宴会厅", "八匚汇", "江南灶"]:
            print(f"  语料含「{kw}」: {'✅' if kw in full else '❌'}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
