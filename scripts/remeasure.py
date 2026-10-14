"""复测收敛：单轮分层采集原语（spec 复测收敛设计，2026-09-15 定稿，B 模式）。

用法：
  python scripts/remeasure.py <品牌> <城市> <run_id> --round 1
  python scripts/remeasure.py <品牌> <城市> <run_id> --round 2

每轮 = 同基线上（同指纹、不新开 run）分层采集 → 按 qid 合并进 measurement（保留未采集层的旧判定）
→ 写 draft（不开快照）。判定（子 agent + G1-G5）由主 agent 在轮间完成，之后 `finalize_v4 seal`
生成该轮 rejudge 快照（converge.py 按 measurement_json.round_no 读取同周期轮次）。

分层（设计定稿，用户 2026-09-15 拍板）：
  round 1：4 平台全量 35 题（命中 25 + 归因 10）
  round 2/3：豆包/文心 全量 35；DeepSeek/Kimi 仅归因 10（命中层沿用第 1 轮）

指纹恒用 `build_platform_questions` 全 35 题算（不随采集子集变）→ 同基线复用、不误开新 run。
"""
import argparse
import asyncio
import copy
import sys
from datetime import datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.gt_entry import write_measurement
from src.collector.hit_rate import finalize_measurement
from src.collector.measure import build_platform_questions, measure_platform
from src.collector.question_builder import fingerprint
from src.collector.rate_limiter import build_rate_limiters
from src.config import settings
from src.models.collection_run import CollectionRun
from scripts.run_measure import (
    PLATFORM_ADAPTERS, _find_run, _resolve_measure_target, check_positioning_freshness,
    find_brand_en, make_ask_fn,
)

ALL = ("hit", "attribution")
ROUND_LAYERS = {
    1: {"deepseek": ALL, "kimi": ALL, "doubao": ALL, "wenxin": ALL},
    2: {"deepseek": ("attribution",), "kimi": ("attribution",), "doubao": ALL, "wenxin": ALL},
    3: {"deepseek": ("attribution",), "kimi": ("attribution",), "doubao": ALL, "wenxin": ALL},
}


def merge_round_measurements(existing, results, layers, round_no, fp, now) -> dict:
    """本轮采集结果 → 合并进 measurement（按 qid 替换采集层，保留未采集层旧判定）。

    分层（稳定平台只采归因层）：round 2/3 里 DS/Kimi 的命中层判定必须沿用第 1 轮，
    只有本轮采集层（attribution）的 qid 被新 judgment 替换。
    """
    m = copy.deepcopy(existing or {})
    platforms = m.setdefault("platforms", {})
    for p, r in results.items():
        new_js = r["judgments"]
        layer_set = set(layers[p])
        new_ids = {j["question_id"] for j in new_js}
        old = (platforms.get(p) or {}).get("judgments", [])
        keep = [j for j in old
                if j.get("layer") not in layer_set and j["question_id"] not in new_ids]
        platforms[p] = {"judgments": keep + new_js, "collected_at": now}
    m["collected_at"] = now
    m["round_no"] = round_no
    m["question_fingerprint"] = fp
    # 本轮各平台实际采集层（稳定平台轮2/3 只采归因，命中层沿用轮1）——
    # converge L1 据此只统计真正重采过命中层的轮次，防复制数据被当独立样本拉虚 CI（2026-09-16 对抗审查）
    m["collected_layers"] = {p: sorted(set(layers[p])) for p in results}
    m["agent_notes"] = list({v["agent_notes"] for v in results.values() if v.get("agent_notes")})
    return m


async def main():
    p = argparse.ArgumentParser(description="复测收敛：单轮分层采集（B 模式）")
    p.add_argument("brand")
    p.add_argument("city")
    p.add_argument("run_id")
    p.add_argument("--round", type=int, required=True, help="1-3")
    args = p.parse_args()
    if args.round not in ROUND_LAYERS:
        print(f"错误: round 必须是 {sorted(ROUND_LAYERS)}（B 模式上限 3）")
        sys.exit(1)
    layers = ROUND_LAYERS[args.round]

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        run = await _find_run(db, args.brand, args.city, args.run_id)
        if run is None:
            print(f"错误: 找不到 {args.brand} {args.city} 的 collection_run（先跑 run_gt_diagnosis）")
            await engine.dispose()
            sys.exit(1)
        positioning = run.positioning_json or {}
        existing = run.measurement_json or {}
        run_id_str = str(run.id)
    if not check_positioning_freshness(positioning):
        await engine.dispose()
        sys.exit(1)
    brand_en = find_brand_en(args.brand)

    system = (existing or {}).get("system", "A")   # 提问体系随 run（A/B），复算指纹须一致
    full_questions = build_platform_questions(args.brand, args.city, positioning, system=system)
    current_fp = fingerprint(full_questions)
    print(f"[round {args.round}] 分层: " + ", ".join(f"{pl}:{'/'.join(L)}" for pl, L in layers.items())
          + f"（全量指纹 {len(current_fp)} 题）")

    async with session_factory() as db:
        run_row = await db.get(CollectionRun, run_id_str)
        target_run_id, is_new = await _resolve_measure_target(db, run_row, current_fp)
        if is_new:
            print("⚠️ 警告: 指纹未匹配现有基线 → 新开 run（问法可能已变）。收敛应在同基线内进行。")

        limiters = build_rate_limiters(list(layers))
        results = {}
        for pl, layer_set in layers.items():
            adapter = PLATFORM_ADAPTERS[pl]()
            results[pl] = await measure_platform(
                args.brand, args.city, brand_en, positioning,
                make_ask_fn(adapter, limiters[pl]), platform=pl, layers=set(layer_set), system=system)
        now = datetime.now().isoformat(timespec="seconds")
        measurement = merge_round_measurements(existing, results, layers, args.round, current_fp, now)
        remaining = finalize_measurement(measurement)
        await write_measurement(db, target_run_id, measurement, snapshot_type="draft")
        await db.commit()
        counts = {pl: len(measurement["platforms"][pl]["judgments"]) for pl in layers}
        print(f"已写 draft（run {target_run_id[:8]}）round {args.round}；待判 {remaining} 题；"
              f"各平台题数 {counts}")
        print("→ 主 agent 判定该轮（子 agent + G1-G5），再 finalize_v4 seal 生成该轮快照")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
