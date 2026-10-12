"""场景匹配竞对分配（P1-②，2026-09-10）：从 sealed 测量算每场景头号对手，写回 positioning_json。

范围严格锁死：只从 positioning.competitors 确认竞对（主=国际五星同档/次=本地高端同档）里选，
表外/未确认酒店不参与（走覆盖度检查 → write_competitor 补确认 → 下一轮才进匹配）。
写回 positioning_json["scenario_competitors"] = {"商务差旅": "福州世茂洲际酒店", ...}，
measure_platform 读它给归因题按场景注入对比对象（无则回退单主竞对）。

用法：
  python scripts/assign_scenario_competitors.py <run_id>          # 预览
  python scripts/assign_scenario_competitors.py <run_id> --apply  # 写回 positioning_json
"""
import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.competitor_visibility import compute_scenario_competitors
from src.config import settings
from src.models.collection_run import CollectionRun


async def main():
    p = argparse.ArgumentParser(description="场景匹配竞对分配（写 positioning_json.scenario_competitors）")
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
        city = run.city or m.get("city")
        sc = compute_scenario_competitors(m, comps, city)
        print("=== 场景匹配竞对（只从确认竞对里选）===")
        if not sc:
            print("（无确认竞对 / 无共现数据）")
        for scenario, name in sc.items():
            print(f"  {scenario}: {name}")
        if args.apply:
            pos["scenario_competitors"] = sc
            run.positioning_json = pos
            await db.commit()
            print(f"\n已写回 positioning_json.scenario_competitors（{len(sc)} 场景）")
            print("注意：场景竞对变 → 归因题文本变 → 需重跑 run_measure 才能让归因题按场景分对手"
                  "（会自动开新基线、复制 P2）；当前 run 的归因题仍是未分场景的旧文本")
        else:
            print("\n（预览，未写库。加 --apply 写回）")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
