"""P4 落地内容·主题块渲染（2026-09-22 build，spec「P4 落地内容规格 v0.1」）。

通用模板（换甲方有效）：属性层 5 块 + 场景层 5 块 + 品牌特有（有真事实才生成）。
确定性渲染：事实原文+限定一字不改，来源/时间/弱证据进【证据备注·不对外】。
注水校验：数字可回溯（防编造）+ 事实覆盖（防注水丢事实）——AI 注水输出过这两个闸。
防幻觉铁律：消费端不压缩事实成标签、不插生成层；verified 无 URL = 弱证据。
"""
from __future__ import annotations

import re

# ---- 通用主题块模板（换甲方不变） ----
# categories=从 gt_facts_json 哪些分类取事实；selectors=场景块按关键词在候选池内筛选（事实原文不变，只决定归块）
THEMES: list[dict] = [
    # 属性层（答"有没有"，原料）
    dict(id="location", name="位置与交通", layer="attribute",
         questions=["酒店在哪里？交通方便吗？离机场/高铁站多远？", "附近有什么景点商圈？"],
         categories=("位置交通",)),
    dict(id="rooms", name="客房与房型", layer="attribute",
         questions=["酒店有多少间房？有什么房型？", "有没有景观房/主题房？"],
         categories=("客房",)),
    dict(id="wellness", name="康体与休闲", layer="attribute",
         questions=["酒店有泳池/健身房/SPA吗？", "运动休闲设施怎么样？"],
         categories=("康体设施",)),
    dict(id="dining", name="餐饮与美食", layer="attribute",
         questions=["酒店有什么餐厅？有米其林吗？", "早餐/送餐方便吗？"],
         categories=("餐饮",)),
    dict(id="business", name="商务与会议", layer="attribute",
         questions=["酒店能开会/办宴会吗？", "商务配套怎么样？"],
         categories=("会议宴会", "服务")),
    # 场景层（答"适合谁"，决策层，AI 高价值）
    dict(id="business_trip", name="商务出行", layer="scenario",
         questions=["商务出差选这家合适吗？", "会议接待方便吗？"],
         categories=("位置交通", "会议宴会", "服务", "餐饮"),
         selectors=r"商务|会议|宴会|行政|接送|机场|车站|礼宾|办公|出差",
         who_for="出差/开会/商务接待的旅客；需要会议宴会场地或行政酒廊的商务人士"),
    dict(id="family", name="亲子度假", layer="scenario",
         questions=["带娃住方便吗？", "有亲子房/儿童设施吗？"],
         categories=("客房", "康体设施", "餐饮", "配套", "服务"),
         selectors=r"主题房|亲子|儿童|加床|乐园|儿童池|游乐|家庭",
         who_for="带娃家庭、亲子出游；需要儿童房/儿童餐/乐园配套的家庭"),
    dict(id="couple", name="情侣·浪漫", layer="scenario",
         questions=["情侣/纪念日适合吗？", "有浪漫景观房或氛围餐厅吗？"],
         categories=("客房", "餐饮", "位置交通"),
         selectors=r"景观|酒廊|夜景|浪漫|情侣|下午茶|套房",
         who_for="情侣出游、纪念日/求婚；偏好景观房与氛围餐厅的客人"),
    dict(id="friends", name="朋友·聚会", layer="scenario",
         questions=["朋友聚餐/聚会适合吗？", "有包厢或热闹餐厅吗？"],
         categories=("餐饮", "配套", "服务"),
         selectors=r"酒廊|酒吧|宴会|聚会|聚餐|送餐|包厢|餐厅",
         who_for="朋友聚会/聚餐；看重餐饮酒廊与综合体娱乐的群体"),
    dict(id="solo", name="独自出行", layer="scenario",
         questions=["独自旅行/单人出差方便吗？", "交通和安全怎么样？"],
         categories=("位置交通", "客房", "服务"),
         selectors=r"地铁|车站|机场|单人|安全|位置|接送|独行",
         who_for="独自旅行/单人出差；看重交通便利与安全的旅客"),
    # 品牌特有（有真事实才生成，无则缺省）
    dict(id="complex", name="综合体配套", layer="brand",
         questions=["酒店连着商场吗？有什么配套娱乐？"],
         categories=("配套",)),
]

# 已停业/下线设施 → 排除出铺放，进"已停业清单"（防 AI 复述旧信息，韩香馆教训）
_CLOSED = re.compile(r"已停业|停业|已下线|下线|已停|关门|不再营业")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_CJK_RUN = re.compile(r"[一-鿿]{3,}")


