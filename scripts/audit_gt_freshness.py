"""GT 事实时效性审计（2026-09-18 韩香馆教训驱动）。

背景：GT 是归因/落地/报告的共同地基，但**酒旅资产会随时间变**（餐厅开闭/改造、商场店铺变动、
荣誉年评、设施开放、政策调整）——韩香馆（已停业）曾被当"甲方资产"，暴露 GT 时效从未系统校验。

本脚本：读 `collection_runs.gt_facts_json` → 对「易过时类别」列待复核清单 + 计算距
`last_verified_at` 的时效 → 输出人工复核清单（含建议搜索词）。**不自动联网**（时效判断需主 agent
联网+人工确认，见 spec 教训）。

用法：
  PYTHONPATH=. .venv/bin/python scripts/audit_gt_freshness.py <brand> <city> [--stale-days 180] [--out 报告.md]
"""
import argparse
import asyncio
import json
import sys
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import settings

# 易过时类别 → 建议搜索词后缀（第一性原理：这些会随时间变；客房/位置/会议是物理属性，变动慢）
VOLATILE_HINTS = {
    "餐饮": "餐厅 在营 停业 更名",
    "配套": "商场 配套 店铺 在营",
    "荣誉": "评级 荣誉 最新",
    "康体设施": "设施 营业 开放",
    "服务": "政策 调整 最新",
}
DEFAULT_STALE_DAYS = 180
# 已确认过时标记（脚本跳过，无需再复核）
_RESOLVED_MARKERS = ("已停业", "已改造", "已关闭", "已更名")


def _days_since(ts: str | None, today: date | None = None) -> int | None:
    if not ts:
        return None
    try:
        return ((today or date.today()) - datetime.fromisoformat(ts[:10]).date()).days
    except ValueError:
        return None


def build_report(gj: dict, stale_days: int = DEFAULT_STALE_DAYS,
                 run_id: str = "", today: date | None = None) -> tuple[str, int, bool]:
    """gt_facts_json → (报告 md, 待复核条数, 是否超期)。纯函数，便于测试。"""
    facts = gj.get("facts", {})
    last_verified = gj.get("last_verified_at")
    volatile_cats = set(gj.get("volatile_categories") or VOLATILE_HINTS.keys())
    elapsed = _days_since(last_verified, today)
    stale = elapsed is None or elapsed > stale_days

    L = [f"# GT 时效性审计 · {gj.get('brand','')}{gj.get('city','')}\n",
         f"- 诊断单元 run: `{run_id}`",
         f"- 上次复核: {last_verified or '**未记录**'}"
         + (f"（{elapsed} 天前）" if elapsed is not None else ""),
         f"- 时效状态: {'⚠️ **已超期，需复核**' if stale else '✅ 在时效内'}（阈值 {stale_days} 天）\n",
         f"## 待复核清单（易过时类别：{'/'.join(sorted(volatile_cats))}）\n",
         "> 复核方式：对每条用联网搜索确认**当前在营/有效状态**（注意：搜索摘要含历史资料，"
         "判在营优先看**甲方官网当前页面**；「信源存在」≠「现在在营」）。\n"]
    n = 0
    for cat, items in facts.items():
        if cat not in volatile_cats:
            continue
        pending = [it for it in items if not any(m in it.get("fact", "") for m in _RESOLVED_MARKERS)]
        if not pending:
            continue
        L.append(f"### {cat}")
        hint = VOLATILE_HINTS.get(cat, "")
        for it in pending:
            n += 1
            L.append(f"- [ ] {it.get('fact','')}  `[{it.get('source_tier','')}]`")
            L.append(f"      ↳ 建议搜索：`{gj.get('city','')}{gj.get('brand','')} {hint}`")
        L.append("")
    L.append(f"\n**共 {n} 条待复核**（已标停业/改造的条目已跳过）")
    return "\n".join(L), n, stale


async def main():
    p = argparse.ArgumentParser(description="GT 事实时效性审计")
    p.add_argument("brand")
    p.add_argument("city")
    p.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    p.add_argument("--out", help="输出 md 路径（默认 stdout）")
    args = p.parse_args()

    eng = create_async_engine(settings.database_url)
    async with eng.connect() as c:
        row = (await c.execute(text(
            "SELECT id, gt_facts_json FROM collection_runs "
            "WHERE brand_id=(SELECT id FROM brands WHERE name LIKE :bn LIMIT 1) AND city=:city "
            "AND gt_facts_json IS NOT NULL ORDER BY created_at DESC LIMIT 1"),
            {"bn": f"%{args.brand}%", "city": args.city})).fetchone()
    await eng.dispose()
    if not row:
        print(f"未找到 {args.brand}/{args.city} 的 gt_facts_json（先跑 run_gt_diagnosis 生成事实清单）")
        sys.exit(1)
    run_id, gj = row
    out, n, stale = build_report(gj or {}, args.stale_days, str(run_id))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print(f"审计报告 → {args.out}（{n} 条待复核，{'超期' if stale else '在时效内'}）")
    else:
        print(out)

if __name__ == "__main__":
    asyncio.run(main())
