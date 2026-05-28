# Design: 采集→分析自动衔接 & 反思总结框架

**日期:** 2026-05-29
**状态:** Approved

---

## Section 1: 采集→分析自动衔接

### 问题

`run_collection()` 和 `compute_and_save_metrics()` 各自独立，采集完成后不自动触发分析。同时 API 触发采集端点直接在 HTTP 请求中 await 88 个查询（2-5 分钟），不可用。

### 设计

**链路:** HTTP → Celery Task → run_collection() → compute_and_save_metrics()

| 决策 | 理由 |
|---|---|
| API 返回 202 Accepted + task_id | 88 个查询不能绑在 HTTP 请求上 |
| 采集和分析在同一 Celery task 内串行 | 分析只需 2-3 秒，且 commit 边界隔离——采集数据已落库，分析挂不影响采集 |
| run_collection() 末尾直接调用 pipeline | 一处改动覆盖所有路径：API 手动、Celery beat 定时、CLI 调试 |
| 状态 completed 或 partial 都触发分析 | partial 至少有 2-3 个平台的数据值得分析 |
| 分析包在 try/except 内 | 失败写入 CollectionRun.error_message，不往上抛 |

### 改动文件

1. **`src/api/collection_runs.py`** — 触发端点改为 `collect_brand_task.delay()`，返回 202 + task_id
2. **`src/collector/engine.py`** — `run_collection()` 末尾 commit 后调用 `compute_and_save_metrics()`
3. **`src/collector/tasks.py`** — 无需改动（已调 run_collection()，自动获得分析能力）

### Kimi 429 修复（顺手修）

- 平台级并发上限: `{"kimi": 2, "deepseek": 4, "doubao": 4, "wenxin": 2}`
- 429 自动重试: 最多 2 次，退避 `(retry_count + 1) * 2` 秒

---

## Section 2: 反思总结框架

### 2.1 工程过程元反思: `docs/retrospectives/`

```
docs/retrospectives/
├── INDEX.md       # 时间线索引，格式: [日期] [标题](文件) — 一句话教训
├── TEMPLATE.md    # 5 段式模板: 问题/方案/结果/教训
└── YYYY-MM-DD-<topic>.md
```

**触发条件:** 卡了超过 30 分钟的问题、架构级决策、上线后发现的 bug

**规则:** 每次新任务开始前扫 INDEX.md 中的相关教训

### 2.2 数据层反思: Dashboard 采集摘要卡片

每次 CollectionRun + Analysis 完成后自动生成，三栏结构：

- **平台健康** — 每个平台的成功率、平均延迟、错误分布
- **品牌表现** — 5 KPI 跨平台聚合值
- **关键发现** — 跨平台交叉（同一 GT 字段多平台错误 → 品牌自身问题）、平台差异（引用率等）、系统改进生效项

**生成逻辑:** 新增 `src/analyzer/insights.py::generate_insights()`，从 MetricsSnapshot.details、HallucinationResult、CollectionRun、retrospectives/INDEX.md 中提取数据。

### 2.3 优先级拆分

| 阶段 | 内容 |
|---|---|
| 本次 | 采集→分析自动衔接 + insights 生成 + 摘要卡片 |
| 本次 | retrospectives/ 目录 + TEMPLATE + Kimi 429 复盘 |
| 下次 | 多周趋势图（需 2+ 周数据） |
| 下次 | 竞品对比 Dashboard |
| 后续 | 系统健康仪表盘（API 延迟/成本/成功率） |

---

## Section 3: 改动范围与测试

### 文件改动

```
修改 (5): src/collector/engine.py, src/collector/tasks.py,
          src/api/collection_runs.py, src/analyzer/pipeline.py,
          src/api/dashboard.py, src/templates/dashboard/index.html
新增 (4): src/analyzer/insights.py,
          docs/retrospectives/{TEMPLATE,INDEX}.md,
          docs/retrospectives/2026-05-29-kimi-429-concurrency.md
```

### 测试清单 (8 tests)

| 测试 | 需要 DB |
|---|---|
| collection_triggers_analysis | 是 |
| analysis_failure_doesnt_kill_collection | 是 |
| kimi_429_retry | 否 |
| per_platform_concurrency | 否 |
| trigger_endpoint_returns_202 | 是 |
| insights_cross_platform_p0 | 是 |
| insights_platform_diff | 是 |
| insights_system_improvements | 否 |

### 不改的范围

Celery beat 调度、Analyzer 6 个计算模块、Action Engine、Auth/Brand API、文心适配器。
