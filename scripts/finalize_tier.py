"""档位精修工具（介入点清单第 1 条）：主 agent 提取 ADR/星级 → derive_tier 算档位 → 写回 positioning.tier。

用法：
  python scripts/finalize_tier.py <run_id> --adr 850 --star 五星   # 工具用 derive_tier 综合算
  python scripts/finalize_tier.py <run_id> --tier 高端              # 主 agent 直接指定（derive_tier 无法推导/判断更准）

写回保留 personas/competitors，只更新 tier + tier_reason（write_positioning 会加 positioned_at）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import write_positioning
from src.collector.tier import _ORDER, derive_tier
from src.config import settings
from src.models.brand import Brand
from src.models.collection_run import CollectionRun


async def main():
    p = argparse.ArgumentParser(description="档位精修：主 agent 提取 ADR/星级 → derive_tier → 写回 positioning.tier")
    p.add_argument("run_id")
    p.add_argument("--adr", type=float, default=None, help="主 agent 从 adr 字段材料提取的 ADR（search 带 URL）")
    p.add_argument("--star", default=None, help="星级（五星/四星/三星）")
    p.add_argument("--tier", default=None, help="直接指定档位（derive_tier 无法推导或主 agent 判断更准）")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        brand = (await db.execute(select(Brand).where(Brand.id == run.brand_id))).scalar_one_or_none()
        brand_zh = brand.name if brand else ""

        if args.tier:
            if args.tier not in _ORDER:
                print(f"档位无效: {args.tier}（可选 {_ORDER}）")
                await engine.dispose()
                sys.exit(1)
            tier, reason = args.tier, f"主 agent 直接指定: {args.tier}"
        else:
            tier = derive_tier(brand_zh, adr=args.adr, star_rating=args.star, city=run.city)
            reason = f"derive_tier 精修（品牌 {brand_zh}，输入 ADR={args.adr} 星级={args.star}）→ {tier}"
        if tier is None:
            print("derive_tier 无法推导（品牌表外 + 无 ADR/星级），请用 --tier 直接指定档位")
            await engine.dispose()
            sys.exit(1)

        positioning = dict(run.positioning_json or {})
        positioning["tier"] = tier
        positioning["tier_reason"] = reason
        if args.adr is not None:
            positioning["adr"] = args.adr   # 持久化 ADR：P3 主竞对「ADR 带内选」读 positioning.adr（competitor.select_primary）
        await write_positioning(db, run.id, positioning)
        await db.commit()
        print(f"档位精修完成: {brand_zh} → {tier}（{reason}）")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
