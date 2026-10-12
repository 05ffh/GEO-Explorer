"""content_text 治理（2026-09-16）：只保留甲方「真实可信可用」的 GT 事实（换甲方通用）。

content_text 被下游消费（归因接地语料）→ 必须只含「甲方自己陈述的事实」（设施/餐饮/位置/服务），
不含：UGC 游记/点评（观点 + 常推荐竞对）、重复行、竞对对比。

治理三层（确定性、通用，不硬编码品牌/城市）：
  1. URL 准入：UGC 路径（/moments/、/review、/theme/、/guides、/bbs）→ content_text 置空
     （这些页主体是游记/点评，非甲方事实；raw_content 保留可追溯）
  2. 重过滤：raw_content → filter_client_facts（含 UGC 点评行剥离）→ content_text
  3. 去重：同 URL 多行只保留 1 行有 content_text（tier 权威序 + 内容最长）

用法：
  python scripts/clean_gt_content.py <brand> <city>          # 预览（不改库）
  python scripts/clean_gt_content.py <brand> <city> --apply   # 执行治理
"""
from __future__ import annotations

import argparse
import asyncio
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.client_pages import _TIER_ORDER, _UGC_PATH as UGC_PATH
from src.collector.content_filter import filter_client_facts
from src.config import settings

# 竞对酒店后缀（去后缀得品牌核心词）
_COMP_SUFFIX = re.compile(r"(大酒店|大饭店|酒店|饭店|宾馆|度假村|国际会议中心|国际|会议中心)$")


def _comp_keys(name: str, city: str) -> set[str]:
    """竞对全名 → 匹配核心词集（去城市前缀 + 酒店后缀 + 取 2-3 字），
    使 UGC 点评里的简称（"世茂"）也能匹配全名（"福州世茂洲际酒店"）。"""
    n = name
    if city and n.startswith(city):
        n = n[len(city):]
    n = _COMP_SUFFIX.sub("", n)
    keys = {n}
    if len(n) >= 2:
        keys.add(n[:2])
    if len(n) >= 3:
        keys.add(n[:3])
    return {k for k in keys if len(k) >= 2}


async def main():
    p = argparse.ArgumentParser(description="content_text 治理")
    p.add_argument("brand")
    p.add_argument("city")
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    eng = create_async_engine(settings.database_url)
    async with async_sessionmaker(eng, expire_on_commit=False)() as db:
        bid = (await db.execute(text("SELECT id FROM brands WHERE name=:n"), {"n": args.brand})).fetchone()
        if not bid:
            print(f"错误: 品牌 {args.brand} 不存在"); await eng.dispose(); return
        bid = bid[0]
        # 竞对名（positioning.competitors，通用）：甲方事实页不应推荐/对比竞对 → 含竞对名的行剥离
        pos = (await db.execute(text(
            "SELECT positioning_json FROM collection_runs WHERE brand_id=:b ORDER BY created_at DESC LIMIT 1"),
            {"b": bid})).fetchone()
        comp_keys: set[str] = set()
        for c in ((pos[0] or {}).get("competitors") or []):
            name = c.get("name") if isinstance(c, dict) else c
            if name:
                comp_keys |= _comp_keys(name, args.city)
        rows = (await db.execute(text("""
            SELECT id::text, url, source_tier, coalesce(raw_content,''), coalesce(content_text,''), search_backend
            FROM search_results WHERE brand_id=:b AND (content_text<>'' OR raw_content<>'')
        """), {"b": bid})).fetchall()

        before = sum(len(r[4]) for r in rows)
        # 1) URL 准入 + 2) 重过滤；plan = id -> (content_text, content_layer)
        plan = {}
        ugc_cleared = refiltered = 0
        for rid, url, tier, raw, ct, backend in rows:
            if UGC_PATH.search(url or ""):
                plan[rid] = ("", "opinion"); ugc_cleared += 1
                continue
            # agent_verified（主 agent 联网查证补录）：raw 是来源 URL 说明、content_text 是整理好的
            # 事实 → 保留 content_text，不重过滤（否则 raw 过滤为空覆盖掉事实）
            if backend == "agent_verified":
                plan[rid] = (ct, "fact")
                continue
            new_ct = filter_client_facts(raw) if raw else ct
            if comp_keys:   # 剥离含竞对名的行（UGC 推荐的别家酒店 / 竞对对比，非甲方事实）
                new_ct = "\n".join(l for l in new_ct.split("\n") if not any(k in l for k in comp_keys))
            if new_ct != ct:
                refiltered += 1
            plan[rid] = (new_ct, "fact")

        # 3) 去重：同 URL 仅保留 1 行有 content_text（tier 权威序 + 内容最长）
        # tier 取负：_TIER_ORDER T0=0/T3=3，max 需选数字最小（最权威 T0）→ 用负值
        by_url = {}
        for rid, url, tier, raw, ct, backend in rows:
            key = (url or "").rstrip("/")
            cand = (plan[rid][0], -_TIER_ORDER.get(tier or "T3", 9), -len(plan[rid][0]))
            if key not in by_url or cand > by_url[key][0]:
                by_url[key] = (cand, rid)
        keep = {v[1] for v in by_url.values()}
        deduped = 0
        for rid in list(plan):
            if plan[rid][0] and rid not in keep:
                plan[rid] = ("", "fact"); deduped += 1

        after = sum(len(v[0]) for v in plan.values())
        n_opinion = sum(1 for v in plan.values() if v[1] == "opinion")
        print(f"页行 {len(rows)} | UGC 路径置空 {ugc_cleared} | 重新过滤 {refiltered} | 去重置空 {deduped}")
        print(f"content_text 总长 {before} → {after} 字（-{before-after}）｜ opinion 层 {n_opinion} 行")
        print(f"有效页 {sum(1 for v in plan.values() if v[0])}（原 {sum(1 for r in rows if r[4])}）")
        if args.apply:
            for rid, (v, layer) in plan.items():
                await db.execute(text("UPDATE search_results SET content_text=:c, content_layer=:l WHERE id=:i"),
                                 {"c": v, "l": layer, "i": rid})
            await db.commit()
            print("✅ 已应用")
        else:
            print("（预览，未改库；加 --apply 执行）")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
