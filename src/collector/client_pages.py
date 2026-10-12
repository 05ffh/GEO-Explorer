"""甲方自己页面全文抓取 + 过滤（P2 GT 正文分层，2026-09-14）。

背景：P2 采集只存搜索**摘要**（snippet），content_text 全空；但 GT 内容两个下游消费方
（① 归因 grounding ② P4 落地内容产出）都需要**全文**。本模块抓甲方自己页面的正文，过滤成
**甲方属性基准事实**，分层存储：
- `raw_content` = 抓取原文（重处理原料，不对下游暴露）
- `content_text` = 过滤后基准事实（下游消费）

归属：只抓**甲方自己的页面**（URL 认领品牌+城市），防竞对/别地污染。
过滤：`content_filter.filter_client_facts`（行级去噪+抽属性，高召回）。
"""
from __future__ import annotations

import re

import httpx
from sqlalchemy import text

from src.config import settings
from src.collector.content_filter import filter_client_facts

TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"
_IMG_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")

# 城市拼音映射（URL 认领甲方页面用；仅列常用，新城市补这里或走中文匹配兜底）
_CITY_PINYIN = {
    "北京": "beijing", "上海": "shanghai", "广州": "guangzhou", "深圳": "shenzhen",
    "福州": "fuzhou", "厦门": "xiamen", "杭州": "hangzhou", "成都": "chengdu",
    "南京": "nanjing", "苏州": "suzhou", "武汉": "wuhan", "西安": "xian",
    "重庆": "chongqing", "天津": "tianjin", "长沙": "changsha", "青岛": "qingdao",
}


def city_pinyin(city: str) -> str:
    return _CITY_PINYIN.get(city, "")


def is_client_page_url(url: str, brand: str, city: str, city_en: str, brand_en: str = "") -> bool:
    """URL 是否甲方自己的页面（品牌+城市同时在 URL/title 里）。

    空串守卫（2026-09-15 修）：city_en/brand_en 缺省是 ""，`"" in url` 恒 True 会让
    city_hit/brand_hit 无条件通过（表外城市/品牌时误认领别地/别品牌页面）。
    """
    u = (url or "").lower()
    raw = url or ""
    brand_hit = bool(brand) and brand in raw
    if not brand_hit and brand_en:
        brand_hit = brand_en in u
    city_hit = bool(city) and city in raw
    if not city_hit and city_en:
        city_hit = city_en in u
    return brand_hit and city_hit


def _no_page_reason(rows: list, brand: str, city: str, city_en: str, brand_en: str) -> str:
    """抓不到甲方页面时的诊断原因（防静默降级：接地语料空 → 归因退回只用 content_assets）。"""
    if not rows:
        return "search_results 无含品牌+城市的候选 URL（P2 facts 是否落库？）"
    hints = []
    if not brand_en:
        hints.append(f"品牌「{brand}」不在 brand_domains（无英文名，英文 URL 无法认领）")
    if not city_en:
        hints.append(f"城市「{city}」不在 city_pinyin 映射（非中文 URL 无法认领，补 _CITY_PINYIN）")
    base = "候选 URL 均未同时含品牌+城市"
    return base + ("；" + "；".join(hints) if hints else "")


def _clean(raw: str) -> str:
    from src.collector.content_filter import to_simplified
    return to_simplified(
        re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", _IMG_MD.sub("", raw or ""))).strip()
    )


async def fetch_pages(urls: list[str], batch: int = 5) -> dict[str, str]:
    """Tavily /extract 抓页面原文（trust_env=False 绕过坏代理）。返回 {url: raw}。"""
    fetched: dict[str, str] = {}
    key = getattr(settings, "tavily_api_key", None)
    if not key:
        return fetched
    async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
        for i in range(0, len(urls), batch):
            try:
                r = await c.post(TAVILY_EXTRACT_URL, json={"urls": urls[i:i + batch]},
                                 headers={"Authorization": f"Bearer {key}"})
                if r.status_code == 200:
                    for res in r.json().get("results", []):
                        fetched[res.get("url", "")] = _clean(res.get("raw_content") or "")
            except Exception:
                continue
    return fetched


