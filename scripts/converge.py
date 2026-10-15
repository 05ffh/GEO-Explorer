"""复测收敛聚合（spec 复测收敛设计，2026-09-15 定稿）。

读同基线 run 的各轮（measurement_json.round_no）sealed 快照 → 计算并写 `measurement_json["convergence"]`：
  - L1 命中率：每题 k/R → 平台均值 ± 区间（二项近似）+ 跨轮 spread
  - L2 劣势维度：跨（平台×轮）合并出现率 + 平台分布 + 稳定/模糊/未现（合并口径，用户 2026-09-15 拍板）
  - L3 漂移：首轮 vs 末轮命中率差 > 2×CI → 标记
  - 停止判据：不动点（连续两次稳定集合相同且模糊为空）/ 波动平台 CI 达标 / R_max（默认 3）
  - 稳定性等级：converged / partial / unstable（G4 翻转率 >20%）

产物 = 落库活数据字段（非 sealed，快照仍是原始来源可续算）+ 报告 md。

用法：
  python scripts/converge.py <run_id> [--out ./output]
"""
import argparse
import asyncio
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot

RECOMMEND = "recommend"
LAYER_HIT = "hit"
LAYER_ATTRIBUTION = "attribution"
TYPE_TRUE = "true_disadvantage"
TYPE_UNREF = "client_has_unreferenced"


def _hit_valid(j: dict) -> bool:
    return (j.get("layer") == LAYER_HIT and j.get("has_hotel_recommendations")
            and j.get("recommendation") is not None and j.get("reason") != "error")


def _round_platform_rates(m: dict) -> dict:
    """单轮各平台命中率（直接由 judgment 算，不信任历史 platform_rate）。

    分层（2026-09-16 对抗审查）：稳定平台（DS/Kimi）轮 2/3 只采归因层、命中层沿用轮 1，
    `collected_layers` 缺失该平台命中层 → 该轮不计（否则轮 1 命中数据被复制计为独立轮次，
    拉虚 CI / spread）。旧数据（V5 v3 等无 collected_layers）默认全层已采。
    """
    out = {}
    for pl, info in m.get("platforms", {}).items():
        cl = (m.get("collected_layers") or {}).get(pl)
        if cl is not None and "hit" not in cl:
            continue
        js = [j for j in info.get("judgments", []) if _hit_valid(j)]
        if not js:
            continue
        hits = sum(1 for j in js if j["recommendation"] == RECOMMEND)
        out[pl] = round(hits / len(js), 4)
    return out


def _attribution_decisions(rounds: list[dict], stable_ratio: float = 2 / 3,
                           absent_ratio: float = 1 / 3, min_obs: int = 2) -> dict:
    """跨（平台×轮）合并归因劣势：每 (qid,dim) 的 type 分布 + 平台分布 + 稳定/未现/模糊。

    合并口径（用户 2026-09-15 拍板）：四平台合并计出现率，并标注平台分布暴露特异性。
    分母 = 该题的**总判定次数**（有 attribution_result 的平台×轮）——不是"出现的次数"，
    否则只出现 1 次的维度也会被当成 100% 稳定（对抗审查 2026-09-15 修）。
    稳定 = 主导 type 占比 ≥2/3 且出现 ≥min_obs（多次一致才采信）；未现 = 占比 ≤1/3；其余模糊。
    """
    qid_obs = defaultdict(int)                       # qid -> 判定次数（有 attribution_result 的平台×轮）
    obs = defaultdict(lambda: defaultdict(int))      # (qid,dim) -> type -> count
    obs_pl = defaultdict(lambda: defaultdict(set))   # (qid,dim) -> type -> platforms
    for m in rounds:
        for pl, info in m.get("platforms", {}).items():
            for j in info.get("judgments", []):
                if j.get("layer") != LAYER_ATTRIBUTION:
                    continue
                r = j.get("attribution_result") or {}
                if not r:
                    continue
                qid_obs[j["question_id"]] += 1
                # 每次判定内按 dim 去重（2026-09-16 对抗审查）：同一题同维度判多条劣势
                # （如"泳池旧"+"健身房旧"都记设施 true）逐条计会分子>分母（占比>1），
                # 语义是"该维度是否出现"的 0/1，不是条目数——同判定同 dim 只计一次 type。
                seen_dims = set()
                for d in r.get("client_disadvantage_dims", []):
                    dim = d["dim"]
                    if dim in seen_dims:
                        continue
                    seen_dims.add(dim)
                    k = (j["question_id"], dim)
                    obs[k][d["type"]] += 1
                    obs_pl[k][d["type"]].add(pl)
    decisions = {}
    for (qid, dim), counts in obs.items():
        denom = qid_obs[qid]
        if denom <= 0:
            continue
        best_type, best_n = max(counts.items(), key=lambda x: x[1])
        ratio = best_n / denom
        if ratio >= stable_ratio and best_n >= min_obs:
            status = "stable"
        elif ratio <= absent_ratio:
            status = "absent"
        else:
            status = "ambiguous"
        decisions[(qid, dim)] = {
            "question_id": qid,
            "dim": dim,
            "types": dict(counts),
            "denom": denom,
            "best_type": best_type,
            "best_count": best_n,
            "best_ratio": round(ratio, 3),
            "status": status,
            "platforms": {t: sorted(s) for t, s in obs_pl[(qid, dim)].items()},
        }
    return decisions


