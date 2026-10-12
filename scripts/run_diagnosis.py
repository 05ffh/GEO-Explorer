"""完整诊断编排：P2（GT 采集+定位）→ 主 agent 定位确认 → P3（测量）。

保证环环相扣：
- P2 必须先跑（GT 采集 → positioning_json 带 positioned_at）
- P3 强制校验定位新鲜（过时/缺失 → 拒绝，提示先跑 P2）
- 主 agent 介入点：P2 后确认定位（档位/竞品/人群），P3 后判 needs_agent 回填

用法：
  python scripts/run_diagnosis.py 香格里拉 福州 --stage p2   # GT 采集 + 定位，打印介入点清单
  python scripts/run_diagnosis.py 香格里拉 福州 --stage p3   # 测量（校验定位新鲜），打印介入点清单
"""
import asyncio
import sys

from scripts.run_gt_diagnosis import main as p2_main
from scripts.run_measure import main as p3_main


def main():
    if len(sys.argv) < 3:
        print("用法: python scripts/run_diagnosis.py <品牌> <城市> --stage p2|p3")
        sys.exit(1)
    brand, city = sys.argv[1], sys.argv[2]
    stage = "p2"
    rest = sys.argv[3:]
    for i, a in enumerate(rest):
        if a.startswith("--stage="):          # --stage=p3
            stage = a.split("=")[1]
            break
        if a == "--stage" and i + 1 < len(rest):  # --stage p3（空格分隔）
            stage = rest[i + 1]
            break

    if stage == "p2":
        asyncio.run(p2_main(brand, city, None))
        print("\n[编排] P2 完成（GT 采集 + 定位，positioning_json 已带 positioned_at）。")
        print("[编排] 主 agent 读上面介入点清单，确认定位（档位/竞品/人群/可信度/负面终判），补竞品用:")
        print("[编排]   python scripts/write_competitor.py <run_id> <竞品名>")
        print("[编排] 定位确认后，跑测量: python scripts/run_diagnosis.py {} {} --stage p3".format(brand, city))
    elif stage == "p3":
        asyncio.run(p3_main(brand, city, None))
        print("\n[编排] P3 完成（测量，measurement_json status=partial）。子 agent 判 needs_agent 题后 finalize_hit --apply 回填六字段。")
    else:
        print(f"未知阶段: {stage}（p2 / p3）")
        sys.exit(1)


if __name__ == "__main__":
    main()
