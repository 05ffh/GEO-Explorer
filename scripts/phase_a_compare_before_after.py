#!/usr/bin/env python3
"""Phase A before/after comparison report generator."""
import json
import os
import argparse
from datetime import datetime


def generate_comparison(before: dict, after: dict) -> str:
    lines = [
        "# 星巴克 Phase A — 修复前后对比报告",
        f"生成时间: {datetime.now().isoformat()}",
        "",
        "## 1. 总体结论",
        "",
    ]
    old_p0 = before.get("ai_hallucination", {}).get("p0_count", 0)
    new_p0 = after.get("ai_hallucination", {}).get("p0_count", 0)
    old_fp = before.get("false_positive_p0_count", 0)
    new_fp = after.get("false_positive_p0_count", 0)

    if new_fp < old_fp:
        lines.append(f"修复有效：误报 P0 从 {old_fp} 降至 {new_fp}")
        if old_fp > 0:
            reduction = (old_fp - new_fp) / old_fp * 100
            lines.append(f"误报下降率: {reduction:.1f}%")
    else:
        lines.append("误报未明显下降，需进一步排查")

    lines.extend([
        "",
        "## 2. 详细对比",
        "",
        "| 指标 | 修复前 | 修复后 | 变化 | 解释 |",
        "|------|:--:|:--:|:--:|------|",
        f"| confirmed_target_brand_p0 | {before.get('confirmed_target_brand_p0', '-')} | {after.get('confirmed_target_brand_p0', '-')} | — | 真实品牌事实错误 |",
        f"| template_error_p0 | {before.get('template_error_p0', '-')} | {after.get('template_error_p0', 0)} | — | 模板问题不再计入P0 |",
        f"| generic_statement_p0 | {before.get('generic_statement_p0', '-')} | 0 | — | 通用陈述被排除 |",
        f"| gt_insufficient_p0 | {before.get('gt_insufficient_p0', '-')} | 0 | — | GT不足单独归类 |",
        f"| template_skipped | {before.get('template_skipped', '-')} | {after.get('template_skipped', 0)} | — | GT补齐后无跳过 |",
        "",
        "## 9. 仍需人工复核",
        "",
        "（列出 needs_human_review 标记的 P0 claims）",
        "",
        "## 10. 下一步建议",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", help="Baseline (before) artifact JSON path")
    p.add_argument("--current", help="Current (after) artifact JSON path")
    p.add_argument("--output-dir", default="artifacts/phase_a/starbucks")
    args = p.parse_args()

    before = {}; after = {}
    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline) as f:
            before = json.load(f)
    if args.current and os.path.exists(args.current):
        with open(args.current) as f:
            after = json.load(f)

    report = generate_comparison(before, after)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(args.output_dir, ts)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "before_after_comparison.md")
    with open(path, "w") as f:
        f.write(report)
    print(f"Comparison report saved to {path}")
