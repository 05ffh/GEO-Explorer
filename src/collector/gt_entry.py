"""诊断入口的确定性工具（主 agent 编排时调用的系统函数）。

诊断单元 = 「品牌 + 地区」的门店实体。三个工具对应入口的三个确定性步骤：
查/建品牌 → 建 collection_run → 写定位结果。中间穿插主 agent 的搜索和判断。
"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime

from sqlalchemy import func, select

from src.models.brand import Brand
from src.models.collection_run import CollectionRun
from src.models.measurement_snapshot import MeasurementSnapshot
from src.models.search_result import SearchResultRecord


async def get_or_create_brand(db, name: str, org_id: uuid.UUID) -> Brand:
    """按名查品牌，不存在则创建。"""
    brand = (await db.execute(select(Brand).where(Brand.name == name))).scalar_one_or_none()
    if brand:
        return brand
    brand = Brand(organization_id=org_id, name=name, business_type="hotel", industry="酒旅")
    db.add(brand)
    await db.flush()
    return brand


async def create_collection_run(
    db, org_id: uuid.UUID, brand_id: uuid.UUID, city: str, region: str | None = None,
) -> CollectionRun:
    """创建采集运行（诊断单元 = 品牌 + 地区），返回空 positioning 的 run。"""
    run = CollectionRun(
        organization_id=org_id,
        brand_id=brand_id,
        city=city,
        region=region,
        collection_status="pending",
    )
    db.add(run)
    await db.flush()
    return run


async def write_search_result(
    db,
    org_id: uuid.UUID,
    brand_id: uuid.UUID,
    collection_run_id: uuid.UUID,
    search_backend: str,
    query: str,
    url: str,
    title: str = "",
    snippet: str = "",
    tier: str = "T3",
    published_at: str = "",
) -> SearchResultRecord:
    """写一条原始材料到 search_results（关联 collection_run，带 tier）。

    原始材料是"绝不编造"的可追溯证据——定位结果的每个字段，都能追溯到这条 URL。
    """
    rec = SearchResultRecord(
        organization_id=org_id,
        brand_id=brand_id,
        collection_run_id=collection_run_id,
        search_backend=search_backend,
        query=query,
        url=url,
        title=title,
        snippet=snippet,
        source_tier=tier,
        published_at=published_at or None,
    )
    db.add(rec)
    await db.flush()
    return rec


async def write_positioning(db, collection_run_id: uuid.UUID, positioning: dict) -> None:
    """写定位结果（tier/personas/competitors）到 collection_run 的 positioning_json。

    仅首次定位记录 positioned_at（定位时间戳，供 P3 校验新鲜度）；
    精修（finalize_tier/personas 读-改-写回）保留原时间戳，避免部分写回掩盖过时定位。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is not None:
        positioning = dict(positioning or {})
        positioning["positioned_at"] = positioning.get("positioned_at") or datetime.now().isoformat(timespec="seconds")
        run.positioning_json = positioning
        await db.flush()


async def write_sentiment(db, collection_run_id: uuid.UUID, sentiment: dict) -> None:
    """写负面率结果（store_level/brand_level）到 collection_run 的 sentiment_json。

    深合并：主 agent 终判只改 rate/negative_count/status（覆盖 negative_rate 相关字段），
    保留 total/themes（compute_negative_rate 的原始信息），避免终判覆盖丢主题分布。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is not None:
        existing = dict(run.sentiment_json or {})
        for level in ("store_level", "brand_level"):
            if level in sentiment:
                existing[level] = {**existing.get(level, {}), **sentiment[level]}
        run.sentiment_json = existing
        await db.flush()


async def write_cdp_facts(db, collection_run_id: uuid.UUID, facts: dict) -> None:
    """写 CDP 多平台事实清单（中间处理层产出）到 collection_runs.cdp_facts_json。

    中间处理层 = **主 agent 判断**（归类 gt_facts_json 8 类 / 跨平台一致性核对 / 高价值过滤），
    非脚本自动化。**独立存**，主 agent 核验后再并入 gt_facts_json（第一依据）——保持来源可控可审计。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is not None:
        run.cdp_facts_json = facts
        await db.flush()


_KV = re.compile(r"([一-龥]{0,2})(\d+(?:\.\d+)?)\s*(平方米|间|层|座|米|㎡|年|人|张|条|个)([一-龥]{0,2})")


def _normalize_fact(s: str) -> str:
    """归一化事实文本（去空白/标点），供去重比对。"""
    return re.sub(r"[\s，。、；：（）()【】\[\]·\-—|/]", "", s or "")


def _kv(s: str) -> dict[str, str]:
    """{前后文+单位: 数字}——冲突判定用（同一属性不同值：414间客房 vs 311间客房）。

    含**前后文**（非仅单位）防假阳性：`楼高26层` 与 `房型6-20层` 共享"层"但属性不同 → 键不同。
    """
    return {pre + u + post: num for pre, num, u, post in _KV.findall(s or "")}


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def _overlap(a: str, b: str) -> float:
    """Jaccard（union 归一）——避免"短事实 ⊂ 长事实"被 min 归一误判为高重叠。"""
    ga, gb = _bigrams(a), _bigrams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def _is_conflict(a: str, b: str) -> bool:
    """同一属性（前后文+单位）数字不同 → 冲突；或归一化 bigram Jaccard ≥0.45（数字不同的近似句）。

    键含前后文（而非仅单位）防假阳性：`414间客房` 与 `7间多功能厅` 共享"间"但属性不同 → 非冲突。
    """
    ka, kb = _kv(a), _kv(b)
    if any(k in kb and kb[k] != v for k, v in ka.items()):
        return True
    return _overlap(_normalize_fact(a), _normalize_fact(b)) >= 0.45


