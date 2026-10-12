"""P0-B 平台调性复核工具（spec ⑪ 复核门）：系统出 reading 先验 → 主 agent 核对语境改判/确认。

分层哲学（与 finalize_sentiment 一致）：系统确定性算数字+初判 reading（可审计可复现），
主 agent 复核 reading 是否与实际回答语境相符（防子 agent 判错 / AI 格式假象导致的误判），
改判留 reason（审计留痕）。成本≈0（只看已有回答，不重问 AI 不扣联网额度）。

用法：
  1. generate：python scripts/review_platform_baseline.py generate <run_id> [out_path]
     → 每平台 系统 reading + 依据数字 + 待核对证据（只答区域题/低列题的回答片段）
  2. apply：python scripts/review_platform_baseline.py apply <run_id> 复核.json
     → 复核.json = {"wenxin": {"reading": "client_content_gap", "reason": "文心实际列了高档酒店但格式未列清单..."}}
     → 改判/确认 reading + 留 reason，backfill 写回（修正解读标签，不重判、不重问）
"""
import argparse
import asyncio
import copy
import json
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import write_measurement
from src.collector.platform_baseline import apply_review, compute_platform_baseline
from src.config import settings
from src.models.collection_run import CollectionRun

PLATFORM_CN = {"deepseek": "DeepSeek", "kimi": "Kimi", "doubao": "豆包", "wenxin": "文心一言"}
_SNIPPET_LEN = 90


def _evidence_for(measurement: dict, pl: str):
    """待核对证据：只答区域题（hotels 空，判定过）与低列题（1-2 家）的回答片段——
    主 agent 据此分辨"真平台风格"vs"AI 格式假象（推荐区域/未列清单）"。
    """
    info = measurement.get("platforms", {}).get(pl, {})
    zero, low = [], []
    for j in info.get("judgments", []):
        if j.get("layer") == "attribution" or j.get("reason") == "error" or j.get("recommendation") is None:
            continue
        hotels = j.get("hotels_recommended") or []
        n = len(hotels)
        if n == 0:
            zero.append(j)
        elif n <= 2:
            low.append(j)
    def _snip(j):
        return (j.get("answer") or "").replace("\n", " ")[:_SNIPPET_LEN]
    return [
        {"question": j.get("question"), "answer": _snip(j)} for j in zero
    ], [
        {"question": j.get("question"), "n_hotels": len(j.get("hotels_recommended") or []),
         "hotels": (j.get("hotels_recommended") or [])[:3], "answer": _snip(j)} for j in low
    ]


def _competitor_gap_evidence(measurement: dict, pl: str):
    """关键判别证据（对抗审查 MED）：逐题「国际五星竞对被推、甲方未推荐」——
    平台愿意推甲方档位（竞对进名单）但不推甲方 = 内容不足；竞对也没进 = 结构性。
    读 competitor_visibility.question_detail（P0-A 已聚合）。"""
    qd = measurement.get("competitor_visibility", {}).get("question_detail", [])
    return [
        {"question": d.get("question"), "main_in": d.get("main_in") or []}
        for d in qd
        if d.get("platform") == pl and not d.get("client_recommend") and (d.get("main_in") or [])
    ]


