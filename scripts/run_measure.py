"""P3 诊断入口（测量段）：读定位 → 提问 → 命中判定 → 四切面 → 落库 → 介入点清单。

用法：
  python scripts/run_measure.py <品牌名> <城市> [collection_run_id]
  python scripts/run_measure.py <品牌名> <城市> [collection_run_id] --platforms doubao   # 补测

落库 measurement_json 标 status=partial（题待子 agent 判六字段），
子 agent 判完用 finalize_hit --apply 回填（recommendation/scene 等六字段）后改 status=complete。

--platforms 子集 = 补测：只替换目标平台的 judgments，其他平台（含主 agent 已判内容）原样保留，
status 由 finalize_measurement 重判（仍存 needs_agent → partial）。

问法基线变更（spec 11.9 基线变更模式）：每次测量记录 question_fingerprint（问法集指纹）；
与现有 run 最新指纹不同（问法集变更，如题目净化/甲方指定问法）→ 自动新开 run 行并复制
P2（定位/舆情），新基线独立可自消费 P2；指纹相同（同基线复测/补测）→ 同 run 快照累积。
"""
import argparse
import asyncio
import copy
import json
import sys
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.adapters import DeepSeekAdapter, KimiAdapter, WenxinAdapter, DoubaoAdapter
from src.collector.ai_hotels import extract_hotels
from src.collector.gt_entry import write_measurement
from src.collector.hit_rate import finalize_measurement
from src.collector.measure import measure_platform
from src.collector.question_builder import fingerprint
from src.collector.rate_limiter import build_rate_limiters
from src.collector.tier import derive_tier
from src.config import settings
from src.industry_knowledge.loader import get_knowledge_loader
from src.models.brand import Brand
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot

PLATFORM_ADAPTERS = {
    "deepseek": DeepSeekAdapter,
    "kimi": KimiAdapter,
    "wenxin": WenxinAdapter,
    "doubao": DoubaoAdapter,
}


def make_ask_fn(adapter, limiter):
    """把真实 adapter + 限流包装成 measure 需要的 ask_fn(question)->answer_text。

    semaphore = 限流并发数，控制同时提问数——避免 measure 并发 35 题（25 命中 + 10 归因）时全挤排队超时。
    """
    max_concurrent = limiter.config.max_concurrent if limiter.config.max_concurrent > 0 else 1
    sem = asyncio.Semaphore(max_concurrent)

    async def ask_fn(question):
        async with sem:
            if not await limiter.acquire_or_wait(120):
                raise TimeoutError(f"[{adapter.platform_name}] 限流预算耗尽")
            try:
                resp = await adapter.query(question)
                if resp.error_code:
                    limiter.on_rate_limit()
                    raise RuntimeError(f"[{adapter.platform_name}] 提问失败 {resp.error_code}: {(resp.error_message or '')[:80]}")
                limiter.on_success()
                return resp.answer_text or ""
            finally:
                limiter.release()
    return ask_fn


def find_brand_en(brand_zh: str) -> str | None:
    """从 brand_domains 查英文名（命中判定别名）。表外返回 None。

    统一 lowercase（与 run_gt_diagnosis.find_brand_en 一致）：URL 认领/匹配前一律小写。
    """
    for item in get_knowledge_loader().load_category("brand_domains"):
        if item.get("zh") == brand_zh:
            return (item.get("en") or "").lower() or None
    return None


# 酒旅定位字段（tier/星级/竞品/ADR 带）月级稳定，定位超 30 天才建议刷新
POSITIONING_FRESH_DAYS = 30


def check_positioning_freshness(positioning: dict) -> bool:
    """校验定位新鲜度（强制）：positioned_at 缺失或 >30 天 → 拒绝测量，强制先跑 P2。

    定位是 P3 测量的前置（tier/competitors 决定题目），P3 不能跳过 P2 复用旧定位。
    返回 True（新鲜可用）/ False（过时/缺失，应退出）。
    """
    positioned_at = positioning.get("positioned_at")
    if not positioned_at:
        print("错误: positioning_json 未标注定位时间（旧数据或主 agent 手填）。请先跑 P2: python scripts/run_gt_diagnosis.py <品牌> <城市>")
        return False
    try:
        age_days = (datetime.now() - datetime.fromisoformat(positioned_at)).total_seconds() / 86400
        if age_days > POSITIONING_FRESH_DAYS:
            print(f"错误: 定位时间 {positioned_at}（{age_days:.0f} 天前），超过 {POSITIONING_FRESH_DAYS} 天。请重跑 P2 刷新定位")
            return False
        print(f"定位时间: {positioned_at}（{age_days:.0f} 天前，新鲜）")
        return True
    except ValueError:
        print(f"错误: positioned_at 格式无法解析（{positioned_at}），无法判断新鲜度")
        return False


