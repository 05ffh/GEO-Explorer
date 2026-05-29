"""Export Content Packages as deliverable files (.md + .json-ld)."""

import json
import os
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

PUBLISH_GUIDE = """## 发布流程
1. 逐件审核内容是否与品牌事实一致
2. 将 Markdown 内容发布到官网对应页面（如 /about, /faq）
3. 将 JSON-LD 代码嵌入页面 `<head>` 标签内
4. 使用 Google Rich Results Test 验证结构化数据
5. 提交 URL 到 Google Search Console 加速索引
6. 2-4 周后重新触发 GEO 采集，验证 AI 认知改善
"""


async def export_content_packages(
    brand_name: str,
    brand_id: str,
    db: AsyncSession,
    output_dir: str = "reports",
) -> dict:
    """Export all draft Content Packages for a brand as publishable files."""
    pkgs = (await db.execute(text("""
        SELECT cp.id, cp.content_items, cp.schema_items, cp.publishing_checklist,
               cp.fact_check_report, cp.status, cp.created_at,
               ap.priority, ap.action_type, ap.correct_ground_truth, ap.suggested_content_type
        FROM content_packages cp
        LEFT JOIN action_plans ap ON cp.action_plan_id = ap.id
        WHERE cp.brand_id = :bid AND cp.status = 'draft'
        ORDER BY CASE ap.priority WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 ELSE 3 END
    """), {"bid": brand_id})).fetchall()

    if not pkgs:
        return {"exported": 0, "dir": None, "files": []}

    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    safe_name = brand_name.replace(" ", "_").replace("/", "_")
    out_dir = os.path.join(output_dir, f"{safe_name}_{date_str}_content_packages")
    os.makedirs(out_dir, exist_ok=True)

    files = []
    for i, pkg in enumerate(pkgs):
        d = dict(pkg._mapping)
        field = (d.get("correct_ground_truth") or {}).get("field", f"item_{i}")
        priority = d.get("priority", "P2")
        content_type = d.get("suggested_content_type", "FAQ")

        # Build Markdown
        lines = [
            f"# {brand_name} - {field}",
            "",
            f"> 优先级: {priority} | 类型: {content_type} | 状态: {d['status']}",
            f"> 生成时间: {d['created_at']}",
            "",
        ]
        for item in d["content_items"]:
            lines.append(item.get("body", ""))
        lines.extend([
            "",
            "## Schema.org JSON-LD",
            "> 将以下代码复制到页面 `<head>` 标签内",
            "",
            "```html",
            '<script type="application/ld+json">',
            json.dumps(d["schema_items"][0] if d["schema_items"] else {}, ensure_ascii=False, indent=2),
            "</script>",
            "```",
            "",
            "## 发布检查清单",
        ])
        for item in d["publishing_checklist"]:
            checked = "✓" if item.get("checked") else "☐"
            lines.append(f"- [{checked}] {item.get('item')}")

        # Save Markdown
        safe_field = field.replace("/", "_")
        md_filename = f"content_{i+1:02d}_{safe_field}.md"
        md_path = os.path.join(out_dir, md_filename)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # Save pure JSON-LD
        json_filename = f"content_{i+1:02d}_{safe_field}_schema.json"
        json_path = os.path.join(out_dir, json_filename)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(d["schema_items"], f, ensure_ascii=False, indent=2)

        files.append({
            "field": field, "priority": priority, "type": content_type,
            "md": os.path.abspath(md_path),
            "json_ld": os.path.abspath(json_path),
        })

    # Index README
    idx = [
        f"# {brand_name} Content Packages ({len(pkgs)} 件)",
        "",
        "| # | 字段 | 优先级 | 类型 | 内容文件 | Schema |",
        "|---|------|--------|------|----------|--------|",
    ]
    for i, f in enumerate(files):
        idx.append(f"| {i+1} | {f['field']} | {f['priority']} | {f['type']} | "
                   f"[MD]({os.path.basename(f['md'])}) | [JSON]({os.path.basename(f['json_ld'])}) |")
    idx.append("")
    idx.append(PUBLISH_GUIDE)

    idx_path = os.path.join(out_dir, "README.md")
    with open(idx_path, "w", encoding="utf-8") as f:
        f.write("\n".join(idx))

    return {
        "exported": len(pkgs),
        "dir": os.path.abspath(out_dir),
        "index": os.path.abspath(idx_path),
        "files": files,
    }
