"""导出测量提问+回答+判定为 md（分平台，格式同「福州香格里拉_XX回答.md」）。

用法：
  python -m scripts.export_answers <collection_run_id>                  # 全部平台 → 桌面
  python -m scripts.export_answers <run_id> --platforms deepseek,kimi   # 指定平台
  python -m scripts.export_answers <run_id> --version 2                # 指定快照版本（默认最新）
  python -m scripts.export_answers <run_id> --out /tmp                 # 指定输出目录
"""
import argparse
import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.judgment import LAYER_ATTRIBUTION
from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot

PLATFORM_CN = {"deepseek": "DeepSeek", "kimi": "Kimi", "doubao": "豆包", "wenxin": "文心一言"}

REC_CN = {"recommend": "推荐", "mention": "提及", "exclude": "排除", "absent": "未提"}
DIM_CN = {"region": "区域", "tier": "档位", "topic": "话题", "category": "话题", "budget": "预算"}


def attribution_block(j: dict) -> str:
    """归因题提取块（P1-②，2026-09-13）：展示 pick + 劣势/优势维度（带接地分类）。"""
    if j.get("error"):
        return "**子 agent 提取：**\n\n- ⚠️ 提问失败（无回答可提取）"
    r = j.get("attribution_result") or {}
    pick = r.get("pick")
    pick_cn = {"competitor": "竞品", "client": "甲方", "tie": "无明确偏向", "no_choice": "没给结论"}.get(pick)
    dis = r.get("client_disadvantage_dims") or []
    adv = r.get("client_advantage_dims") or []
    lines = ["**子 agent 提取：**", ""]
    if pick is not None:
        lines.append(f"- **偏向**：{pick_cn or pick}（{pick}）")
    if dis:
        for d in dis:
            typ = "甲方有未引用" if d.get("type") == "client_has_unreferenced" else "真劣势"
            lines.append(f"- **劣势·{d.get('dim')}**（{typ}）：{d.get('evidence')}")
    else:
        lines.append("- **劣势**：无")
    if adv:
        for d in adv:
            lines.append(f"- **优势·{d.get('dim')}**：{d.get('evidence')}")
    else:
        lines.append("- **优势**：无")
    return "\n".join(lines)


def judge_block(j: dict) -> str:
    """子 agent 判定块（V3 格式，2026-09-06 定稿）：每题展示判定/场景/同档被推/引用内容/has_hotel。"""
    if j.get("layer") == LAYER_ATTRIBUTION:
        return attribution_block(j)
    if j.get("error"):
        return "**子 agent 判定：**\n\n- ⚠️ 提问失败（无回答可判定）"
    rec = j.get("recommendation")
    rec_cn = REC_CN.get(rec, str(rec))
    scene = j.get("scene")
    if scene and (scene.get("val") or scene.get("dim")):
        dim = DIM_CN.get(scene.get("dim"), scene.get("dim"))
        scene_str = f"{dim}「{scene.get('val')}」"
        if scene.get("rank_in_scene"):     # rank 缺（子 agent 未给）→ 只显示 维度「场景名」，不显示 null
            scene_str += f"rank {scene.get('rank_in_scene')}/{scene.get('in_scene_count')}"
    else:
        scene_str = "null"
    same = j.get("same_tier_pushed")
    if rec == "recommend":
        same_str = "—（命中）"
    elif rec == "absent":
        same_str = "真劣势（同档出现，未提甲方）" if same else "结构性（同档未推，未提甲方）"
    elif rec == "mention":
        same_str = "提及（未被推荐）"
    elif rec == "exclude":
        same_str = "排除（明确不推荐）"
    else:
        same_str = "—"
    ref = j.get("referred_content") or []
    ref_str = "；".join(ref) if ref else "-"
    has = "True" if j.get("has_hotel_recommendations") else "False"
    return (
        f"**子 agent 判定：**\n\n"
        f"- **判定**：{rec_cn}（{rec}）\n"
        f"- **场景**：{scene_str}\n"
        f"- **同档被推**：{same_str}\n"
        f"- **引用内容**：{ref_str}\n"
        f"- has_hotel_recommendations：{has}"
    )