def _hit_flip_rate(rounds: list[dict]) -> float:
    """命中层 recommendation 跨轮翻转率：甲方「被推荐↔未被推荐」跨轮翻转的题占比。

    这是"AI 对预设问题的回答结论会不会翻转"的直接度量（2026-09-16 用户拍板：收敛 = 结论不翻转，
    而非 CI 精度）。二值化：recommend=命中，mention/exclude/absent=未命中；某 (平台×题) 的
    二值序列跨相邻轮出现变化 → 该题"翻转"。只统计真正重采过命中层的轮次（collected_layers），
    稳定平台（DS/Kimi）轮 2/3 沿用的复制命中不计（否则假翻转率被复制数据稀释）。
    """
    seq = defaultdict(list)  # (pl, qid) -> [(round_idx, is_hit)]
    for round_idx, m in enumerate(rounds):
        for pl, info in m.get("platforms", {}).items():
            cl = (m.get("collected_layers") or {}).get(pl)
            if cl is not None and "hit" not in cl:
                continue
            for j in info.get("judgments", []):
                if not _hit_valid(j):
                    continue
                seq[(pl, j["question_id"])].append((round_idx, j["recommendation"] == RECOMMEND))
    flipped = observed = 0
    for key, s in seq.items():
        s.sort()
        vals = [h for _, h in s]
        if len(vals) < 2:
            continue
        observed += 1
        if any(a != b for a, b in zip(vals, vals[1:])):
            flipped += 1
    return round(flipped / observed, 3) if observed else 0.0


