"""人群推断写回工具（介入点清单第 8 条）：主 agent 从四信号判人群 → 写回 positioning.personas。

用法：python scripts/finalize_personas.py <run_id> 商务差旅 3 亲子家庭 1
  参数：人群 信号数 成对（信号数 = 官网定位描述/房型/设施/地理位置四信号命中的个数）

写回保留 tier/competitors，只更新 personas（write_positioning 会加 positioned_at）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import write_positioning
from src.config import settings
from src.models.collection_run import CollectionRun


async def main():
    p = argparse.ArgumentParser(description="人群推断写回：主 agent 判各人群信号数 → 写回 positioning.personas")
    p.add_argument("run_id")
    p.add_argument("pairs", nargs="+", help="人群 信号数 成对，如 商务差旅 3 亲子家庭 1")
    args = p.parse_args()
    if len(args.pairs) % 2 != 0:
        print("参数必须成对：人群 信号数 人群 信号数")
        sys.exit(1)
    try:
        personas = {args.pairs[i]: int(args.pairs[i + 1]) for i in range(0, len(args.pairs), 2)}
    except ValueError:
        print("信号数必须为整数（如 商务差旅 3）")
        sys.exit(1)
    for name, n in personas.items():
        if not (0 <= n <= 4):
            print(f"信号数应在 0-4 之间（{name}={n}，四信号：官网定位/房型/设施/位置）")
            sys.exit(1)

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        positioning = dict(run.positioning_json or {})
        positioning["personas"] = personas
        await write_positioning(db, run.id, positioning)
        await db.commit()
        print(f"人群推断写回: {personas}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
