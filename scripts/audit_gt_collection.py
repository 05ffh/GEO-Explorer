"""GT 采集可靠性验证（spec 优先级 v2 #1，2026-09-16）。

目的：确认 grounding_corpus（甲方自己页面过滤后的语料）对"甲方核心资产"覆盖完整——
覆盖缺口会让归因强制查语料把"甲方有但语料缺"的资产误判成真劣势（方向做反）。

验证分四块：
  L1 采集链路审计：抓取覆盖（search_results 甲方页面数/tier）、过滤保留率、语料装配块覆盖。
  L2 官网过滤抽查：抽 T0 页 raw vs content_text，核对过滤是否保留关键事实（主 agent 审）。
  L3 核心资产覆盖矩阵：check-list（AI 共识资产 + content_assets + 官网高频设施）
     × grounding_corpus 匹配 → 覆盖✓ / 缺口✗。缺口 = 下游归因 type 的假真劣势风险点。
  L4 缺口清单 → 人工终裁 → 补抓/refilter。

用法：
  python scripts/audit_gt_collection.py <brand> <city> --assets /tmp/gt_assets_checklist.json
    --out ./output
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.collector.client_pages import build_grounding_corpus
from src.config import settings

# 资产类关键词（官网 raw 高频设施提取用）：命中即视为"甲方资产证据"
_ASSET_KW = re.compile(
    r"泳池|健身|SPA|水疗|餐厅|酒吧|宴会|会议室|亲子|儿童|主题房|行政酒廊|豪华阁|"
    r"米其林|早餐|地铁|停车场|接送|桑拿|网球场|温泉|雪茄|茶|下午茶|购物|商场|"
    r"浴缸|天际|套房|客房|景观|江景|湖景|园林"
)


def _candidates(asset: str) -> list[str]:
    """资产名 → 语料匹配候选核心词集（多候选，任一命中即覆盖）。

    对抗审查 2026-09-16：只取最长实体片段会让措辞变体漏配（"健身中心"vs语料"健体中心"、
    "南门兜地铁站"vs"地铁南门兜站"、"天际客房"vs"天际房"→ 假缺口）。改为拆出所有 2-6 字
    子片段作候选，任一中语料即视为覆盖；剩余未命中才交主 agent 判"真缺口 vs 语义等价变体"。
    """
    a = re.sub(r"^(福州|香格里拉|酒店|国际)", "", asset.strip())
    cands = set()
    for part in re.split(r"[，。、·（）()\s/]", a):
        if len(part) < 2:
            continue
        cands.add(part)
        for w in re.findall(r"[一-鿿]{2,4}", part):
            cands.add(w)
    return sorted(c for c in cands if len(c) >= 2)


def _coverage_matrix(assets: list[str], corpus: str) -> dict:
    """资产清单 × 语料子串匹配 → 覆盖/缺口。任一核心词命中即覆盖，记录命中的词。"""
    out = {}
    for asset in assets:
        if not (asset or "").strip():
            continue
        cands = _candidates(asset)
        hit = matched = None
        for c in cands:
            if c in corpus:
                hit, matched = True, c
                break
        out[asset] = {"covered": bool(hit), "candidates": cands, "matched_by": matched}
    return out


async def main():
    p = argparse.ArgumentParser(description="GT 采集可靠性验证")
    p.add_argument("brand")
    p.add_argument("city")
    p.add_argument("--assets", default="/tmp/gt_assets_checklist.json")
    p.add_argument("--out", default="./output")
    args = p.parse_args()

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        brand_row = (await db.execute(text("SELECT id FROM brands WHERE name=:n"), {"n": args.brand})).fetchone()
        if brand_row is None:
            print(f"错误: 品牌 {args.brand} 不存在")
            await engine.dispose()
            sys.exit(1)
        brand_id = brand_row[0]

        # ---- L1 采集链路审计 ----
        tiers = (await db.execute(text("""
            SELECT source_tier,
                   count(*) as n,
                   sum(CASE WHEN raw_content IS NOT NULL AND raw_content<>'' THEN 1 ELSE 0 END) as with_raw,
                   sum(CASE WHEN content_text IS NOT NULL AND content_text<>'' THEN 1 ELSE 0 END) as with_text,
                   coalesce(sum(length(raw_content)),0) as raw_len,
                   coalesce(sum(length(content_text)),0) as text_len
            FROM search_results WHERE brand_id=:b GROUP BY source_tier ORDER BY source_tier
        """), {"b": brand_id})).fetchall()
        link = defaultdict(lambda: {"n": 0, "raw": 0, "text": 0, "raw_len": 0, "text_len": 0})
        for t in tiers:
            link[t[0]] = {"n": t[1], "raw": t[2], "text": t[3], "raw_len": t[4], "text_len": t[5]}

        # ---- L2 官网过滤抽查：抽 T0 最长 3 页 raw vs content_text ----
        t0_sample = (await db.execute(text("""
            SELECT url, raw_content, content_text FROM search_results
            WHERE brand_id=:b AND source_tier='T0' AND raw_content IS NOT NULL AND raw_content<>''
            ORDER BY length(raw_content) DESC LIMIT 3
        """), {"b": brand_id})).fetchall()

        # ---- L3 覆盖矩阵 ----
        corpus = await build_grounding_corpus(db, brand_id, args.city)

    await engine.dispose()

    assets = []
    if os.path.exists(args.assets):
        assets += json.load(open(args.assets, encoding="utf-8")).get("assets", [])

    matrix = _coverage_matrix(assets, corpus)
    covered = [k for k, v in matrix.items() if v["covered"]]
    gaps = [k for k, v in matrix.items() if not v["covered"]]

    # ---- 报告 ----
    lines = [f"# {args.city}{args.brand} GT 采集可靠性验证（spec 优先级 v2 #1）", ""]
    lines += ["## L1 采集链路审计", "", "| tier | 行数 | 有raw | 有content_text | raw总长 | 过滤后总长 | 保留率 |", "|---|---|---|---|---|---|---|"]
    for t, d in sorted(link.items()):
        rate = f"{d['text_len']/d['raw_len']*100:.0f}%" if d["raw_len"] else "—"
        lines.append(f"| {t} | {d['n']} | {d['raw']} | {d['text']} | {d['raw_len']} | {d['text_len']} | {rate} |")
    lines += ["", f"语料装配：grounding_corpus **{len(corpus)} 字**", ""]
    lines += ["## L2 官网过滤抽查（T0 最长 3 页 raw vs content_text）", ""]
    for u, raw, txt in t0_sample:
        lines.append(f"- `{u[:60]}` raw {len(raw)}字 → content_text **{len(txt)}字**")
    lines += ["", "## L3 核心资产覆盖矩阵（AI 共识标尺 × 语料）", ""]
    lines += [f"- check-list {len(matrix)} 条 | **覆盖 {len(covered)}** | **缺口 {len(gaps)}**", ""]
    for asset, v in matrix.items():
        mark = "✅" if v["covered"] else "❌"
        ev = f"（匹配 {v['matched_by']}）" if v["matched_by"] else f"（候选 {v['candidates']}）"
        lines.append(f"- {mark} {asset}{ev}")
    lines += ["", "## L4 缺口清单（下游归因假真劣势风险点）", ""]
    if gaps:
        for g in gaps:
            lines.append(f"- ❌ **{g}** —— 语料未覆盖 → 人工终裁甲方是否有，有则补抓/refilter")
    else:
        lines.append("- 无缺口")
    lines += ["", "> 环环相扣：grounding_corpus → build_client_context → 归因强制查语料 → type 判定。缺口=该资产归因会误判真劣势。"]
    report = "\n".join(lines)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"{args.city}{args.brand}_GT采集可靠性验证.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"验证完成：资产 {len(matrix)} 条，覆盖 {len(covered)}，缺口 {len(gaps)} → {path}")
    print("缺口:", gaps)


if __name__ == "__main__":
    asyncio.run(main())
