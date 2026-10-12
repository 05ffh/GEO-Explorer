"""V4 测量判定收口（P1-②，2026-09-11）：命中判定 → 归因劣势提取 → 一次盖章。

两阶段（归因接地需要 content_assets，而 content_assets 由命中判定后 finalize 产出）：
  阶段1 hit：apply_patch(命中) + finalize_measurement（算出 content_assets 供归因接地）→ 活数据，不开快照
  阶段2 seal：apply_attribution(归因) + close_measurement（全部派生）+ write(judge/rejudge) → V4 sealed 快照

用法：
  python scripts/finalize_v4.py hit <run_id> <命中patch.json>
  python scripts/finalize_v4.py seal <run_id> <归因patch.json>
"""
import asyncio
import json
import sys

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.attribution_extract import apply_attribution, aggregate_attribution
from src.collector.gt_entry import write_measurement
from src.collector.hit_rate import close_measurement, finalize_measurement
from src.collector.judgment_apply import apply_patch
from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot


async def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    phase, run_id, patch_file = sys.argv[1], sys.argv[2], sys.argv[3]

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, run_id)
        if run is None:
            print(f"错误: collection_run {run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        m = dict(run.measurement_json or {})
        pos = dict(run.positioning_json or {})
        tier = pos.get("tier")
        city = run.city
        competitors = pos.get("competitors") or []
        sentiment = run.sentiment_json or {}

        with open(patch_file, encoding="utf-8") as fh:
            patch = json.load(fh)

        if phase == "hit":
            applied = apply_patch(m, patch, city=city, client_tier=tier)
            finalize_measurement(m)   # 算出 content_assets（归因接地输入）
            await write_measurement(db, run_id, m, snapshot_type="draft")  # 活数据，等 seal 统一盖章
            await db.commit()
            print(f"[阶段1 hit] 回填 {applied} 题；content_assets {len(m.get('content_assets') or [])} 条（归因接地用）")
            await engine.dispose()
            return

        if phase == "seal":
            applied = apply_attribution(m, patch)
            m["attribution_dims"] = aggregate_attribution(m)
            remaining = close_measurement(m, competitors=competitors, sentiment=sentiment, city=city, client_tier=tier)
            has_snap = (await db.execute(
                select(func.count()).select_from(MeasurementSnapshot)
                .where(MeasurementSnapshot.collection_run_id == run_id)
            )).scalar() > 0
            snap_type = "rejudge" if has_snap else "judge"
            await write_measurement(db, run_id, m, snapshot_type=snap_type)
            await db.commit()
            dims = (m.get("attribution_dims") or {})
            dims_keys = list(dims.keys()) if isinstance(dims, dict) else dims
            print(f"[阶段2 seal] 归因回填 {applied} 题；盖章 {snap_type}，status={m['status']}，"
                  f"overall_hit_rate={m['overall']['overall_hit_rate']}，真劣势={m['miss_structure']['true_disadvantage']}，"
                  f"归因维度={dims_keys}")
            await engine.dispose()
            return

        print(f"未知阶段 {phase!r}（支持 hit / seal）")
        await engine.dispose()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
