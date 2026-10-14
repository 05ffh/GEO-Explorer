"""舆情-only 刷新：**只重跑舆情采集**（两路搜索后端）→ 初筛负面率 → 写 `sentiment_json` + 舆情材料。

**为什么需要**：`run_gt_diagnosis` 是 P2 全量重跑（事实搜索 + 甲方页面全文 + CDP 三平台 + 舆情）——
只想"刷舆情"时会**顺带重抓** GT 的来源语料（甲方页面/CDP），多余。本脚本只做舆情那一步。

不碰：GT（gt_facts_json）/ 甲方页面全文 / CDP。负面率写 `status=preliminary`（终判仍走 `finalize_sentiment`）。

用法：
  python scripts/refresh_sentiment.py <run_id> [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_collector_v2 import collect_sentiment, group_by_field
from src.collector.gt_entry import write_search_result, write_sentiment
from src.collector.sentiment import compute_negative_rate
from src.config import settings
from src.models.brand import Brand
from src.models.collection_run import CollectionRun
from src.search.search_all import search_all_backends


async def refresh_run_sentiment(db, run: CollectionRun, search_fn) -> dict:
    """只重采舆情：`collect_sentiment` → 初筛负面率 → 写 `sentiment_json`(preliminary) + 舆情材料（按 url 去重）。

    `search_fn` 可注入（测试）。返回 summary（材料数/新落库行/门店级+品牌级负面率）。
    """
    brand_name = (await db.execute(select(Brand.name).where(Brand.id == run.brand_id))).scalar() or ""
    senti = await collect_sentiment(brand_name, run.city, search_fn)
    if not senti:
        # 两路后端全失败（网络/额度）→ **不覆盖**已有 sentiment_json，防 confirmed 舆情被空初筛冲毁。
        return {"materials": 0, "new_rows": 0, "store_level": {}, "brand_level": {}, "written": False}
    grouped = group_by_field(senti)
    store = compute_negative_rate(grouped.get("store_level", []))
    brand_neg = compute_negative_rate(grouped["brand_level"]) if grouped.get("brand_level") else None
    senti_json = {"store_level": {**store, "status": "preliminary"}}
    if brand_neg is not None:                    # 单档（体系B，无品牌级词）→ 不写 brand_level
        senti_json["brand_level"] = {**brand_neg, "status": "preliminary"}
    await write_sentiment(db, run.id, senti_json)
    # 舆情材料落 search_results（按 url 去重，避免重复刷新堆行）
    existing = set((await db.execute(
        text("SELECT url FROM search_results WHERE collection_run_id=:r AND url <> ''"),
        {"r": run.id})).scalars().all())
    new_rows = 0
    for m in senti:
        if m.url and m.url in existing:
            continue
        if m.url:
            existing.add(m.url)
        await write_search_result(db, run.organization_id, run.brand_id, run.id,
                                  m.provider, m.query, m.url, m.title, m.snippet, m.tier, m.published_at)
        new_rows += 1
    return {"materials": len(senti), "new_rows": new_rows,
            "store_level": store, "brand_level": brand_neg, "written": True}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--dry-run", action="store_true", help="采+算但不落库（预览负面率）")
    args = ap.parse_args()

    engine = create_async_engine(settings.database_url, connect_args={"timeout": 5})
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            return 1
        summary = await refresh_run_sentiment(db, run, search_all_backends)
        if args.dry_run:
            await db.rollback()
        else:
            await db.commit()
    await engine.dispose()

    if not summary.get("written", True):
        print("舆情刷新：⚠️ 两路后端均无结果 → 未落库（保留原有舆情），请核查后端后重跑")
        return 1
    print(f"舆情刷新：{summary['materials']} 材料 → 新落库 {summary['new_rows']} 行")
    print(f"  门店级负面率（preliminary）: {summary['store_level']['rate']}")
    if summary.get("brand_level"):
        print(f"  品牌级负面率（preliminary）: {summary['brand_level']['rate']}")
    if args.dry_run:
        print("（--dry-run：未落库）")
    else:
        print(f"下一步（终判）：python scripts/finalize_sentiment.py {args.run_id} --generate → 主 agent 标 verdict → --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
