"""P0-B 平台信源调性报告（只读，spec ⑪）。

platform_baseline 已在判定盖章（close_measurement）时 seal 进版本；本脚本只读展示/导出 md，
未 seal 的旧 run 则现场重算（纯 judgments 聚合）。回答甲方"文心 0% 是内容不足还是平台风格"。

用法：
  python scripts/report_platform_baseline.py <run_id>              # 打印 + 桌面 md
  python scripts/report_platform_baseline.py <run_id> --out /tmp  # 指定 md 输出目录
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.platform_baseline import compute_platform_baseline
from src.config import settings
from src.models.collection_run import CollectionRun

PLATFORM_CN = {"deepseek": "DeepSeek", "kimi": "Kimi", "doubao": "豆包", "wenxin": "文心一言"}


def render_md(measurement: dict, baseline: dict) -> str:
    brand = measurement.get("brand", "品牌")
    city = measurement.get("city", "城市")
    lines = [
        f"# {city}{brand} 平台信源调性（P0-B 基线）",
        "",
        f"- 甲方命中率：{measurement.get('overall', {}).get('overall_hit_rate', 0) * 100:.1f}%",
        "",
        "| 平台 | 每题平均列几家 | 甲方档位占比 | 甲方命中率 | 国际五星竞对平均 | 解读 | 复核 |",
        "|---|---|---|---|---|---|---|",
    ]
    def _pct(v):
        return f"{v * 100:.0f}%" if v is not None else "—"   # high_end_ratio/竞对 在数据不足态为 None
    for pl, b in baseline.items():
        cn = PLATFORM_CN.get(pl, pl)
        rv = b.get("review")
        st = "改判" if rv and rv["status"] == "revised" else "确认" if rv else "未复核"
        lines.append(
            f"| {cn} | {b['avg_hotels_listed']:.1f} | {_pct(b['high_end_ratio'])} | "
            f"{b['hit_rate'] * 100:.0f}% | {_pct(b['main_band_avg_rate'])} | {b['note']} | {st} |"
        )
    unknown = measurement.get("unknown_tier_hotels") or []
    if unknown:
        lines += ["", "## 数据盲区（表外酒店）", "",
                  f"- {len(unknown)} 家推荐酒店查不到品牌档位（brand_domains 表外）：{'、'.join(unknown[:10])}"
                  f"{'…' if len(unknown) > 10 else ''} —— 这些酒店的档位/同档判定未计入，"
                  f"真劣势/结构性结论可能被低估，见 brand_domains 信任缺口。"]
    lines += ["", "## 结论", ""]
    for pl, b in baseline.items():
        rv = b.get("review")
        st = f"（复核：{'改判' if rv['status'] == 'revised' else '确认'} {rv['reviewed_reading']}）" if rv else "（未复核，系统先验）"
        lines.append(f"- **{PLATFORM_CN.get(pl, pl)}**：{b['note']} {st}")
    return "\n".join(lines)


async def main():
    p = argparse.ArgumentParser(description="P0-B 平台信源调性报告（只读）")
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
        client_tier = (run.positioning_json or {}).get("tier")
        baseline = m.get("platform_baseline") or compute_platform_baseline(m, client_tier)
        md = render_md(m, baseline)
        print(md)
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{m.get('city','')}{m.get('brand','')}_平台信源调性.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"\n已导出 {path}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
