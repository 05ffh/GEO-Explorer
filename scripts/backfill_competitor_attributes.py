"""竞对排序字段回填（P1-② 前置，2026-09-10）：让 select_primary 真正按设计意图选主竞对。

现状：positioning.competitors 只有 name+band，缺 ring/tier/ai_cooccurrence →
select_primary 排序函数失效（返回 None）→ measure 退回"列表第一个"，脆弱。
本脚本从 sealed 测量数据算每个竞对的 AI 同场景共现（与甲方同题被推荐次数）+
补 ring（main→核心/secondary→近邻）+ tier（查 brand_domains）→ 写回 positioning_json，
select_primary 就能选"共现最高 = 甲方被挤压最狠"的主竞对。

用法：
  python scripts/backfill_competitor_attributes.py <run_id>          # 预览（不算写）
  python scripts/backfill_competitor_attributes.py <run_id> --apply  # 写回 positioning_json
"""
import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.competitor import COMPETITOR_BAND_MAIN, COMPETITOR_BAND_SECONDARY
from src.collector.competitor_visibility import competitor_in_hotels
from src.collector.tier import get_brand
from src.config import settings
from src.models.collection_run import CollectionRun


async def main():
    p = argparse.ArgumentParser(description="竞对排序字段回填（ring/tier/ai_cooccurrence）")
    p.add_argument("run_id")
    p.add_argument("--apply", action="store_true", help="写回 positioning_json（默认只预览）")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        pos = dict(run.positioning_json or {})
        comps = pos.get("competitors") or []
        m = dict(run.measurement_json or {})
        client_brand = m.get("brand") or ""
        city = run.city or m.get("city")
        platforms = m.get("platforms", {})
        # 与甲方同题被推荐（hotels_recommended 名单口径）→ AI 同场景共现
        def _cooccur(comp_name: str) -> int:
            return sum(
                1
                for info in platforms.values()
                for j in info.get("judgments", [])
                for e in (j.get("hotels_recommended") or [])
                if competitor_in_hotels(e, client_brand, city)
                and any(competitor_in_hotels(x, comp_name, city) for x in j.get("hotels_recommended") or [])
            )
        print(f"=== {city}{client_brand} 竞对排序字段预览 ===")
        enriched = []
        for c in comps:
            if not isinstance(c, dict):
                c = {"name": str(c)}
            c = dict(c)
            band = c.get("band")
            c["ring"] = "核心" if band == COMPETITOR_BAND_MAIN else "近邻"
            brand = get_brand(c["name"], city=city)
            c["tier"] = brand["tier"] if brand else c.get("tier")
            c["ai_cooccurrence"] = _cooccur(c["name"])
            enriched.append(c)
            print(f"  {c['name']}: band={band} ring={c['ring']} tier={c['tier']} 共现={c['ai_cooccurrence']}")
        if args.apply:
            pos["competitors"] = enriched
            run.positioning_json = pos
            await db.commit()
            print(f"\n已写回 positioning_json（{len(enriched)} 竞对）")
        else:
            print("\n（预览，未写库。加 --apply 写回）")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
