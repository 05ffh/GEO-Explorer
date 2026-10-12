"""GT 事实清单可追溯回填（2026-09-18 架构「协议+元数据」）。

把 collection_runs.gt_facts_json 从「裸事实清单」升级为「可追溯事实索引」：每条补
source_url（页级溯源——该事实在哪页甲方原文支撑）+ captured_at（采集/核验时间戳）。
**可信 = 可追溯**（来源 URL + 时间戳），不是"被验证过"。

用法：
  python scripts/build_gt_fact_index.py <collection_run_id> [--force]
    --force：重算并覆盖已有 source_url（默认只补缺的，幂等）

溯源方法：把每条事实按标点切段 → 在 fact 层 content_text 里找覆盖该事实段比例最高的
甲方页面 URL（页级，非句级）。纯函数 annotate_facts 可测；匹配不到的标 "" + 时间戳，
说明是主 agent 联网查证/人工核验补录（非语料来源）。
"""
import argparse
import asyncio
import json
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings

_SEP = re.compile(r"[，。；、,;.：:·—\-（）()【】\[\]/\s及和与到约至]+")


def _tokens(fact: str, min_len: int = 2) -> list[str]:
    """事实拆成细 token（标点/顿号/斜杠/括号都拆）——总结式措辞也能定位支持页。"""
    toks = []
    for s in _SEP.split(fact or ""):
        s = s.strip()
        if len(s) >= min_len:
            toks.append(s)
    return toks


def annotate_facts(facts: dict, rows: list[tuple[str, str]], captured_at: str,
                   force: bool = False) -> tuple[dict, dict]:
    """给 gt_facts_json 每条事实补 source_url/captured_at/source_kind。返回 (新 facts, 统计)。

    rows = [(url, content_text)]（fact 层）；captured_at = 核验时间戳（last_verified_at）。
    溯源 = 页级（该事实的哪些 token 出现在哪页原文）；只认 **http 真 URL**（坏 URL 如
    `baike.baidu.com/cvent` 是补抓存库的脏值，溯源不可靠——宁标 verified 不硬塞）。
    source_kind：corpus=语料溯源；verified=联网查证/人工核验补录（source_url 为空）。
    幂等：默认只补缺字段；--force 重算覆盖。
    """
    cats = facts.get("facts")
    if not isinstance(cats, dict):
        return facts, {}
    stats = {"total": 0, "traced": 0, "untraced": 0}
    good_rows = [(u, c) for u, c in rows if (u or "").startswith("http")]
    for items in cats.values():
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            if not force and (it.get("source_kind") or it.get("source_url")):
                stats["total"] += 1
                stats["traced" if it.get("source_kind") == "corpus" else "untraced"] += 1
                continue
            f = (it.get("fact") or "").strip()
            if not f:
                continue
            stats["total"] += 1
            toks = _tokens(f)
            if not toks:
                continue
            best_url, best_hits = "", 0
            for url, content in good_rows:
                hits = sum(1 for t in toks if t in content)
                if hits > best_hits:
                    best_url, best_hits = url, hits
            # 溯源要求 ≥2 token 命中，或 1 个 ≥4 字 token 命中（防"香格里拉"等泛词误配）
            if best_url and (best_hits >= 2 or (best_hits == 1 and max(len(t) for t in toks) >= 4)):
                it["source_url"] = best_url
                it["source_kind"] = "corpus"
                stats["traced"] += 1
            else:
                it["source_url"] = ""
                it["source_kind"] = "verified"
                stats["untraced"] += 1
            it["captured_at"] = captured_at
    return facts, stats


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        row = (await db.execute(text(
            "SELECT gt_facts_json FROM collection_runs WHERE id=:rid"),
            {"rid": args.run_id})).first()
        if not row or not row.gt_facts_json:
            print(f"错误: run {args.run_id} 无 gt_facts_json")
            await engine.dispose()
            sys.exit(1)
        gj = json.loads(row.gt_facts_json) if isinstance(row.gt_facts_json, str) else row.gt_facts_json
        captured_at = gj.get("last_verified_at") or gj.get("generated_at") or ""
        facts_rows = (await db.execute(text("""
            SELECT url, content_text FROM search_results
            WHERE content_text IS NOT NULL AND content_text<>''
              AND (content_layer IS NULL OR content_layer='fact')
        """))).fetchall()
        new_gj, stats = annotate_facts(gj, list(facts_rows), captured_at, args.force)
        await db.execute(text("UPDATE collection_runs SET gt_facts_json=:g WHERE id=:rid"),
                         {"g": json.dumps(new_gj, ensure_ascii=False), "rid": args.run_id})
        await db.commit()
    print(f"gt_facts_json 可追溯回填：总 {stats['total']} 条，语料溯源 {stats['traced']}，"
          f"非语料（联网/人工核验）{stats['untraced']}，captured_at={captured_at}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
