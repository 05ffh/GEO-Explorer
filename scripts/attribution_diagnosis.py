"""P1 归因树诊断报告（只读，spec ⑪ P1 归因层 ①）。

compute_attribution_tree 是合成层（归因=假设，复测确认因果），不 seal 进测量版本，
本脚本读 sealed measurement_json + sentiment_json 现场算三侧归因树 + 综合主方向，
导出 md 供主 agent / 报告层使用。

用法：
  python scripts/attribution_diagnosis.py <run_id>              # 打印 + 桌面 md
  python scripts/attribution_diagnosis.py <run_id> --out /tmp  # 指定 md 输出目录
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.attribution_tree import compute_attribution_tree
from src.config import settings
from src.models.collection_run import CollectionRun

PLATFORM_CN = {"deepseek": "DeepSeek", "kimi": "Kimi", "doubao": "豆包", "wenxin": "文心一言"}


def render_md(measurement: dict, tree: dict) -> str:
    brand = measurement.get("brand", "品牌")
    city = measurement.get("city", "城市")
    ov = measurement.get("overall", {}).get("overall_hit_rate", 0)
    supply = tree["supply_side"]
    demand = tree["demand_side"]
    comp = tree["competition_side"]
    concl = tree["conclusion"]

    lines = [
        f"# {city}{brand} GEO 归因树（P1 归因层）",
        "",
        f"- 甲方命中率：{ov * 100:.1f}%",
        f"- 综合主方向：**{concl['primary']['direction']}**",
        f"- 主方向理由：{concl['primary']['reason']}",
        f"- 次方向：{'、'.join(concl['secondary']) if concl['secondary'] else '无'}",
        "",
        "## 供给侧（内容 / 信源）",
        "",
        f"- 铺信源信号平台：{'、'.join(PLATFORM_CN.get(p, p) for p in supply['deploy_signal_platforms']) or '无'}"
        f"（{supply['verdict']}）",
        f"- 内容资产：{supply['content_asset_count']} 条"
        + (f"，Top：{ '、'.join(a['content'] for a in supply['content_assets_top']) }" if supply["content_assets_top"] else ""),
        f"- 证据：{supply['evidence']}",
        "",
        "## 需求侧（口碑）",
        "",
        f"- 门店负面率 {demand['store_rate'] or 0:.1%} / 品牌负面率 {demand['brand_rate'] or 0:.1%}（合成 {demand['combined'] or 0:.1%}）",
        f"- 风险等级：{demand['risk_level'] or '—'} → {demand['verdict']}",
        "",
        "## 竞争侧（竞对压力）",
        "",
        f"- 相对可见度：{comp['relative_visibility']}（国际五星竞对平均被推 {comp['main_band_avg_rate'] or 0:.1%}）",
        f"- 四象限：{comp['quadrant_label'] or '—'}",
        f"- 甲方竞对缺口平台：{'、'.join(PLATFORM_CN.get(p, p) for p in comp['client_gap_platforms']) or '无'}",
        f"- 结论：{comp['verdict']}",
    ]
    if comp.get("disadvantage_dims"):
        dims_lines = []
        for dim, v in comp["disadvantage_dims"].items():
            parts = []
            if v.get("true_disadvantage"):
                parts.append(f"真劣势×{v['true_disadvantage']}")
            if v.get("client_has_unreferenced"):
                parts.append(f"甲方有未引用×{v['client_has_unreferenced']}")
            ev = (v.get("disadvantage_evidence") or [""])[0]
            dims_lines.append(f"{dim}（{'、'.join(parts) or '仅优势'}）：{ev}")
        lines += ["", "### 归因题劣势/优势维度（P1-② 提取，接地分类）", ""]
        for dl in dims_lines:
            lines.append(f"- {dl}")
    lines += ["", "## 结论", "", f"> {concl['summary']}"]
    return "\n".join(lines)


async def main():
    p = argparse.ArgumentParser(description="P1 归因树诊断报告（只读）")
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
        sentiment = dict(run.sentiment_json or {})
        tree = compute_attribution_tree(m, sentiment)
        md = render_md(m, tree)
        print(md)
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{m.get('city','')}{m.get('brand','')}_归因树.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"\n已导出 {path}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