def render_checklist(measurement: dict, baseline: dict, run_id: str) -> str:
    brand, city = measurement.get("brand", "品牌"), measurement.get("city", "城市")
    lines = [
        f"# {city}{brand} 平台调性复核清单（P0-B 复核门）",
        "",
        f"- collection_run：{run_id}",
        "- 系统 reading = 先验；主 agent 核对语境后改判/确认，apply 留 reason",
        "",
    ]
    def _pct(v):
        return f"{v * 100:.0f}%" if v is not None else "—"   # 数据不足态（tier_unknown/no_band_data）为 None
    for pl, b in baseline.items():
        zero, low = _evidence_for(measurement, pl)
        lines += [
            f"## {PLATFORM_CN.get(pl, pl)} —— 系统判：{b['reading']}",
            "",
            f"- 平均列 {b['avg_hotels_listed']:.1f} 家 | 甲方档位占比 {_pct(b['high_end_ratio'])} | "
            f"甲方命中 {b['hit_rate'] * 100:.0f}% | 国际五星竞对 {_pct(b['main_band_avg_rate'])}",
            f"- 解读：{b['note']}",
        ]
        if zero:
            lines.append(f"- **只答区域题（0 家，{len(zero)} 题）**——核「少列」是真风格还是格式假象：")
            for e in zero[:4]:
                lines.append(f"  · {e['question']} → 「{e['answer']}」")
        if low:
            lines.append(f"- **低列题（1-2 家，{len(low)} 题）**：")
            for e in low[:4]:
                lines.append(f"  · {e['question']}（{e['n_hotels']} 家：{'/'.join(e['hotels'])}）→ 「{e['answer']}」")
        # 对抗审查 MED：client_content_gap vs structural 的关键判别证据——
        # 逐题列出「国际五星竞对被推、甲方未推荐」的题（平台愿意推甲方档位但不推甲方 = 内容不足；反之结构性）
        gap_qs = _competitor_gap_evidence(measurement, pl)
        if gap_qs:
            lines.append(f"- **竞对被推、甲方未推荐（{len(gap_qs)} 题）**——核「内容不足 vs 结构性」的关键判别：")
            for e in gap_qs[:5]:
                lines.append(f"  · {e['question']} → 竞对在：{'、'.join(e['main_in'])}（甲方未上榜）")
        review = b.get("review")
        if review:
            st = "改判" if review["status"] == "revised" else "确认"
            stale = " ⚠️重判后可能过期" if review.get("stale") else ""
            lines.append(f"- 复核记录：{st} → {review['reviewed_reading']}（系统先验 {review['system_reading']}）"
                         f" reviewer={review['reviewer']} {review['reviewed_at']} reason={review['reason']}{stale}")
        lines.append("")
    return "\n".join(lines)


async def main():
    p = argparse.ArgumentParser(description="P0-B 平台调性复核（generate 清单 / apply 改判）")
    p.add_argument("mode", choices=["generate", "apply"])
    p.add_argument("run_id")
    p.add_argument("arg3", nargs="?", help="generate: 输出路径(可选)；apply: 复核 JSON 路径")
    p.add_argument("--reviewer", default="main_agent", help="复核人身份（审计留痕）")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        # 完全独立深拷贝（JSONB 列只有"重新赋值"才触发持久化；浅拷贝共享嵌套 dict 的原地改会丢变更）
        m = copy.deepcopy(run.measurement_json or {})
        client_tier = (run.positioning_json or {}).get("tier")
        baseline = m.get("platform_baseline") or compute_platform_baseline(m, client_tier)

        if args.mode == "generate":
            checklist = render_checklist(m, baseline, args.run_id)
            print(checklist)
            if args.arg3 and not args.arg3.startswith("-"):
                with open(args.arg3, "w", encoding="utf-8") as fh:
                    fh.write(checklist)
                print(f"\n已导出 {args.arg3}")
            await engine.dispose()
            return

        # apply
        patch_path = args.arg3
        if not patch_path:
            print("用法: review_platform_baseline.py apply <run_id> <复核.json>")
            await engine.dispose()
            sys.exit(1)
        with open(patch_path, encoding="utf-8") as fh:
            patch = json.load(fh)
        apply_review(baseline, patch, reviewer=args.reviewer)
        m["platform_baseline"] = baseline
        await write_measurement(db, args.run_id, m, snapshot_type="backfill")
        await db.commit()
        print("已复核并写回（backfill 修正解读标签）：")
        for pl, b in baseline.items():
            rv = b.get("review")
            if rv:
                st = "改判" if rv["status"] == "revised" else "确认"
                print(f"  [{pl}] {st} → {rv['reviewed_reading']}（系统先验 {rv['system_reading']}）reason={rv['reason']}")
        print("\n注意：复核是解读标签修正，不重判不重问 AI；若后续 rejudge 会重算系统 reading，需重复核。")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
