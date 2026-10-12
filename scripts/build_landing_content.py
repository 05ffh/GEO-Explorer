"""P4 落地内容·主题块渲染 CLI（2026-09-22）。

读 collection_run.gt_facts_json → 渲染全主题块（确定性）→ 写 output/landing_*.md。
用法：
  PYTHONPATH=. .venv/bin/python scripts/build_landing_content.py <run_id> [--brand 名称] [--out 路径]
"""
import asyncio
import datetime
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.gt.theme_blocks import render_theme_blocks


def _render_md(brand: str, blocks: list[dict], closed: list[str]) -> str:
    L = [f"# {brand} · P4 落地内容（主题块，v0.1 确定性渲染）", ""]
    for b in blocks:
        layer = {"attribute": "属性层", "scenario": "场景层", "brand": "品牌特有"}[b["layer"]]
        L += [f"## {b['name']}（{layer}）", ""]
        L.append("【回答的问题】" + " / ".join(b["questions"]) + "\n")
        L.append(f"[直接答案] {b['direct']}\n")
        for it in b["facts"]:
            L.append(f"- {it['text']}")
            if it["limit"]:
                L.append(f"  ↳ 限制：{it['text']}")
        if b["who_for"]:
            L.append(f"\n▍适合谁：{b['who_for']}")
        if b["numbers"]:
            L.append("\n▍数字速览：")
            L += [f"- {t}" for t in b["numbers"][:6]]
        L += ["", "---", "【证据备注·不对外】", ""]
        for it in b["facts"]:
            meta = f"来源:{it['url']}" if it["url"] else f"来源:{it['tier']}"
            if it["captured"]:
                meta += f"｜核验:{it['captured']}"
            if it["weak"]:
                meta += "｜⚠️弱证据·联网核验无单页溯源，铺前确认"
            L.append(f"- {it['text'][:40]}…（{meta}）")
        L.append("")
    if closed:
        L += ["## 已停业/下线排除项（不进铺放，防 AI 复述旧信息）", ""]
        L += [f"- {c}" for c in closed] + [""]
    L.append(f"生成时间：{datetime.date.today().isoformat()}")
    return "\n".join(L)


async def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    run_id = sys.argv[1]
    brand = "该酒店"
    out = None
    if "--brand" in sys.argv:
        brand = sys.argv[sys.argv.index("--brand") + 1]
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]

    engine = create_async_engine(settings.database_url, connect_args={"timeout": 5})
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT gt_facts_json FROM collection_runs WHERE id=:r"), {"r": run_id})).fetchone()
    await engine.dispose()
    if not row:
        print(f"错误: run {run_id} 不存在")
        return 1
    blocks, closed = render_theme_blocks(row[0] or {}, brand)
    if not blocks:
        print("无可用主题块（gt_facts_json 为空？）")
        return 1
    md = _render_md(brand, blocks, closed)
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"已写 {out}")
    else:
        print(md)
    print(f"\n=== 汇总：{len(blocks)} 块 / {sum(len(b['facts']) for b in blocks)} 条事实 / 停业排除 {len(closed)} 条")
    for b in blocks:
        print(f"  [{b['layer']}] {b['name']}: {len(b['facts'])} 事实")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