def compute_convergence(rounds: list[dict], ci_z: float = 1.96, stable_ratio: float = 2 / 3,
                        ci_target: float = 0.10, flip_gate: float = 0.20,
                        hit_flip_gate: float = 0.20, r_max: int = 3) -> dict:
    """纯函数：把各轮 measurement 聚合成收敛判定。rounds = [measurement_json, ...]（每轮一个）。

    收敛判据（2026-09-16 重构，用户拍板：结论稳定性导向）：
      - unstable：归因翻转率 > flip_gate 或 命中翻转率 > hit_flip_gate——回答结论翻转过多，
        判定协议不可信/测量对象本身不稳定（继续测无意义）。
      - converged：翻转率均达标 且 L2 稳定集合达到不动点（连续两轮稳定集合相同）——
        结论不再随额外采样变化，可见度结论可交付。
      - partial：其余（结论还不够稳，需更多轮）。
    CI 达标（ci_met）降级为辅助标注（报告展示精度，不阻塞收敛判定）——±10pp 在 p≈0.5 时
    25 题×3 轮物理不可达（极限 ±11.3pp），不能作为收敛闸门。
    """
    platforms = sorted({pl for m in rounds for pl in m.get("platforms", {})})
    round_rates = [_round_platform_rates(m) for m in rounds]

    # ---- L1 命中率（每题 pooled，只统计真正重采过命中层的轮次，防复制样本拉虚 CI）----
    per_q = {pl: defaultdict(lambda: {"hit": 0, "samples": 0}) for pl in platforms}
    for m in rounds:
        for pl, info in m.get("platforms", {}).items():
            cl = (m.get("collected_layers") or {}).get(pl)
            if cl is not None and "hit" not in cl:
                continue
            for j in info.get("judgments", []):
                if not _hit_valid(j):
                    continue
                d = per_q[pl][j["question_id"]]
                d["samples"] += 1
                d["hit"] += 1 if j["recommendation"] == RECOMMEND else 0
    hit = {}
    for pl in platforms:
        d = per_q[pl]
        samples = sum(x["samples"] for x in d.values())
        hits = sum(x["hit"] for x in d.values())
        p = hits / samples if samples else None
        ci = ci_z * math.sqrt(p * (1 - p) / samples) if (samples and p is not None) else None
        rr = [r[pl] for r in round_rates if pl in r]
        spread = (max(rr) - min(rr)) if len(rr) > 1 else 0.0
        hit[pl] = {
            "rounds": len(rr),
            "hit_rate": round(p, 4) if p is not None else None,
            "ci_half": round(ci, 4) if ci is not None else None,
            "samples": samples,
            "spread": round(spread, 4),
            "round_rates": rr,
            "per_question": {
                q: (round(x["hit"] / x["samples"], 3), x["samples"])
                for q, x in d.items() if x["samples"]
            },
        }
    rates = [hit[pl]["hit_rate"] for pl in platforms if hit[pl]["hit_rate"] is not None]
    overall_rate = round(sum(rates) / len(rates), 4) if rates else None
    cis = [hit[pl]["ci_half"] for pl in platforms if hit[pl]["ci_half"] is not None]
    overall_ci = round(sum(cis) / len(cis), 4) if cis else None

    # ---- L2 劣势维度 ----
    decisions = _attribution_decisions(rounds)
    stable = [d for d in decisions.values() if d["status"] == "stable"]
    ambiguous = [d for d in decisions.values() if d["status"] == "ambiguous"]
    absent = [d for d in decisions.values() if d["status"] == "absent"]

    def _by_dim(ds):
        out = defaultdict(list)
        for d in ds:
            out[d["dim"]].append(d)
        return dict(out)

    decision_sets = {
        "client_has_unreferenced": _by_dim([d for d in stable if d["best_type"] == TYPE_UNREF]),
        "true_disadvantage": _by_dim([d for d in stable if d["best_type"] == TYPE_TRUE]),
        "ambiguous": ambiguous,
        "absent": absent,
    }
    flips = [(k, d) for k, d in decisions.items() if len(d["types"]) > 1 and d["status"] == "ambiguous"]
    flip_rate = round(len(flips) / len(decisions), 3) if decisions else 0.0

    # ---- L3 漂移 ----
    drift = {}
    for pl in platforms:
        rr = [r[pl] for r in round_rates if pl in r]
        if len(rr) >= 2:
            first, last = rr[0], rr[-1]
            ci = hit[pl]["ci_half"]
            drift[pl] = {
                "first_rate": first, "last_rate": last, "diff": round(last - first, 4),
                "flag": bool(ci is not None and abs(last - first) > 2 * ci),
            }
        else:
            drift[pl] = {"first_rate": rr[0] if rr else None, "last_rate": rr[0] if rr else None,
                         "diff": 0.0, "flag": False, "note": "单轮（稳定平台）"}

    # ---- 停止判据 ----
    def _snap(n):
        if n < 1:
            return None
        ds = _attribution_decisions(rounds[:n])
        return frozenset((d["question_id"], d["dim"], d["best_type"])
                         for d in ds.values() if d["status"] == "stable")

    snap_prev, snap_cur = _snap(len(rounds) - 1), _snap(len(rounds))
    fixed_point = snap_prev is not None and snap_prev == snap_cur
    remeasured = [pl for pl in platforms if hit[pl]["rounds"] >= 2]
    ci_met = all(hit[pl]["ci_half"] is not None and hit[pl]["ci_half"] <= ci_target
                 for pl in remeasured) if remeasured else True
    r_max_reached = len(rounds) >= r_max

    hit_flip_rate = _hit_flip_rate(rounds)
    if flip_rate > flip_gate or hit_flip_rate > hit_flip_gate:
        verdict = "unstable"
    elif fixed_point:
        verdict = "converged"
    else:
        verdict = "partial"

    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "rounds": len(rounds),
        "r_max": r_max,
        "r_max_reached": r_max_reached,
        "overall_hit_rate": overall_rate,
        "overall_ci_half": overall_ci,
        "platforms_hit_rate": hit,
        "attribution_keys": len(decisions),
        "decision_sets": decision_sets,
        "flip_rate": flip_rate,
        "hit_flip_rate": hit_flip_rate,
        "flips": [{"question_id": qid, "dim": dim, "types": d["types"]} for (qid, dim), d in flips],
        "drift": drift,
        "stop": {"fixed_point": bool(fixed_point), "ci_met": bool(ci_met), "verdict": verdict},
    }