async def fetch_and_store_client_pages(db, brand_id, brand: str, city: str,
                                       city_en: str, brand_en: str = "") -> dict:
    """读 search_results 甲方页面 URL → 抓全文 → 过滤 → 分层存 raw_content + content_text。

    返回 {"urls": n, "fetched": n, "rows": n, "reason": str}（reason 空=正常，非空=抓 0 页的原因）。
    robust：无 URL/无 key/抓取失败不抛（采集不中断）。
    """
    rows = (await db.execute(text("""
        SELECT DISTINCT url FROM search_results
        WHERE brand_id=:b AND url IS NOT NULL
          AND query LIKE :brandq AND query LIKE :cityq
    """), {"b": brand_id, "brandq": f"%{brand}%", "cityq": f"%{city}%"})).fetchall()
    urls = [u for (u,) in rows if is_client_page_url(u, brand, city, city_en, brand_en)]
    if not urls:
        return {"urls": 0, "fetched": 0, "rows": 0,
                "reason": _no_page_reason(rows, brand, city, city_en, brand_en)}
    fetched = await fetch_pages(urls)
    n = 0
    for u, content in fetched.items():
        if not content:
            continue
        # 采集端分层（架构改造 2026-09-17）：UGC 路径（游记/点评/攻略）→ opinion，content_text 置空
        # （原文存 raw_content，作为 AI 视角参考/舆情）；资料页 → fact（过滤后事实，下游消费）。
        # **源头分层**——不依赖事后治理脚本，换甲方新采集自动分层。
        layer = "opinion" if _UGC_PATH.search(u) else "fact"
        ct = "" if layer == "opinion" else filter_client_facts(content)
        res = await db.execute(text(
            "UPDATE search_results SET raw_content=:raw, content_text=:filt, content_layer=:layer "
            "WHERE brand_id=:b AND url=:u"),
            {"raw": content, "filt": ct, "layer": layer, "b": brand_id, "u": u})
        n += res.rowcount
    return {"urls": len(urls), "fetched": len(fetched), "rows": n, "reason": ""}


async def refilter_client_pages(db, brand_id) -> int:
    """用当前过滤规则重跑 raw_content → content_text（**不重抓**，过滤规则升级时用）。返回更新行数。

    **按 URL 重新分层**（2026-09-17 修）：UGC 页 → opinion（content_text 置空，不重过滤）——
    否则 refilter 会把游记/点评正文灌回 content_text，破坏"opinion content_text 必须空"的契约。
    """
    rows = (await db.execute(text(
        "SELECT id, url, raw_content FROM search_results WHERE brand_id=:b AND raw_content IS NOT NULL AND raw_content<>''"),
        {"b": brand_id})).fetchall()
    n = 0
    for rid, url, raw in rows:
        layer = "opinion" if _UGC_PATH.search(url or "") else "fact"
        ct = "" if layer == "opinion" else filter_client_facts(raw)
        await db.execute(text("UPDATE search_results SET content_text=:c, content_layer=:l WHERE id=:i"),
                         {"c": ct, "l": layer, "i": rid})
        n += 1
    return n


_TIER_ORDER = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4}
_TIER_NAME = {"T0": "官网/官方", "T1": "OTA平台", "T2": "点评媒体", "T3": "UGC", "T4": "其他"}
# 预算按信源分层：官网最权威但**不独占**——纯 tier 优先时，官网内容超预算会整片饿死 OTA/点评/
# 口碑视角（福州香格里拉官网过滤后 8164 字 > 8000 预算 → 评分/口碑事实全丢）。未用份额顺延给下层。
_TIER_SHARE = {"T0": 0.60, "T1": 0.25, "T2": 0.10, "T3": 0.05}
# OTA/UGC 域名下的社区/攻略页（游记口吻）≠ 酒店资料页——同一域名信源级相同但可信度不同，加标签提示
_UGC_PATH = re.compile(
    r"/(moments|theme|guides?|review|reviews|travel-guide|attractions?|things-to-do|notes?|bbs|forum)/", re.I)
# 通用列表页（城市/区域/星级/榜单）——非本酒店专页，事实密度低；同 tier 内排到专页（含品牌/详情路径）之后
_GENERIC_PATH = re.compile(r"/(city|region|district|country|fivestars|hotels-list|search)/", re.I)
# 时效弱标记（2026-09-18）：营销活动页（offer/campaign/节日）或路径含年份的 URL——旧活动内容会过时
# （如 /campaign-rooms-2025laborday/、/offer-detail/...）。同 tier 内排到**末尾**（时效最弱，预算不够先丢）。
_STALE_URL = re.compile(r"/(offer|offers|campaign|promo|deal|package)[^/]*/|/20\d{2,6}[a-z-]*/", re.I)


def _label(tier: str, url: str) -> str:
    tier = tier or "T3"
    name = _TIER_NAME.get(tier, tier)
    if _UGC_PATH.search(url or ""):
        name += "·游记/第三方"
    return f"{tier} {name}"


