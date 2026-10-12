"""P0-A 竞对相对可见度报告（只读，spec ⑫ 架构）。

competitor_visibility 已在「判定盖章」（finalize_hit --apply → close_measurement）时 seal 进版本，
本脚本只做只读展示/导出 md，不写库——用于：①给甲方/内部出报告；②复核某个 run 的竞对聚合。
（旧版会写库回填，已并入 close_measurement 收口，避免派生指标散落多脚本。）

用法：
  python scripts/aggregate_competitors.py <run_id>                # 打印 + 桌面 md
  python scripts/aggregate_competitors.py <run_id> --out /tmp    # 指定 md 输出目录
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.competitor_visibility import compute_competitor_visibility
from src.config import settings
from src.models.collection_run import CollectionRun


def render_md(measurement: dict, result: dict, run_id: str) -> str:
    brand = measurement.get("brand", "品牌")
    city = measurement.get("city", "城市")
    ov = result["overall"]
    main, secondary = ov["main"], ov["secondary"]
    lines = [
        f"# {city}{brand} 竞对相对可见度（P0-A 聚合）",
        "",
        f"- collection_run：{run_id}",
        f"- 甲方命中率：{ov['client_hit_rate'] * 100:.1f}%",
        "",
        f"## 主竞争带（国际五星同档）—— 相对可见度 {main['relative_visibility'] if main['relative_visibility'] is not None else '—'}",
        "",
        "| 竞对 | 被推荐率 | 平台分布 |",
        "|---|---|---|",
    ]
    for m in main["members"]:
        pr = " / ".join(f"{pl} {r*100:.0f}%" for pl, r in sorted(m["platform_rates"].items()))
        lines.append(f"| {m['name']} | {m['overall_rate'] * 100:.1f}% | {pr} |")
    lines.append(f"| **平均** | **{main['avg_rate'] * 100:.1f}%** | |")
    if main["relative_visibility"] is None:
        lines.append("")
        lines.append("> 竞对平均被推荐率 = 0 → 平台未进入甲方档位（结构性）")
    lines += ["", f"## 次竞争带（本地高端）—— 相对可见度 {secondary['relative_visibility'] if secondary['relative_visibility'] is not None else '—'}", ""]
    lines.append("| 竞对 | 被推荐率 | 平台分布 |")
    lines.append("|---|---|---|")
    for m in secondary["members"]:
        pr = " / ".join(f"{pl} {r*100:.0f}%" for pl, r in sorted(m["platform_rates"].items()))
        lines.append(f"| {m['name']} | {m['overall_rate'] * 100:.1f}% | {pr} |")
    lines.append(f"| **平均** | **{secondary['avg_rate'] * 100:.1f}%** | |")
    lines += ["", "## 四象限诊断", ""]
    q = result["quadrant"]
    lines.append(f"- 有效可见度 {q['effective_visibility']}（绝对健康度）× 主相对可见度 {main['relative_visibility']} → **{q['label']}**")
    lines += ["", "## 同题真劣势（竞对在名单、甲方未推荐）", ""]
    rows = [
        d for d in result["question_detail"]
        if not d["client_recommend"] and (d["main_in"] or d["secondary_in"])
    ]
    for d in rows[:30]:
        who = "、".join(d["main_in"] + d["secondary_in"])
        lines.append(f"- [{d['platform']}] {d['question_id']}：{d['question']} → 竞对在：{who}")
    if not rows:
        lines.append("- 无")
    return "\n".join(lines)


async def main():
    p = argparse.ArgumentParser(description="P0-A 竞对相对可见度报告（只读，spec ⑫）")
    p.add_argument("run_id")
    p.add_argument("--out", default="./output", help="md 输出目录")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        m = dict(run.measurement_json or {})
        if not m.get("platforms"):
            print("该 run 无测量数据")
            await engine.dispose()
            sys.exit(1)
        competitors = (run.positioning_json or {}).get("competitors") or []
        if not competitors:
            print("无竞对（positioning.competitors 为空），先 write_competitor 写竞对")
            await engine.dispose()
            sys.exit(1)

        # 竞对归一化（字符串→{name,band}）已收敛在 compute_competitor_visibility 内部（spec ⑫ 单一口径）
        result = compute_competitor_visibility(m, competitors, run.city)
        md = render_md(m, result, args.run_id)
        print(md)
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{m.get('city','')}{m.get('brand','')}_竞对相对可见度.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"\n已导出 {path}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
