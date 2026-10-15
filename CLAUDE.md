# GEO Explorer

品牌 AI 可见度诊断工具（纯 CLI）。监测 DeepSeek / Kimi / 豆包 / 文心一言四个 AI 平台上品牌的推荐情况，量化可见度、**归因**（为什么被推 / 不被推），并给出内容优化方向。

## 链路与用法

| 步 | 做什么 | 命令 |
|---|---|---|
| 1 诊断入口 | 建诊断单元 + GT 采集 + 定位 | `scripts/run_gt_diagnosis.py <品牌> <城市>` |
| 2 测量 | 4 平台采集 AI 回答 | `scripts/run_measure.py <品牌> <城市> [run_id]` |
| 3 命中判定 | 判每条回答推没推甲方 | `scripts/finalize_hit.py --generate <run_id>` → 判定 → `--apply <run_id>` |
| 4 归因提取 | 判 AI 表述的维度 + 性质 | `scripts/finalize_attribution.py generate <run_id>` → 提取 → `apply <run_id>` |
| 5 收口盖章 | 锁定一版（重判 = 新快照，不覆盖） | `scripts/finalize_v4.py seal <run_id>` |
| 6 复测收敛 | 多轮重跑，只留稳定结论 | `scripts/remeasure.py ... --round N` + `scripts/converge.py <run_id>` |
| 7 报告 | 生成 HTML / PDF 诊断报告 | `scripts/build_geo_report.py <run_id> [--pdf]` |
| 8 导出 | 生成 md 回答清单 | `python -m scripts.export_answers <run_id>` |

**辅助**：CDP 抓国内 OTA（携程 / 同程 / 飞猪）补甲方事实 —— `scripts/fetch_ota_cdp.py`。

## 关键概念

- **命中率** —— AI 推荐名单里有没有甲方
- **GT 事实清单**（`gt_facts_json`）—— 甲方"有什么"的证据库，归因第一判决依据
- **真劣势** vs **甲方有·AI 未引**（= 铺内容靶点）
- **复测收敛** —— 多轮重跑，只采信跨轮稳定的结论

## 工作流

spec → 审阅 → Build → 验证。TDD。

## 测试

`.venv/bin/pytest tests/`

## 目录结构

```
scripts/        链路入口
src/collector/  采集 + 命中判定 + 归因 + 收敛
src/report/     诊断报告（数据桥 / 渲染 / 叙述）
src/search/     两路搜索后端
src/adapters/   四平台 AI 适配层
src/models/     DB 模型
src/gt/         GT 事实清单 + 主题块引擎
alembic/        DB 迁移
```

MIT License
