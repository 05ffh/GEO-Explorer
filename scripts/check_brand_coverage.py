"""brand_domains 覆盖度检查（只读，brand_domains 信任③，2026-09-10）。

诊断新城市/新品牌前，检查推荐名单里 brand_domains 表外的酒店（档位判定盲区）：
- 表外酒店按出现频次排序（高频 = 竞对/重要酒店，主 agent 复核后考虑补表 or write_competitor）
- 展示当前 brand_domains 覆盖摘要（该城市本地品牌 + 国际品牌档位分布），暴露覆盖缺口

用法：
  python scripts/check_brand_coverage.py <run_id>               # 该 run 的表外酒店频次
  python scripts/check_brand_coverage.py <run_id> --top 20      # 只看 Top N
"""
import argparse
import asyncio
from collections import Counter
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.tier import get_brand
from src.config import settings
from src.industry_knowledge.loader import get_knowledge_loader
from src.models.collection_run import CollectionRun


async def main():
    p = argparse.ArgumentParser(description="brand_domains 覆盖度检查（只读）")
    p.add_argument("run_id")
    p.add_argument("--top", type=int, default=15, help="表外酒店 Top N，默认 15")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        m = dict(run.measurement_json or {})
        city = run.city or m.get("city")
        unknown: Counter[str] = Counter()
        total = 0
        for info in m.get("platforms", {}).values():
            for j in info.get("judgments", []):
                for h in j.get("hotels_recommended") or []:
                    total += 1
                    if get_brand(h, city=city) is None:
                        unknown[h] += 1

        print(f"=== {run.city or ''}{m.get('brand','')} brand_domains 覆盖度 ===")
        print(f"推荐名单酒店共 {total} 条，表外（档位未知）{len(unknown)} 家 / {sum(unknown.values())} 条 "
              f"({sum(unknown.values()) / total * 100:.0f}%)")
        print(f"\n--- 表外 Top {args.top}（按频次，高频 = 竞对/重要酒店，考虑补表）---")
        for name, count in unknown.most_common(args.top):
            print(f"  {count:>3} 次  {name}")

        # 当前表覆盖摘要：该城市本地品牌 + 国际（无 region）档位分布
        items = get_knowledge_loader().load_category("brand_domains")
        local = [i for i in items if i.get("region") == (city or "").rstrip("市")]
        inter = [i for i in items if not i.get("region")]
        from collections import Counter as C
        print(f"\n--- 当前表覆盖 ---")
        print(f"本地品牌（region={city}）：{len(local)} 家，档位 {dict(C(i['tier'] for i in local))}")
        print(f"国际品牌（无 region）：{len(inter)} 家，档位 {dict(C(i['tier'] for i in inter))}")
        if unknown:
            print(f"\n→ 表外高频酒店若为甲方竞对，用 write_competitor 补入竞对；若为常见连锁，补 brand_domains。")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
