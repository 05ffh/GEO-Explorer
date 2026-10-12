"""测量版本对比：从 measurement_snapshots 取两个版本，输出整体 + 四平台命中率对比。

用法：
  python -m scripts.compare_measure <collection_run_id>            # 对比最新两个版本
  python -m scripts.compare_measure <collection_run_id> --from 1 --to 2

不带 --from/--to 时列出全部版本后对比最新两个。
"""
import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot


async def main():
    p = argparse.ArgumentParser(description="测量版本对比")
    p.add_argument("run_id")
    p.add_argument("--from", dest="frm", type=int, default=None, help="起始版本号")
    p.add_argument("--to", dest="to", type=int, default=None, help="终止版本号")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        snaps = (
            await db.execute(
                select(MeasurementSnapshot)
                .where(MeasurementSnapshot.collection_run_id == args.run_id)
                .order_by(MeasurementSnapshot.snapshot_no)
            )
        ).scalars().all()
        if not snaps:
            print("该 run 无测量快照（先跑 run_measure 采集）")
            await engine.dispose()
            sys.exit(1)

        print("=== 现有版本 ===")
        for s in snaps:
            overall = s.measurement_json.get("overall", {}).get("overall_hit_rate")
            print(f"  v{s.snapshot_no} [{s.snapshot_type}] {s.collected_at}  回填:{s.backfilled_at or '-'}  整体可见度:{overall}")

        by_no = {s.snapshot_no: s for s in snaps}
        frm = args.frm if args.frm is not None else (snaps[-2].snapshot_no if len(snaps) > 1 else snaps[0].snapshot_no)
        to = args.to if args.to is not None else snaps[-1].snapshot_no
        a, b = by_no.get(frm), by_no.get(to)
        if a is None or b is None:
            print(f"错误: 版本号不存在（可用 {sorted(by_no)}）")
            await engine.dispose()
            sys.exit(1)

        ma, mb = a.measurement_json, b.measurement_json
        oa, ob = ma.get("overall", {}), mb.get("overall", {})
        print(f"\n=== 对比 v{frm} ({a.collected_at}) → v{to} ({b.collected_at}) ===")
        print(f"整体可见度: {oa.get('overall_hit_rate')} → {ob.get('overall_hit_rate')}")

        pa, pb = ma.get("platforms", {}), mb.get("platforms", {})
        print(f"\n平台命中率对比:")
        print(f"  {'平台':<10} {'v' + str(frm):<10} {'v' + str(to):<10} 变化")
        for pl in sorted(set(pa) | set(pb)):
            ra = pa.get(pl, {}).get("platform_rate", {}).get("hit_rate")
            rb = pb.get(pl, {}).get("platform_rate", {}).get("hit_rate")
            delta = "" if ra is None or rb is None else f"{rb - ra:+.2f}"
            print(f"  {pl:<10} {ra or '-':<10} {rb or '-':<10} {delta}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
