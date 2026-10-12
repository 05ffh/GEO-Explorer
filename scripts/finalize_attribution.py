"""归因劣势提取工具（P1-②）：generate 待提取清单（含甲方接地上下文）→ 子 agent 提取 → apply 回填。

用法：
  1. generate：python scripts/finalize_attribution.py generate <collection_run_id> --out 归因待提取.json
     → 输出归因层（layer=attribution）待提取题（题目+回答+client_context 甲方已知属性接地）
  2. 子 agent 提取 JSON（按平台+题；资产类劣势维度填 corpus_fact，type 由系统派生，不输出）：
     {"deepseek": {"attr_business": {"pick": "competitor",
         "client_disadvantage_dims": [{"dim": "位置", "corpus_fact": "none", "evidence": "世茂洲际市中心"}],
         "client_advantage_dims": [{"dim": "餐饮", "evidence": "香格里拉餐饮口碑强"}]}}}
  3. apply：python scripts/finalize_attribution.py apply <collection_run_id> 提取.json
     → 写回 judgment.attribution_result + 聚合 attribution_dims + 更新 measurement_json（活数据，不开快照）
     盖章（sealed 快照）由 finalize_v4.py 统一做（命中+归因一次收口）
"""
import argparse
import asyncio
import json
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.attribution_extract import apply_attribution, aggregate_attribution, generate_attribution_pending
from src.collector.client_pages import build_grounding_corpus
from src.collector.gt_entry import write_measurement
from src.config import settings
from src.models.collection_run import CollectionRun


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode, run_id = sys.argv[1], sys.argv[2]
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, run_id)
        if run is None:
            print(f"错误: collection_run {run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        m = dict(run.measurement_json or {})

        if mode == "generate":
            # 接地两级（2026-09-18 架构）：gt_facts_json 第一判决依据 + grounding_corpus 原文佐证
            # spec 由 generate_attribution_pending 内嵌（自包含契约，防漂移）
            corpus = await build_grounding_corpus(db, run.brand_id, run.city)
            out = generate_attribution_pending(m, grounding_corpus=corpus, gt_facts=run.gt_facts_json,
                                               force="--force" in sys.argv)
            out_path = None
            if "--out" in sys.argv:
                i = sys.argv.index("--out")
                if i + 1 < len(sys.argv):
                    out_path = sys.argv[i + 1]
            total = sum(len(v) for v in out["platforms"].values())
            if out_path:
                with open(out_path, "w", encoding="utf-8") as fh:
                    json.dump(out, fh, ensure_ascii=False, indent=2)
                print(f"归因待提取 {total} 题（接地上下文 {len(out['client_context'])} 条甲方属性）→ {out_path}")
            else:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            await engine.dispose()
            return

        if mode == "apply":
            patch_file = sys.argv[3]
            with open(patch_file, encoding="utf-8") as fh:
                patch = json.load(fh)
            applied = apply_attribution(m, patch)
            m["attribution_dims"] = aggregate_attribution(m)
            await write_measurement(db, run_id, m, snapshot_type="draft")  # 活数据，不开快照（V4 收口统一盖）
            await db.commit()
            print(f"已回填归因劣势 {applied} 题；聚合维度：{list((m.get('attribution_dims') or {}).keys())}")
            await engine.dispose()
            return

        print(f"未知模式 {mode!r}（支持 generate / apply）")
        await engine.dispose()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