def render_md(run: CollectionRun, conv: dict) -> str:
    brand, city = run.measurement_json.get("brand", "品牌"), run.city or "城市"
    lines = [
        f"# {city}{brand} 复测收敛报告（spec P0-E）",
        "",
        f"- 轮次：{conv['rounds']}（R_max {conv['r_max']}，{'已达' if conv['r_max_reached'] else '未达'}）",
        f"- 稳定性等级：**{conv['stop']['verdict']}**"
        f"（不动点 {'✓' if conv['stop']['fixed_point'] else '✗'} / 归因翻转率 {conv['flip_rate']}"
        f" / 命中翻转率 {conv.get('hit_flip_rate')} / CI 达标(辅助) "
        f"{'✓' if conv['stop']['ci_met'] else '✗'}）",
        f"- 整体命中率：{conv['overall_hit_rate']} ± {conv['overall_ci_half']}",
        "",
        "## L1 命中率（均值 ± CI）",
        "",
        "| 平台 | 轮次 | 命中率 | CI 半宽 | 跨轮 spread |",
        "|---|---|---|---|---|",
    ]
    for pl, h in conv["platforms_hit_rate"].items():
        lines.append(f"| {pl} | {h['rounds']} | {h['hit_rate']} | {h['ci_half']} | {h['spread']} |")
    lines += ["", "## L2 劣势维度（四平台合并 + 平台分布，稳定=主导≥2/3 且出现≥2）", ""]
    lines.append(f"- 未现（≤1/3，未成信号）：{len(conv['decision_sets']['absent'])} 条")
    for label, cn in (("甲方有未引用（→铺内容）", TYPE_UNREF), ("真劣势（→对标竞对）", TYPE_TRUE)):
        grouped = conv["decision_sets"][cn]
        if not grouped:
            continue
        lines.append(f"### {label}")
        for dim, items in grouped.items():
            for d in items:
                pl = d["platforms"].get(d["best_type"], [])
                lines.append(f"- {d['question_id']} · **{dim}**（出现 {d['best_count']}/{d['denom']}，"
                             f"占比 {d['best_ratio']}，平台 {','.join(pl)}）")
    if conv["decision_sets"]["ambiguous"]:
        lines += ["### 存疑（翻转/未达稳定，需主 agent 仲裁）"]
        for d in conv["decision_sets"]["ambiguous"]:
            lines.append(f"- {d['question_id']} · **{d['dim']}**（{d['types']}，平台 {d['platforms']}）")
    if conv["flips"]:
        lines += ["", "### 判定翻转（G3 仲裁对象）"]
        for f in conv["flips"]:
            lines.append(f"- {f['question_id']} · {f['dim']}（{f['types']}）")
    lines += ["", "## L3 漂移", ""]
    for pl, dr in conv["drift"].items():
        flag = " ⚠️ 漂移" if dr["flag"] else ""
        lines.append(f"- {pl}: 首 {dr['first_rate']} → 末 {dr['last_rate']}（差 {dr['diff']}）{flag}")
    lines += ["", "## 停止判定", ""]
    lines.append(f"> **{conv['stop']['verdict']}** —— 不动点：{'✓' if conv['stop']['fixed_point'] else '✗'}"
                 f"；归因翻转率 {conv['flip_rate']} / 命中翻转率 {conv.get('hit_flip_rate')}"
                 f"（>0.2 视为回答结论翻转过多，协议不可信）"
                 f"；CI 达标（辅助标注，不阻塞收敛）{'✓' if conv['stop']['ci_met'] else '✗'}")
    return "\n".join(lines)


async def main():
    p = argparse.ArgumentParser(description="复测收敛聚合")
    p.add_argument("run_id")
    p.add_argument("--out", default="./output")
    p.add_argument("--r-max", type=int, default=3)
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        run = await db.get(CollectionRun, args.run_id)
        if run is None:
            print(f"错误: collection_run {args.run_id} 不存在")
            await engine.dispose()
            sys.exit(1)
        snaps = (
            await db.execute(
                select(MeasurementSnapshot)
                .where(MeasurementSnapshot.collection_run_id == args.run_id)
                .order_by(MeasurementSnapshot.snapshot_no)
            )
        ).scalars().all()
        # 按 round_no 分组，每轮取最新快照
        by_round = {}
        skipped = []
        for s in snaps:
            rn = (s.measurement_json or {}).get("round_no")
            if rn is None:
                skipped.append(s.snapshot_no)
                continue
            if rn not in by_round or s.snapshot_no > by_round[rn].snapshot_no:
                by_round[rn] = s
        if skipped:
            print(f"提示: 跳过 {len(skipped)} 个无 round_no 标记的快照"
                  f"（snapshot_no={skipped}）——非收敛轮次，不入统计")
        if not by_round:
            print("错误: 该 run 无 round_no 标记的快照（先跑 remeasure.py --round N + seal）")
            await engine.dispose()
            sys.exit(1)
        rounds = [by_round[rn].measurement_json for rn in sorted(by_round)]
        conv = compute_convergence(rounds, r_max=args.r_max)
        # 落库活数据字段（非 sealed）
        m = dict(run.measurement_json or {})
        m["convergence"] = conv
        run.measurement_json = m
        await db.commit()
        print(json.dumps({k: conv[k] for k in ("rounds", "overall_hit_rate", "overall_ci_half", "stop")},
                         ensure_ascii=False, indent=1))
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, f"{run.city or ''}{m.get('brand','品牌')}_复测收敛.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_md(run, conv))
        print(f"已写 measurement_json['convergence'] + 报告 {path}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