async def _find_run(db, brand: str, city: str, run_id: str | None):
    if run_id:
        run = await db.get(CollectionRun, run_id)
        if run is None:
            return None
        # 显式 run_id 也校验品牌/城市一致（防误传跨单元 run 导致 P2 错配：
        # 换品牌/换城市 = 新诊断单元 = P2 需重建，不能用别的单元的定位/舆情测）
        brand_row = (await db.execute(select(Brand).where(Brand.name == brand))).scalar_one_or_none()
        if brand_row is None or run.brand_id != brand_row.id or run.city != city:
            print(f"错误: 指定 run {str(run.id)[:8]} 属于 {run.city}，与请求 {brand}/{city} 不一致（换品牌/城市需先跑 run_gt_diagnosis 重建 P2）")
            return None
        return run
    brand_row = (await db.execute(select(Brand).where(Brand.name == brand))).scalar_one_or_none()
    if brand_row is None:
        return None
    # 优先找有定位结果的 run（positioning_json 非空）；否则最新 run 兜底
    run = (await db.execute(
        select(CollectionRun)
        .where(CollectionRun.brand_id == brand_row.id, CollectionRun.city == city,
               CollectionRun.positioning_json != {})
        .order_by(CollectionRun.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if run is not None:
        return run
    return (await db.execute(
        select(CollectionRun)
        .where(CollectionRun.brand_id == brand_row.id, CollectionRun.city == city)
        .order_by(CollectionRun.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()


def _remeasure_merge(existing: dict, platform_results: dict, platforms: list) -> dict:
    """补测合并：只替换目标平台的 judgments，其他平台原样保留。

    主 agent 回填存在各平台 judgments 里，保留即不覆盖已判内容。
    platform_rate / agent_tasks / status 不在此处理，由 finalize_measurement
    从 judgments 单一来源重建，避免残留已判题。
    """
    m = dict(existing or {})
    m.setdefault("platforms", {})
    now = datetime.now().isoformat(timespec="seconds")
    for p in platforms:
        m["platforms"][p] = {"judgments": platform_results[p]["judgments"], "collected_at": now}
    m["agent_notes"] = list({v["agent_notes"] for v in platform_results.values() if v["agent_notes"]})
    m["collected_at"] = now
    # 竞对相对可见度是已判 judgment 的派生字段：补测替换了目标平台 judgment（未判），
    # 旧的 competitor_visibility 会 stale → 清掉，待 finalize_hit --apply 判定后重算（P0-A 主链路挂点）
    m.pop("competitor_visibility", None)
    return m


def _should_new_baseline(latest_fp: list | None, current_fp: list) -> bool:
    """基线变更判断：现有基线无指纹（旧数据）→ 保守复用；指纹不同 → 问法集变更 → 新开 run。"""
    return latest_fp is not None and latest_fp != current_fp


async def _latest_fingerprint(db, run_id: str) -> list | None:
    """读 run 最新一次测量的问法指纹（优先最新快照，fallback run 行 measurement_json）。"""
    snap = (await db.execute(
        select(MeasurementSnapshot)
        .where(MeasurementSnapshot.collection_run_id == run_id)
        .order_by(MeasurementSnapshot.snapshot_no.desc())
        .limit(1)
    )).scalar_one_or_none()
    m = snap.measurement_json if snap is not None else None
    if m is None:
        run = await db.get(CollectionRun, run_id)
        m = run.measurement_json if run is not None else None
    fp = (m or {}).get("question_fingerprint")
    return fp if isinstance(fp, list) else None


async def _clone_run_for_new_baseline(db, old: CollectionRun) -> CollectionRun:
    """问法基线变更 → 新开 run 行 + 完整复制 P2（定位/舆情），真实 run 独立后可自消费 P2。"""
    new = CollectionRun(
        organization_id=old.organization_id,
        brand_id=old.brand_id,
        city=old.city,
        region=old.region,
        collection_status="pending",
    )
    new.positioning_json = copy.deepcopy(old.positioning_json or {})
    new.sentiment_json = copy.deepcopy(old.sentiment_json or {})
    db.add(new)
    await db.flush()
    return new


async def _resolve_measure_target(db, run_row: CollectionRun, current_fp: list) -> tuple[str, bool]:
    """基线解析（spec 11.9 基线变更模式）：扫该品牌+城市所有有定位的 run，
    问法指纹匹配现有基线 → 复用该 run（多基线并行时复测各自的基线，不误开新 run）；
    无匹配 → 现有基线指纹不同则新开 run（复制 P2），旧数据无指纹则保守复用当前 run。
    返回 (target_run_id, is_new_baseline)。"""
    candidates = (await db.execute(
        select(CollectionRun)
        .where(CollectionRun.brand_id == run_row.brand_id,
               CollectionRun.city == run_row.city,
               CollectionRun.positioning_json != {})
        .order_by(CollectionRun.created_at.desc())
    )).scalars().all()
    for cand in candidates:
        if await _latest_fingerprint(db, cand.id) == current_fp:
            return str(cand.id), False
    # 无匹配：旧数据无指纹 → 保守复用（本次写指纹锚）；现有基线指纹不同 → 新开 run
    latest = await _latest_fingerprint(db, run_row.id)
    if not _should_new_baseline(latest, current_fp):
        return str(run_row.id), False
    new_run = await _clone_run_for_new_baseline(db, run_row)
    return str(new_run.id), True


def _build_measurement(brand, city, is_new_baseline, platforms, platform_results, existing_measurement):
    """构造测量 measurement。基线变更 → 新基线第一版只用本次平台（不合并旧基线其他平台，防污染）；
    同基线全量 → 新建快照；同基线补测 → 只替换目标平台。返回 (measurement, snapshot_type)。"""
    if is_new_baseline or set(platforms) == set(PLATFORM_ADAPTERS):
        collected_at = datetime.now().isoformat(timespec="seconds")
        measurement = {
            "brand": brand,
            "city": city,
            "collected_at": collected_at,
            "platforms": {
                p: {"judgments": v["judgments"], "collected_at": collected_at}
                for p, v in platform_results.items()
            },
            "agent_notes": list({v["agent_notes"] for v in platform_results.values()}),
        }
        return measurement, "full"
    return _remeasure_merge(existing_measurement, platform_results, platforms), "remeasure"


async def main(brand: str, city: str, run_id: str | None = None, platforms: list[str] | None = None):
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        run = await _find_run(db, brand, city, run_id)
        if run is None:
            print(f"错误: 找不到 {brand} {city} 的 collection_run（先跑 run_gt_diagnosis 建单元+定位）")
            await engine.dispose()
            sys.exit(1)
        positioning = run.positioning_json or {}
        existing_measurement = run.measurement_json or {}
        run_id_str = str(run.id)
    brand_en = find_brand_en(brand)
    if not check_positioning_freshness(positioning):
        await engine.dispose()
        sys.exit(1)

    if platforms is None:
        platforms = list(PLATFORM_ADAPTERS.keys())
    unknown = set(platforms) - set(PLATFORM_ADAPTERS)
    if unknown:
        print(f"错误: 未知平台 {sorted(unknown)}（可选: {', '.join(PLATFORM_ADAPTERS)}）")
        await engine.dispose()
        sys.exit(1)

    # 并发提问 + 判定（每平台独立 limiter + adapter，gather 并发安全）
    async def _measure_one(p: str):
        adapter = PLATFORM_ADAPTERS[p]()
        result = await measure_platform(brand, city, brand_en, positioning, make_ask_fn(adapter, limiters[p]), platform=p)
        return p, {
            "judgments": result["judgments"],
            "agent_notes": result["agent_notes"],
            "questions": result["questions"],
        }

    limiters = build_rate_limiters(platforms)
    platform_results: dict[str, dict] = dict(await asyncio.gather(*(_measure_one(p) for p in platforms)))

    # 基线变更检测（问法指纹）：指纹相同 → 同 run 快照累积；指纹不同（问法集变更，如题目净化/
    # 甲方指定问法）→ 新开 run 行 + 复制 P2，新基线独立可自消费 P2（spec 11.9 基线变更模式）
    first_questions = next(iter(platform_results.values())).get("questions", [])
    current_fp = fingerprint(first_questions)
    async with session_factory() as db:
        run_row = await db.get(CollectionRun, run_id_str)
        target_run_id, is_new_baseline = await _resolve_measure_target(db, run_row, current_fp)

        # 构造 measurement：基线变更 → 新基线第一版只用本次平台（不合并旧基线其他平台，防污染）；
        # 同基线全量 → 全新建；同基线补测 → 只替换目标平台
        measurement, _ = _build_measurement(
            brand, city, is_new_baseline, platforms, platform_results, existing_measurement)
        if is_new_baseline:
            print(f"\n[问法基线变更] 检测到问法集变化（与现有基线指纹不同）→ 新开 run {target_run_id}，复制 P2（定位/舆情），第一版仅本次测的 {', '.join(platforms)} 平台；后续判定/归因/报告以新 run 为入口")
        elif set(platforms) != set(PLATFORM_ADAPTERS):
            print(f"[补测] 平台 {', '.join(platforms)} 已更新；其他平台结果原样保留（含主 agent 已判内容）")

        remaining = finalize_measurement(measurement)

        if is_new_baseline:
            measurement["baseline_of"] = run_id_str
        measurement["question_fingerprint"] = current_fp
        # 采集=草稿（spec ⑫）：只写 run.measurement_json，不开快照；
        # 全部派生指标（命中率/有效可见度/竞对相对可见度）在判定盖章（finalize_hit --apply →
        # close_measurement）时一次算齐，采集阶段 judgments 未判、派生无意义。
        await write_measurement(db, target_run_id, measurement, snapshot_type="draft")
        await db.commit()

    print(json.dumps({
        "brand": brand, "city": city, "collection_run_id": target_run_id,
        "status": measurement["status"],
        "overall_hit_rate": measurement["overall"]["overall_hit_rate"],
        "platform_hit_rates": measurement["overall"]["platform_hit_rates"],
        "undecided_total": sum(m["platform_rate"]["undecided"] for m in measurement["platforms"].values()),
        "remaining_agent": remaining,
    }, ensure_ascii=False, indent=2))

    # P3a 后：AI 推荐酒店提取 → 可能竞对（候选池补充，供主 agent 复核后 write_competitor 补入）
    all_judgments = [j for pr in platform_results.values() for j in pr["judgments"]]
    ai_reco = extract_hotels(all_judgments, brand, city)
    if ai_reco:
        print("\n=== AI 推荐的可能竞对（P3 命中层回答提取，候选池补充）===")
        for name, info in sorted(ai_reco.items(), key=lambda kv: -kv[1]["cooccurrence"])[:10]:
            t = derive_tier(name, city=city)
            mark = "⚠️ 无档位" if t is None else t
            print(f"  {name}: 同场景共现 {info['cooccurrence']}/{info['mentions']} 次 | 档位={mark}")
        print("  → 同场景共现（与甲方同题被推荐）= AI 实际抢客对象；主 agent 复核后可用")
        print(f"    python scripts/write_competitor.py {target_run_id} '酒店名:圈层:档位:ADR:标准' 补充进竞对")

    print("\n=== 主 agent 介入点清单（P3 测量段）===")
    sc = positioning.get("scenario_competitors") or {}
    print(f"0. 定位状态: tier={'已定' if positioning.get('tier') else '未定'} / 竞品={'有' if positioning.get('competitors') else '无'}"
          f" / 场景竞对={len(sc)} 个场景（tier 未定→命中层 20 题；竞品无→归因层 0 题，归因阶段需补）")
    if positioning.get("competitors") and not sc:
        print("   ⚠️ 场景竞对未分配：归因题 5 个场景将全用同一主竞对。判定后跑"
              " assign_scenario_competitors.py <run_id> --apply 写回，再重跑本脚本"
              "（归因题文本变 → 自动开新基线，复制 P2）")
    tasks = measurement["agent_tasks"]
    if tasks:
        print(f"1. 命中语义判定（{len(tasks)} 题）: 子 agent 判五字段语义（recommendation/scene/引用内容/has_hotel_recommendations/hotels_recommended[推荐]/hotels_mentioned[提及]），档位竞对系统派生")
        for t in tasks[:5]:
            print(f"   - {t['question']}")
        if len(tasks) > 5:
            print(f"   ... 共 {len(tasks)} 题，详见 measurement_json['agent_tasks']")
    else:
        print("1. 命中语义判定: 无（本批无待判题）")
    print(f"2. 地区语境复核: 确认甲方是否在 {city} 语境被提到（别地区同名品牌不算命中），子 agent 判 scene 用 AI 分块标题")
    print("3. 生成待判清单 → 子 agent 判 → 回填六字段:")
    print(f"   python scripts/finalize_hit.py --generate {target_run_id} --out /tmp/待判清单.json")
    print(f"   python scripts/finalize_hit.py --apply {target_run_id} /tmp/判定.json   # 回填+派生档位+重算+backfill")
    await engine.dispose()


def _parse_args(argv):
    p = argparse.ArgumentParser(description="P3 诊断入口（测量段）")
    p.add_argument("brand", nargs="?", default="香格里拉")
    p.add_argument("city", nargs="?", default="福州")
    p.add_argument("run_id", nargs="?", default=None)
    p.add_argument("--platforms", default=None,
                   help="只测指定平台，逗号分隔（如 doubao / deepseek,kimi）。默认四平台全量")
    args = p.parse_args(argv)
    platforms = [x.strip() for x in args.platforms.split(",")] if args.platforms else None
    return args.brand, args.city, args.run_id, platforms


if __name__ == "__main__":
    brand, city, run_id, platforms = _parse_args(sys.argv[1:])
    asyncio.run(main(brand, city, run_id, platforms))
