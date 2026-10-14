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
    """写负面率结果（store_level[+brand_level]）到 collection_run 的 sentiment_json。

    **档位集合以本次 payload 为准**（重写 level 键集）：单档只留 store_level、清掉陈旧 brand_level——
    否则深合并会让已换成单档的诊断单元残留旧口径的品牌级。档位**内部**深合并：主 agent 终判只改
    rate/negative_count/status，保留 total/themes（compute_negative_rate 原始信息），避免终判丢主题分布。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is not None:
        existing = dict(run.sentiment_json or {})
        run.sentiment_json = {
            level: {**existing.get(level, {}), **sentiment[level]}
            for level in sentiment
        }
        await db.flush()


# 甲方级 P2 字段（诊断单元级，与问法无关）。sentiment_json 列在此（属 P2）但**两条路径都 skip**
# ——它是测量结果（绑词表+时点），一律重采，不做承接（见 carry_forward_p2 docstring）。
_P2_FIELDS = ("positioning_json", "gt_facts_json", "cdp_facts_json", "sentiment_json")


async def carry_forward_p2(db, src_run: CollectionRun, dst_run: CollectionRun,
                           *, skip: tuple[str, ...] = ()) -> list[str]:
    """把「甲方级 P2」从 src_run 承接（深拷贝）到 dst_run，返回实际承接字段。

    甲方事实 = positioning（定位）/ gt_facts_json（第一依据）/ cdp_facts_json（CDP 台账）——
    随**诊断单元**（品牌+地区）而非问法走，换问法/重建 P2 都应承接。
    - **换问法**（clone 路径）：承接 `positioning/gt/cdp`，`skip=("sentiment_json",)` 让舆情重采。
    - **重建 P2**（run_gt_diagnosis，如换舆情词）：同上，`skip=("sentiment_json",)`。
    **`sentiment_json` 两条路径都 `skip`（2026-10-14，第一性原理）**：舆情是绑「词表+时点」的**测量结果**
    （同命中率），非甲方事实——换舆情词后旧舆情不可比、时点已旧 → 承接是错的（还会冒充 confirmed）。
    舆情一律**新基线重采**（`run_measure --refresh-sentiment` 或 `refresh_sentiment.py`）。
    深拷贝 → 新 run 独立（改一个不动另一个）；**根因**：clone 是 09-05 build，gt_facts_json 09-16 才加，
    曾漏承接 → 新基线第一依据为空（2026-10-14 修）。
    """
    carried: list[str] = []
    for f in _P2_FIELDS:
        if f in skip:
            continue
        setattr(dst_run, f, copy.deepcopy(getattr(src_run, f) or {}))
        carried.append(f)
    await db.flush()
    return carried


async def write_cdp_facts(db, collection_run_id: uuid.UUID, facts: dict) -> None:
    """写 CDP 多平台事实清单（中间处理层产出）到 collection_runs.cdp_facts_json。

    中间处理层 = **主 agent 判断**（归类 gt_facts_json 8 类 / 跨平台一致性核对 / 高价值过滤），
    非脚本自动化。**独立存**，主 agent 核验后再并入 gt_facts_json（第一依据）——保持来源可控可审计。
    """
    run = await db.get(CollectionRun, collection_run_id)
    if run is not None:
        run.cdp_facts_json = facts
        await db.flush()


# CDP 平台域名 → 平台名（多平台接入时补；携程/同程/飞猪）
_CDP_PLATFORM = {"ctrip.com": "携程", "ly.com": "同程", "alitrip.com": "飞猪"}

# 中间处理层固化规范（对齐 _HIT_SPEC/_ATTRIBUTION_SPEC：随待处理输入内嵌下发，防主 agent 手写漂移）。
_CDP_MIDLAYER_SPEC = (
    "CDP 中间处理层判定（spec「CDP 中间处理层设计」）：读 OTA 详情页事实原文 → 产 8 类结构化事实，"
    "供并入 gt_facts_json（第一判决依据，无 8000 字预算截断）。\n"
    "**输入**：各平台的 content_text（已是过滤后的甲方属性事实层，非整页原文）。\n"
    "**输出**：{\"facts\": {8 类: [事实...]}, \"stale_facts\": {8 类: [{\"fact\":\"...\",\"reason\":\"...\"}]}, "
    "\"consistency\": {铁律字段: \"agree\"/\"conflict\"}}。\n"
    "1. 归类到 8 类（对齐 gt_facts_json schema；fact 原文一字不改，不压缩成标签）：\n"
    "   位置交通（地址/交通/周边距离/商圈）｜客房（房型/间数/面积/床型/主题房）｜"
    "康体设施（泳池/健身/SPA/桑拿/网球场）｜餐饮（餐厅/菜系/米其林/酒廊/早餐）｜"
    "会议宴会（宴会厅/会议室/场地面积/容量）｜服务（接送/礼宾/加床/儿童政策）｜"
    "配套（商场/滑雪场/影院/乐园）｜荣誉（星级/奖项/认证）。\n"
    "   ⚠️ OTA 页 H1 区常混类（地址/房型/评分/附近同区）→ **按行归类**，不整块搬；"
    "无主语残行（孤立的「免费」「310米」）先并回主语行再判。\n"
    "2. 一致性核对：**铁律字段优先**（店名/地址/政策/房型）跨平台比对——一致记 agree，矛盾记 conflict。\n"
    "   ⚠️ 矛盾**标出、不静默取一**（AI 判「有风险」是硬约束）；无冲突字段不入 consistency。\n"
    "   ⚠️ **矛盾的事实项不进 `facts`**——自动合并闸门（`_is_conflict`）只拦「数字矛盾」，政策类矛盾"
    "（加床/退改/宠物/年龄分档/时间窗）拦不住 → 会静默污染第一依据。凡跨平台或与基线矛盾的事实，"
    "**改记入 `consistency`（值写明双方口径）**，不进 `facts`。\n"
    "3. 高价值过滤：只留**有主语 + 可验证 + 跨平台不矛盾**的事实；丢观点/营销软文/无主语残渣。"
    "跨平台相似或包含的行**去重合并**，platforms 记全部出现平台。\n"
    "4. 每项 schema：{\"fact\": \"<事实原文>\", \"platforms\": [\"携程\", ...]}（来源/时间等由系统补）。\n"
    "5. **过时/停业事实**（描述里提到已改造/已停业项，如飞猪「酒店介绍」的『夏宫』——已改造为江南灶·融府）："
    "**不进 `facts`**（避免污染 gt_facts_json 第一依据），单独记 `stale_facts`（同 8 类 schema + `reason`），"
    "供 P4「改过时信息」落地参考。判据=与 GT 时效审计/跨平台当前在营状态矛盾（输入附 `stale_reference`=GT 已确认的停业/改造项，比对用）。\n"
    "6. **地址 = 铁律字段**：跨平台对齐为统一口径「市+区+街道号」——某平台缺省/区时取最完整平台口径补全"
    "（如飞猪页无『鼓楼区』→ 用携程/同程口径补）。\n"
    "**输出格式**：只输出该 JSON，类名必须 ∈ 8 类；无其他文字。"
)


async def generate_cdp_midlayer_input(db, collection_run_id: uuid.UUID) -> dict:
    """读 run 的 CDP 采集成品（各平台 content_text）→ 中间处理层待处理输入（内嵌 spec，防漂移）。

    对齐 finalize_attribution.generate_attribution_pending：系统 generate 待处理 → 主 agent 判定 →
    ingest_cdp_facts（apply）落库。spec 自包含，任何调用方都拿到固化规范（防主 agent 手写漂移）。

    platforms 值取**列表**：同平台多页（同 run 多 --hotel-id）不静默丢，逐页进待处理。
    """
    rows = (await db.execute(
        select(SearchResultRecord.url, SearchResultRecord.query, SearchResultRecord.content_text)
        .where(SearchResultRecord.collection_run_id == collection_run_id,
               SearchResultRecord.search_backend == "cdp")
        .order_by(SearchResultRecord.collected_at)
    )).all()
    platforms: dict = {}
    for url, query, content_text in rows:
        name = next((n for dom, n in _CDP_PLATFORM.items() if dom in (url or "")), url or "unknown")
        platforms.setdefault(name, []).append(
            {"url": url, "query": query, "content_text": content_text or ""})
    # stale_reference：GT 已确认的过时项——供主 agent 判 CDP 页面过时描述时比对
    # （如飞猪「酒店介绍」的夏宫 vs GT「江南灶·融府 由原夏宫改造」）。**注入参照，不自动判**（判断属主 agent）。
    # 标记放宽到「改造/停业」等非「已」前缀（GT 记法如「由原夏宫改造」无「已」）——只入参照、非闸门，宁多勿漏。
    run = await db.get(CollectionRun, collection_run_id)
    gj = (run.gt_facts_json if run else None) or {}
    stale_reference = [
        it.get("fact") for items in (gj.get("facts") or {}).values()
        for it in items
        if any(m in (it.get("fact") or "") for m in ("停业", "改造", "关闭", "更名", "下线"))
    ]
    return {"run_id": str(collection_run_id), "platforms": platforms,
            "stale_reference": stale_reference, "spec": _CDP_MIDLAYER_SPEC}


_KV = re.compile(r"([一-龥]{0,4})(\d+(?:\.\d+)?)\s*(平方米|间|层|座|米|㎡|年|人|张|条|个)([一-龥]{0,2})")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _normalize_fact(s: str) -> str:
    """归一化事实文本（去空白/标点），供去重比对。"""
    return re.sub(r"[\s，。、；：（）()【】\[\]·\-—|/]", "", s or "")


def _kv(s: str) -> dict[str, str]:
    """{属性键: 数字}——冲突判定用（同一属性不同值：414间客房 vs 311间客房）。

    键取**非空语境**两侧（`前文+单位` 与/或 `单位+后文`），空的一侧不进键：
    - **后文**（单位+属性名词，如「间客房」）是主判据——领字不同（「酒店共有414间客房」vs「311间客房」）
      仍有共同后文键 → 不漏报同属性冲突；
    - 前窗 4 字覆盖到实体名（「茶亭地铁站810米」vs「南门兜地铁站310米」→ 键`茶亭地铁站米`≠`南门兜地铁站米`）
      → 不把不同实体误判为同属性（2026-10-12 真数据）。
    """
    out: dict[str, str] = {}
    for pre, num, u, post in _KV.findall(s or ""):
        if pre:
            out[pre + u] = num
        if post:
            out[u + post] = num
    return out


def _skeleton(s: str) -> str:
    """去数字 + 归一化（冲突兜底用）——「同文本、仅数字不同」即同属性。"""
    return _normalize_fact(_NUM.sub("", s or ""))


def _is_conflict(a: str, b: str) -> bool:
    """同一属性数字不同 → 冲突。两条并列判据（缺一不判）：

    ① 语境键（`_kv`，前文/单位）相同、数字不同 → `414间客房` vs `311间客房`、`共有414间客房` vs `311间客房`；
    ② **骨架全等**（去数字归一化后完全相同）但数字集不同 → `步行3分钟…` vs `步行5分钟…`（单位不在 `_KV` 表内也兜住）。
    ② 用**骨架全等**而非 Jaccard 相似度：模板同构但主语不同的事实（`大床房`/`双床房`、`专车送机`/`专车接机`、
    `茶亭站`/`南门兜站`）骨架不同 → 不误判（2026-10-12 真数据 10 例假冲突全部由此暴露）。
    """
    ka, kb = _kv(a), _kv(b)
    if any(k in kb and kb[k] != v for k, v in ka.items()):
        return True
    if set(_NUM.findall(a or "")) != set(_NUM.findall(b or "")):
        return _skeleton(a) == _skeleton(b)
    return False


async def _cdp_provenance(db, collection_run_id: uuid.UUID) -> dict:
    """run 的 CDP 采集成品 → {平台名: {source_url, source_tier, captured_at}}（溯源注入用）。

    同平台多页取首页（最早采集）；`captured_at` 用采集日期（对齐 build_gt_fact_index 的 YYYY-MM-DD）。
    """
    rows = (await db.execute(
        select(SearchResultRecord.url, SearchResultRecord.source_tier, SearchResultRecord.collected_at)
        .where(SearchResultRecord.collection_run_id == collection_run_id,
               SearchResultRecord.search_backend == "cdp")
        .order_by(SearchResultRecord.collected_at)
    )).all()
    out: dict = {}
    for url, tier, collected_at in rows:
        name = next((n for dom, n in _CDP_PLATFORM.items() if dom in (url or "")), url or "unknown")
        out.setdefault(name, {
            "source_url": url,
            "source_tier": tier,
            "captured_at": collected_at.date().isoformat() if collected_at else "",
        })
    return out


def _prov_for(it: dict, prov: dict) -> dict | None:
    """事实项 → 溯源 dict（按 platforms 顺序取首个有溯源的平台）。"""
    for plat in (it.get("platforms") or []):
        p = prov.get(plat)
        if p:
            return p
    return None


def _enrich_fact_prov(it: dict, prov: dict) -> dict:
    """CDP 事实并入第一依据前补溯源（spec §545：可信=可追溯；**系统补**，主 agent 不填）。

    拷贝并入（不原地改）→ cdp_facts_json 保持中间处理层原始产出。已有字段不覆盖（setdefault）。
    `captured_at`=首次捕获锚点；`last_seen_at`=最近一次 CDP 观测（重抓重合并会刷新，供时效审计）。
    """
    out = dict(it)
    p = _prov_for(it, prov)
    if p:
        out.setdefault("source_url", p["source_url"])
        out.setdefault("source_tier", p["source_tier"])
        out.setdefault("captured_at", p["captured_at"])
        out.setdefault("source_kind", "corpus")
        out.setdefault("last_seen_at", p["captured_at"])
    return out


async def merge_cdp_facts_into_gt(
    db, collection_run_id: uuid.UUID, *, apply_conflicts: bool = False,
) -> dict:
    """CDP 事实清单并入 gt_facts_json（第一判决依据），三态：去重 / 补充 / 冲突标注。

    去重 = CDP 事实**被既有条目覆盖**（CDP ⊆ 既有，归一化后包含）→ 跳过（防冗余）；
    补充 = 新事实追加（并入前**系统补溯源** source_url/tier/captured_at，对齐 §545）；
    冲突 = 同一属性（单位+名词）数字不同、或归一化 bigram 重叠 ≥0.45
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
    prov = await _cdp_provenance(db, collection_run_id)
    summary: dict = {"added": [], "deduped": [], "conflicts": []}
    for cls, items in (cdp.get("facts") or {}).items():
        existing = list(gt_facts.get(cls) or [])
        ex_norm = [(_normalize_fact(e.get("fact", "")), e) for e in existing]
        for it in items:
            fact = it.get("fact", "")
            t = _normalize_fact(fact)
            if not t:
                continue
            matched = next((e for en, e in ex_norm if en and t in en), None)
            if matched is not None:  # CDP ⊆ 既有 → 去重
                # 观测=复核：重抓重合并时刷新「最近观测」锚点（否则时间戳停在首次并入日 → 审计误报过时）
                p = _prov_for(it, prov)
                if p and p.get("captured_at"):
                    matched["last_seen_at"] = p["captured_at"]
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
            enriched = _enrich_fact_prov(it, prov)  # 系统补溯源（不原地改，cdp_facts_json 保原始）
            existing.append(enriched)
            ex_norm.append((t, enriched))
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
