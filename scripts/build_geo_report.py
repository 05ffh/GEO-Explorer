"""生成 AI 可见度诊断报告 HTML。

用法：
  PYTHONPATH=. .venv/bin/python scripts/build_geo_report.py <run_id> [--out output/]
"""
import argparse
import asyncio
import importlib
import os
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.models.collection_run import CollectionRun
from src.report.geo_report import render_report
from src.report.report_data import build_report_data, sentiment_status


async def main():
    p = argparse.ArgumentParser(description="生成 AI 可见度诊断报告 HTML")
    p.add_argument("run_id")
    p.add_argument("--out", default="output")
    a = p.parse_args()
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, a.run_id)
        if run is None:
            print(f"错误: run {a.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        # 终判闸门：舆情未终判（仍含粗筛误判）→ 拒绝出报告，把"漏执行"变成"跑不出来"
        st = sentiment_status(run)
        if st != "confirmed":
            print(f"错误: 舆情尚未终判（当前 status={st}）——报告不得出。")
            print(f"  请先终判：python scripts/finalize_sentiment.py {a.run_id} --generate"
                  f" → 主 agent 标 verdict → --apply <verdict.json>")
            await engine.dispose()
            sys.exit(1)
        data = build_report_data(run)
    await engine.dispose()
    mod = importlib.import_module(f"src.report.narratives.{data['city']}{data['brand']}")
    os.makedirs(a.out, exist_ok=True)
    html = render_report(data, mod.NARRATIVE, brand=data["brand"], city=data["city"],
                         date=(data.get("collected_at") or "")[:10])
    path = os.path.join(a.out, f"{data['city']}{data['brand']}_AI可见度诊断报告.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"已生成 {path}")


if __name__ == "__main__":
    asyncio.run(main())
