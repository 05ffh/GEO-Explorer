"""负面终判工具（spec 4.5 细筛）：粗筛候选 → 主 agent 逐条裁决 → 重算负面率写回 confirmed。

粗筛（classify_negative 关键词召回）只产出"候选"，不裁决；细筛（主 agent 逐条裁决）排除：
  主语不符（香格里拉市地名/他城/跨国）、语境不符（评分摘要/好评）、轻微不伤消费决策。
未裁决的候选默认不算负面（粗筛不当细筛，宁少勿滥）。

用法：
  python scripts/finalize_sentiment.py <run_id> --generate
      # 生成负面候选清单 /tmp/negative_review_<run_id前8位>.json
      # [{id, url, title, snippet, level(store/brand), themes}]
  python scripts/finalize_sentiment.py <run_id> --apply <verdict.json>
      # 读裁决（每条 {id, verdict: negative|exclude, reason}）
      # 排除 exclude 的分子+分母 → 重算负面率 → write_sentiment(status=confirmed)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import write_sentiment
from src.collector.sentiment import classify_negative
from src.config import settings
from src.models.search_result import SearchResultRecord


async def _load_rows(db, run_id):
    return (
        await db.execute(
            select(SearchResultRecord).where(SearchResultRecord.collection_run_id == run_id)
        )
    ).scalars().all()


def _level(query: str) -> str:
    return "brand" if "集团" in (query or "") else "store"


async def generate(run_id: str, out_path: str) -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        rows = await _load_rows(db, run_id)
    candidates = []
    for r in rows:
        hits = classify_negative(r.snippet or "")
        if hits:
            candidates.append({
                "id": str(r.id), "url": r.url, "title": r.title or "", "snippet": r.snippet or "",
                "level": _level(r.query), "themes": sorted({h.theme for h in hits}),
            })
    with open(out_path, "w") as fh:
        json.dump(candidates, fh, ensure_ascii=False, indent=2)
    print(f"负面候选 {len(candidates)} 条 → {out_path}")
    print("主 agent 逐条标 verdict: negative（真负面）/ exclude（误判：主语/语境/地区不符）+ reason")
    await engine.dispose()


async def apply(run_id: str, verdict_path: str) -> None:
    with open(verdict_path) as fh:
        verdicts = json.load(fh)
    vmap = {v["id"]: v for v in verdicts}

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        rows = await _load_rows(db, run_id)
        result = {}
        for level, key in (("store", "store_level"), ("brand", "brand_level")):
            level_rows = [r for r in rows if _level(r.query) == level]
            if not level_rows:
                continue  # 单档（无品牌级）→ 不写空 brand_level
            excluded = [r for r in level_rows if vmap.get(str(r.id), {}).get("verdict") == "exclude"]
            negative = [r for r in level_rows if vmap.get(str(r.id), {}).get("verdict") == "negative"]
            # 未裁决的候选默认不算负面（粗筛不当细筛）
            total_clean = len(level_rows) - len(excluded)
            themes: dict[str, int] = {}
            for r in negative:
                for h in classify_negative(r.snippet or ""):
                    themes[h.theme] = themes.get(h.theme, 0) + 1
            result[key] = {
                "total": total_clean,
                "negative_count": len(negative),
                "rate": round(len(negative) / total_clean, 4) if total_clean else 0.0,
                "themes": themes,
                "status": "confirmed",
                "excluded_count": len(excluded),
            }
        await write_sentiment(db, run_id, result)
        await db.commit()
        print("已写回 sentiment_json（status=confirmed）:")
        print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "themes"} for k, v in result.items()},
                         ensure_ascii=False, indent=1))
    await engine.dispose()


def main():
    p = argparse.ArgumentParser(description="负面终判：粗筛候选 → 主 agent 裁决 → 重算负面率写回")
    p.add_argument("run_id")
    p.add_argument("--generate", action="store_true", help="生成负面候选清单（供主 agent 裁决）")
    p.add_argument("--apply", metavar="verdict.json", help="按裁决重算负面率写回 sentiment_json")
    args = p.parse_args()
    if args.generate:
        asyncio.run(generate(args.run_id, f"/tmp/negative_review_{args.run_id[:8]}.json"))
    elif args.apply:
        asyncio.run(apply(args.run_id, args.apply))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