def render_theme_blocks(gj: dict, brand: str = "该酒店") -> tuple[list[dict], list[str]]:
    """gt_facts_json → 主题块（确定性结构渲染）+ 已停业排除清单。"""
    by_cat: dict[str, list[dict]] = (gj or {}).get("facts") or {}
    blocks: list[dict] = []
    closed: list[str] = []
    for theme in THEMES:
        pool: list[dict] = []
        for cat in theme["categories"]:
            pool.extend(by_cat.get(cat) or [])
        sel = re.compile(theme["selectors"]) if theme.get("selectors") else None
        chosen = [it for it in pool if not sel or sel.search(it.get("fact") or "")]
        active: list[dict] = []
        for it in chosen:
            t = (it.get("fact") or "").strip()
            if not t:
                continue
            if _CLOSED.search(t):
                if t not in closed:  # 同一停业事实会匹配多块（场景选择器），只记一次
                    closed.append(t)
            else:
                active.append(it)
        if not active:
            continue  # 无真事实（含品牌特有块）→ 缺省不生成
        blocks.append(_build_block(theme, active, brand))
    return blocks, closed


def _build_block(theme: dict, facts: list[dict], brand: str) -> dict:
    items = []
    for f in facts:
        t = (f.get("fact") or "").strip()
        # 弱证据：联网核验（source_kind=verified）但无单页可溯源 URL
        weak = f.get("source_kind") == "verified" and not (f.get("source_url") or "")
        limit = bool(re.search(r"会员制|仅住客|需预约|提前.{0,4}预约|需预订|仅限", t))
        items.append({
            "text": t,
            "tier": f.get("source_tier") or "?",
            "url": f.get("source_url") or "",
            "captured": f.get("captured_at") or "",
            "weak": weak,
            "limit": limit,
        })
    numbers = [t for t in (it["text"] for it in items) if _NUM.search(t)]
    return {
        "id": theme["id"],
        "name": theme["name"],
        "layer": theme["layer"],
        "questions": theme["questions"],
        "direct": f"{brand}酒店「{theme['name']}」：" + "；".join(it["text"] for it in items[:2]) + "。",
        "facts": items,
        "who_for": theme.get("who_for", ""),
        "numbers": numbers,
    }


# ---- 注水校验（AI 注水输出必须过这两闸） ----

def check_untraceable_numbers(text: str, facts: list[str]) -> list[str]:
    """注水文本里的数字必须都能在源事实里找到（防编造数字）。返回不可溯源数字。"""
    fact_nums: set[str] = set()
    for f in facts:
        fact_nums.update(_NUM.findall(f))
    return sorted(set(_NUM.findall(text)) - fact_nums)


def check_fact_coverage(text: str, facts: list[str]) -> list[str]:
    """每条源事实的关键内容应出现在注水文本里（防注水丢事实）。返回未被覆盖的事实。"""
    missed = []
    for f in facts:
        nums = _NUM.findall(f)
        runs = _CJK_RUN.findall(f)
        keys = nums + [r for r in runs if len(r) >= 3][:3]
        if not any(k in text for k in keys):
            missed.append(f)
    return missed


if __name__ == "__main__":
    demo = {"facts": {
        "位置交通": [{"fact": "步行约3分钟到地铁南门兜站", "source_tier": "T0", "source_kind": "corpus",
                      "source_url": "https://www.shangri-la.com/cn/fuzhou/shangrila/", "captured_at": "2026-09-18"},
                     {"fact": "距长乐机场约45分钟车程", "source_tier": "T0", "source_kind": "corpus",
                      "source_url": "https://www.shangri-la.com/cn/fuzhou/shangrila/", "captured_at": "2026-09-18"}],
        "餐饮": [{"fact": "韩香馆（韩国烧烤）（已停业，2026-09-18 核实）", "source_tier": "T1", "source_kind": "corpus",
                  "source_url": "", "captured_at": "2026-09-18"},
                 {"fact": "江南灶·融府（2楼，淮扬菜，2025、2026 连续两年米其林一星）", "source_tier": "T1",
                  "source_kind": "corpus", "source_url": "https://hk.trip.com/", "captured_at": "2026-09-18"}],
    }}
    blocks, closed = render_theme_blocks(demo, "福州香格里拉")
    for b in blocks:
        print(f"[{b['layer']}] {b['name']} — {len(b['facts'])} 事实")
    print("已停业排除:", closed)
    assert check_untraceable_numbers("机场班车每25分钟一班", [f["text"] for b in blocks for f in b["facts"]]) == ["25"]
    assert "韩香馆" not in "\n".join(f["text"] for b in blocks for f in b["facts"])
    print("demo OK")
