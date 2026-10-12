"""CDP 中间处理层产出 → gt_facts_json（第一判决依据）接入工具。

链路（spec「CDP 中间处理层设计」）：
  fetch_ota_cdp.py（raw → search_results，已通）
  → 主 agent 中间处理层（读 raw → 归 gt_facts_json 8 类 + 跨平台一致性核对 + 高价值过滤；非脚本自动化）
  → 本脚本：写 cdp_facts_json（独立存）→ 合并三态 → gt_facts_json

用法：
  python scripts/ingest_cdp_facts.py <collection_run_id> --generate [--out 待处理.json]
    （产中间处理层待处理输入：各平台 content_text + 内嵌固化 spec，供主 agent 判定）
  python scripts/ingest_cdp_facts.py <collection_run_id> --from 中间处理层产出.json [--apply-conflicts] [--dry-run]
    （--from - 读 stdin；--dry-run 只算不落库，预览三态）

输入 JSON（= cdp_facts_json 结构，8 类对齐 gt_facts_json）：
  {"facts": {"位置交通": [{"fact": "步行约3分钟到南门兜站", "platforms": ["携程"]}], ...},
   "consistency": {"地址": "agree", "房型": "agree"}}

三态（merge 默认）：去重/补充自动并入 gt_facts_json；冲突（同属性数字不同）默认不并入，
记 cdp_facts_json["merge_conflicts"] 待主 agent 核验——第一判决依据改动须可控可审计。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import generate_cdp_midlayer_input, merge_cdp_facts_into_gt, write_cdp_facts
from src.config import settings
from src.models.collection_run import CollectionRun


# gt_facts_json 8 类（spec §546：下游只消费这 8 类——render_gt_facts 归因判决 + theme_blocks P4 素材）。
# theme_blocks 只认这 8 类中的 7 类（荣誉不进主题块）；类名写错 → P4 静默丢弃且无下游报错 → 信任边界必须拦。
_CLASSES = frozenset({"位置交通", "客房", "康体设施", "餐饮", "会议宴会", "服务", "配套", "荣誉"})


def load_cdp_facts(text: str) -> dict:
    """解析并校验中间处理层产出（信任边界：主 agent 手写 JSON 落第一依据前必须校验）。"""
    data = json.loads(text)
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, dict) or not facts:
        raise ValueError("输入须为 {'facts': {类名: [事实...]}}，且 facts 非空")
    for cls, items in facts.items():
        if cls not in _CLASSES:
            raise ValueError(f"类名 {cls!r} 不在 GT 8 类内：{sorted(_CLASSES)}")
        if not isinstance(items, list) or not items:
            raise ValueError(f"facts[{cls!r}] 须为非空列表")
        for it in items:
            if not isinstance(it, dict) or not isinstance(it.get("fact"), str) or not it["fact"].strip():
                raise ValueError(f"facts[{cls!r}] 每项须为 dict 且含非空 str 'fact'")
    return data


async def ingest(db, run_id, facts: dict, *, apply_conflicts: bool = False) -> dict:
    """写 cdp_facts_json（独立存）→ 合并三态进 gt_facts_json，返回 summary。"""
    await write_cdp_facts(db, run_id, facts)
    return await merge_cdp_facts_into_gt(db, run_id, apply_conflicts=apply_conflicts)


def _print_summary(n_facts: int, n_classes: int, summary: dict) -> None:
    print(f"CDP 中间处理层产出 {n_facts} 条（{n_classes} 类）→ cdp_facts_json")
    print(f"合并三态：补充 {len(summary['added'])} / 去重 {len(summary['deduped'])} / 冲突 {len(summary['conflicts'])}")
    for c in summary["conflicts"]:
        print(f"  ⚠ 冲突[{c['class']}] CDP：{c['cdp']}  ≠ GT：{c['gt']}")
    if summary["conflicts"]:
        print("  冲突默认未并入（已记 cdp_facts_json.merge_conflicts）——核验后重跑 --apply-conflicts")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--generate", action="store_true",
                    help="产中间处理层待处理输入（各平台 content_text + 内嵌 spec），供主 agent 判定")
    ap.add_argument("--out", help="--generate 时写文件（默认 stdout）")
    ap.add_argument("--from", dest="src", help="中间处理层产出 JSON 路径，或 - 读 stdin（apply 用）")
    ap.add_argument("--apply-conflicts", action="store_true", help="冲突也并入（默认不并入，待核验）")
    ap.add_argument("--dry-run", action="store_true", help="只算不落库（预览三态）")
    args = ap.parse_args()

    if not args.generate and not args.src:
        print("错误: 须给 --generate（产待处理输入）或 --from（apply 中间处理层产出）")
        return 1

    facts = None
    if not args.generate:
        if args.src == "-":
            text = sys.stdin.read()
        else:
            with open(args.src, encoding="utf-8") as fh:
                text = fh.read()
        try:
            facts = load_cdp_facts(text)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"错误: 输入非法 —— {e}")
            return 1

    engine = create_async_engine(settings.database_url, connect_args={"timeout": 5})
    out = None
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        if await db.get(CollectionRun, args.run_id) is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            return 1
        if args.generate:
            out = await generate_cdp_midlayer_input(db, args.run_id)
        else:
            summary = await ingest(db, args.run_id, facts, apply_conflicts=args.apply_conflicts)
            if args.dry_run:
                await db.rollback()
            else:
                await db.commit()
    await engine.dispose()

    if args.generate:
        if not out["platforms"]:
            print("错误: 该 run 无 CDP 采集成品（先跑 fetch_ota_cdp.py）")
            return 1
        text = json.dumps(out, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"中间处理层待处理 {len(out['platforms'])} 平台 → {args.out}")
        else:
            print(text)
        return 0

    _print_summary(sum(len(v) for v in facts["facts"].values()), len(facts["facts"]), summary)
    if args.dry_run:
        print("（--dry-run：未落库，以上为预览）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