async def merge_cdp_facts_into_gt(
    db, collection_run_id: uuid.UUID, *, apply_conflicts: bool = False,
) -> dict:
    """CDP 事实清单并入 gt_facts_json（第一判决依据），三态：去重 / 补充 / 冲突标注。

    去重 = CDP 事实**被既有条目覆盖**（CDP ⊆ 既有，归一化后包含）→ 跳过（防冗余）；
    补充 = 新事实追加；冲突 = 同一属性（单位+名词）数字不同、或归一化 bigram 重叠 ≥0.45
    → **默认不并入**，记入 cdp_facts_json["merge_conflicts"] 待主 agent 核验
    （第一判决依据的改动须可控可审计；apply_conflicts=True 才强制并入）。

    注：去重**只认 CDP ⊆ 既有**——若 CDP 是更全的超集（既有 ⊂ CDP），不静默丢弃，
    走冲突/补充（避免丢信息）。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is None:
        return {"added": [], "deduped": [], "conflicts": [], "error": "run not found"}
    gt = dict(run.gt_facts_json or {})
    gt_facts = dict(gt.get("facts") or {})
    cdp = dict(run.cdp_facts_json or {})
    summary: dict = {"added": [], "deduped": [], "conflicts": []}
    for cls, items in (cdp.get("facts") or {}).items():
        existing = list(gt_facts.get(cls) or [])
        ex_norm = [(_normalize_fact(e.get("fact", "")), e) for e in existing]
        for it in items:
            fact = it.get("fact", "")
            t = _normalize_fact(fact)
            if not t:
                continue
            if any(t in en for en, _ in ex_norm if en):  # CDP ⊆ 既有 → 去重
                summary["deduped"].append({"class": cls, "fact": fact})
                continue
            conflict = next(
                (e for en, e in ex_norm if en and _is_conflict(fact, e.get("fact", ""))),
                None,
            )
            if conflict is not None:
                summary["conflicts"].append({"class": cls, "cdp": fact, "gt": conflict.get("fact")})
                if not apply_conflicts:
                    continue  # 默认不并入，待主 agent 核验
            existing.append(it)
            ex_norm.append((t, it))
            summary["added"].append({"class": cls, "fact": fact})
        gt_facts[cls] = existing
    gt["facts"] = gt_facts
    run.gt_facts_json = gt
    if summary["conflicts"]:
        cdp["merge_conflicts"] = summary["conflicts"]
        run.cdp_facts_json = cdp
    await db.flush()
    return summary


async def append_competitors(db, collection_run_id: uuid.UUID, competitors: list) -> None:
    """补竞品到 positioning_json（保留已有 tier/personas，按名去重**追加** competitors）。

    2026-09-13 修复：原实现直接覆盖整个列表——write_competitor 补新竞对时把已确认竞对冲掉
    （V5 实测：补三迪希尔顿/融侨皇冠后原 5 家丢失）。改为按名去重追加。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is not None:
        positioning = dict(run.positioning_json or {})
        existing = list(positioning.get("competitors") or [])
        seen = {(c.get("name") if isinstance(c, dict) else c) for c in existing}
        merged = list(existing)
        for c in competitors:
            name = c.get("name") if isinstance(c, dict) else c
            if name and name not in seen:
                merged.append(c)
                seen.add(name)
        positioning["competitors"] = merged
        run.positioning_json = positioning
        await db.flush()


async def write_measurement(
    db,
    collection_run_id: uuid.UUID,
    measurement: dict,
    snapshot_type: str | None = None,
) -> None:
    """写测量结果到 measurement_json + 快照表（spec ⑫ 版本与派生架构）。

    snapshot_type 语义：
      - 'draft'（采集）→ 只写 run.measurement_json（活数据，未判定草稿），**不开快照**
      - 'judge' / 'rejudge'（判定/重判）→ 新建快照，snapshot_no 递增（sealed 版本留痕）
      - 'full' / 'remeasure' → 历史兼容（旧采集语义，新流程用 draft+judge 代替）
      - 'backfill'（数据修正，如漏存字段）→ 不新增版本，更新最新快照 + backfilled_at
      - None → 兼容旧调用，按 full 处理

    版本不变量（spec ⑫）：判定结果不可原地覆盖——重判=新快照；backfill 仅用于修正数据错误。
    快照表支撑「发布后复测」追溯对比（整体 + 各平台命中率）。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is None:
        return
    # 深拷贝防 MutableDict 共享引用丢变更：调用方浅拷贝后原地改嵌套 dict，再赋给本列时
    # SQLAlchemy 变更检测不可靠（嵌套变更不触发 dirty）——统一在这里解耦，所有写路径安全。
    measurement = copy.deepcopy(measurement)
    run.measurement_json = measurement
    now = measurement.get("collected_at") or datetime.now().isoformat(timespec="seconds")
    if snapshot_type == "draft":
        await db.flush()
        return
    if snapshot_type == "backfill":
        snap = (
            await db.execute(
                select(MeasurementSnapshot)
                .where(MeasurementSnapshot.collection_run_id == collection_run_id)
                .order_by(MeasurementSnapshot.snapshot_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snap is not None:
            snap.measurement_json = measurement
            snap.backfilled_at = now
    else:
        max_no = (
            await db.execute(
                select(func.max(MeasurementSnapshot.snapshot_no))
                .where(MeasurementSnapshot.collection_run_id == collection_run_id)
            )
        ).scalar() or 0
        db.add(MeasurementSnapshot(
            collection_run_id=collection_run_id,
            snapshot_no=max_no + 1,
            snapshot_type=snapshot_type or "full",
            collected_at=now,
            measurement_json=measurement,
        ))
    await db.flush()
