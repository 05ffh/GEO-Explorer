"""归因题冒烟测试（P1-②，2026-09-11）：1-2 平台采集归因题回答，验证对比/平衡回答质量。

目的：正式全量采集前，先确认归因题（甲方 vs 场景头号对手）能问出「AI 真对比 + 给理由」的回答。
只采、只打印归因层回答（layer=attribution，10 题/平台），不落库、不判定。

用法：
  python scripts/smoke_attribution.py <run_id> --platforms deepseek,kimi
  python scripts/smoke_attribution.py <run_id> --platforms deepseek       # 单平台更省额度
"""
import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.competitor import select_primary
from src.collector.measure import measure_platform
from src.collector.question_builder import build_questions
from src.collector.rate_limiter import build_rate_limiters
from src.config import settings
from src.models.collection_run import CollectionRun
from scripts.run_measure import PLATFORM_ADAPTERS, find_brand_en, make_ask_fn


async def main():
    p = argparse.ArgumentParser(description="归因题冒烟测试（只采归因回答打印，不落库）")
    p.add_argument("run_id")
    p.add_argument("--platforms", default="deepseek", help="逗号分隔，默认 deepseek（最省额度）")
    args = p.parse_args()
    platforms = [x.strip() for x in args.platforms.split(",") if x.strip()]

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        pos = dict(run.positioning_json or {})
        brand = (run.measurement_json or {}).get("brand") or "香格里拉"
        city = run.city or "福州"
        tier = pos.get("tier")
        competitors = pos.get("competitors") or []
        primary = select_primary(competitors, tier) if competitors else None
        competitor = primary["name"] if primary else (competitors[0]["name"] if competitors else None)
        scenario_competitors = pos.get("scenario_competitors") or {}
        brand_en = find_brand_en(brand)

        limiters = build_rate_limiters(platforms)

        async def _one(pl: str):
            adapter = PLATFORM_ADAPTERS[pl]()
            result = await measure_platform(
                brand, city, brand_en, pos, make_ask_fn(adapter, limiters[pl]), platform=pl)
            attrs = [j for j in result["judgments"] if j["layer"] == "attribution"]
            print(f"\n{'='*60}\n平台 {pl}：归因题 {len(attrs)} 道\n{'='*60}")
            for j in attrs:
                answer = (j.get("answer") or "").strip()
                print(f"\n【{j['question_id']}】{j['question']}")
                print(f"  回答（前 500 字）: {answer[:500]}{'…' if len(answer) > 500 else ''}")
            return pl

        await asyncio.gather(*(_one(pl) for pl in platforms))
        print("\n（冒烟完成：未落库。请主 agent 判断归因回答质量 → 决定是否全量采集）")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