def assemble_corpus(pages: list[tuple[str, str, str]], budget_chars: int = 8000,
                    tier_share: dict[str, float] | None = None) -> str:
    """把 [(tier, url, content_text)] 填成归因接地语料：tier 权威序 + 行级去重 + 分层配额装填。

    第一性原理：语料要"给定预算内覆盖甲方**多视角**事实（官网设施/餐饮 + OTA 评分/口碑）"。
    以**行**为装填单位（非整页）——旧版整页判断"装不下就 break"白扔预算且整片丢 OTA（2026-09-15 修）。
    **按 tier 配额**（`tier_share`）：官网最权威但不得独占——否则官网内容超预算会饿死评分/口碑视角
    （福州香格里拉官网 8164 字 > 8000 → 纯优先会让 T1/T2/T3 颗粒无收）；某层未用份额顺延给下层。
    """
    share = {**_TIER_SHARE, **(tier_share or {})}
    # 同 URL 取最高信源级（best-per-url）
    best: dict[str, tuple[str, str]] = {}
    for tier, url, content in pages:
        if not (content or "").strip():
            continue
        key = url or ""
        if key not in best or _TIER_ORDER.get(tier, 9) < _TIER_ORDER.get(best[key][0], 9):
            best[key] = (tier or "T3", content)
    # 按标签分组（tier + 是否游记），**标签内按价值排序**（本酒店专页 > 通用列表页）再跨页行去重
    groups: dict[str, list[str]] = {}
    seen: set[str] = set()

    def _value_key(item):
        url, (tier, _c) = item
        # 2026-09-18：时效弱标记（营销/年份活动页）排最后——同 tier 内预算不够先丢旧活动页
        return (_TIER_ORDER.get(tier, 9), bool(_UGC_PATH.search(url or "")),
                bool(_GENERIC_PATH.search(url or "")), bool(_STALE_URL.search(url or "")), url or "")

    for url, (tier, content) in sorted(best.items(), key=_value_key):
        label = _label(tier, url)
        for line in content.split("\n"):
            ls = line.strip()
            if not ls or ls in seen:
                continue
            seen.add(ls)
            groups.setdefault(label, []).append(line)
    # 标签装填序：tier 权威序，同 tier 内"资料页"先于"游记"
    by_tier: dict[str, list[str]] = {}
    for label in sorted(groups, key=lambda L: (_TIER_ORDER.get(L[:2], 9), "游记" in L)):
        by_tier.setdefault(label[:2], []).append(label)
    parts, total, leftover = [], 0, 0
    tier_seq = sorted(set(by_tier) | set(_TIER_ORDER), key=lambda t: _TIER_ORDER.get(t, 9))
    for tier in tier_seq:
        tier_labels = by_tier.get(tier)
        if not tier_labels:
            leftover += int(budget_chars * share.get(tier, 0.0))   # 缺席层份额顺延给下层
            continue
        allowance = int(budget_chars * share.get(tier, 0.0)) + leftover   # 份额按 tier 计，未用顺延
        used = 0
        for label in tier_labels:
            kept: list[str] = []
            for line in groups[label]:
                if used >= allowance or total + len(line) + 1 > budget_chars:
                    break
                kept.append(line)
                total += len(line) + 1
                used += len(line) + 1
            if kept:
                parts.append(f"[{label}] " + "\n".join(kept))
            if used >= allowance:
                break
        leftover = allowance - used
        if total >= budget_chars:
            break
    return "\n".join(parts)


async def build_grounding_corpus(db, brand_id, city: str, budget_chars: int = 8000) -> str:
    """归因接地语料（方案A，2026-09-14）：甲方自己页面的过滤后正文（content_text），
    按信源级排序（T0 官网 > T1 OTA > T2 点评 > T3 UGC）拼到 budget_chars 上限。

    与 content_assets（AI 引用）不同——这是**甲方页面原话**（GT 证实），供子 agent 判断
    「甲方有没有 X」时在原文里查，替代闭集清单（未提到≠没有）。方括号标信源（含"游记/第三方"
    提示），下游据此权衡可信度。装配细节见 assemble_corpus。

    行来源：brand_id + query 含城市（`fetch_and_store_client_pages` 只对甲方页面写 content_text，
    content_text 非空 ⟹ 甲方页面——存储契约，无需再按 URL 认领）。

    **只读 fact 层**（2026-09-17 修）：content_layer='fact' 卡口。分层契约由写入方维持
    （fetch_and_store 源头分层 + clean_gt_content 治理），但 `refilter_client_pages` 不写
    content_layer 且重过滤全部行（含 opinion）→ 光靠"content_text 非空"会放第三方观点进语料。
    在**唯一读方**加守卫，未来任何写入方都安全。
    """
    rows = (await db.execute(text("""
        SELECT url, source_tier, content_text FROM search_results
        WHERE brand_id=:b AND content_text IS NOT NULL AND content_text<>''
          AND (content_layer IS NULL OR content_layer='fact')
          AND query LIKE :cq
    """), {"b": brand_id, "cq": f"%{city}%"})).fetchall()
    return assemble_corpus([(t, u, c) for u, t, c in rows], budget_chars)