def build_platform_md(platform: str, measurement: dict) -> str:
    info = measurement["platforms"][platform]
    rate = info["platform_rate"]
    judgments = info["judgments"]
    brand = measurement.get("brand", "品牌")
    city = measurement.get("city", "城市")
    collected = info.get("collected_at", measurement.get("collected_at", ""))
    lines = [f"# {PLATFORM_CN.get(platform, platform)} 平台回答 + 子 agent 命中判定（{city}{brand} AI 可见度诊断）", ""]
    lines += [
        f"- 品牌：{brand}（{city}）",
        f"- 诊断时间：{collected}",
        f"- collection_run：{measurement.get('_run_id', '')}",
        f"- 命中率：{rate['hit_rate'] * 100:.1f}%（{rate['hit_count']}/{rate['valid']}，命中层分母）首推 {rate['first_rate'] * 100:.1f}% 平均排名 {rate['avg_rank']}（total {rate['total']} 含归因层，不进命中分母）",
        f"- 判定口径：二分命中（hit = 推荐，含推荐列表内靠后）；命中独立于竞争关系与区域档位；备选区域唯一列出=推荐；has_hotel=false（只答区域）排除出分母",
        "",
        "---",
        "",
    ]
    for j in judgments:
        lines.append(f"## {j.get('question_id', '')}：{j['question']}")
        lines.append("")
        lines.append("**AI 回答：**")
        lines.append("")
        if j.get("error"):
            lines.append(f"> ⚠️ 提问失败：{j['error']}")
        else:
            lines.append("> " + (j.get("answer", "") or "").replace("\n", "\n> "))
        lines.append("")
        lines.append(judge_block(j))
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


async def main():
    p = argparse.ArgumentParser(description="导出提问+回答+判定 md（分平台）")
    p.add_argument("run_id")
    p.add_argument("--platforms", default=None, help="逗号分隔，默认全部")
    p.add_argument("--version", type=int, default=None, help="指定快照版本，默认最新")
    p.add_argument("--suffix", default="", help="文件名版本后缀（如 v3.2 → {平台}回答_v3.2.md）")
    p.add_argument("--out", default="./output", help="输出目录")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        if args.version is not None:
            snap = (
                await db.execute(
                    select(MeasurementSnapshot).where(
                        MeasurementSnapshot.collection_run_id == args.run_id,
                        MeasurementSnapshot.snapshot_no == args.version,
                    )
                )
            ).scalar_one_or_none()
            if snap is None:
                print(f"错误: 版本 v{args.version} 不存在")
                await engine.dispose()
                sys.exit(1)
            measurement = dict(snap.measurement_json)
            print(f"使用版本 v{args.version} [{snap.snapshot_type}] {snap.collected_at}")
        else:
            snap = (
                await db.execute(
                    select(MeasurementSnapshot)
                    .where(MeasurementSnapshot.collection_run_id == args.run_id)
                    .order_by(MeasurementSnapshot.snapshot_no.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snap is not None:
                measurement = dict(snap.measurement_json)
                print(f"使用最新 sealed 快照 v{snap.snapshot_no} [{snap.snapshot_type}] {snap.collected_at}")
            else:
                measurement = dict(run.measurement_json or {})
                print("警告: 无 sealed 快照，回退活 measurement_json（可能为未判定草稿）")
        if not measurement.get("platforms"):
            print("该 run 无测量数据")
            await engine.dispose()
            sys.exit(1)
        measurement["_run_id"] = args.run_id
        os.makedirs(args.out, exist_ok=True)
        plats = [x.strip() for x in args.platforms.split(",")] if args.platforms else list(measurement["platforms"])
        brand, city = measurement.get("brand", "品牌"), measurement.get("city", "城市")
        for pl in plats:
            if pl not in measurement["platforms"]:
                print(f"跳过未知平台 {pl}")
                continue
            md = build_platform_md(pl, measurement)
            suffix = f"_{args.suffix}" if args.suffix else ""
            path = os.path.join(args.out, f"{city}{brand}_{PLATFORM_CN.get(pl, pl)}回答{suffix}.md")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(md)
            print(f"已生成 {path}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
