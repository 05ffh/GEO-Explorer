# Design: 采集→分析自动衔接 & 反思总结框架 (v2)

**日期:** 2026-05-29
**状态:** Approved (审定修正后)
**审阅:** AI 工程交付与数据管线架构评审专家 / GEO 产品架构负责人

---

## Section 1: 采集→分析自动衔接

### 问题

`run_collection()` 和 `compute_and_save_metrics()` 各自独立，采集完成后不自动触发分析。API 触发采集端点直接在 HTTP 请求中 await 88 个查询（2-5 分钟），不可用。

### 设计

**链路:** HTTP → Celery Task → run_collection(auto_analyze=True) → run_analysis_for_collection()

| 决策 | 理由 |
|---|---|
| API 返回 202 Accepted + task_id | 88 个查询不能绑在 HTTP 请求上 |
| 采集提交后在同一 Celery task 内调 run_analysis_for_collection() | commit 边界隔离——采集数据已落库，分析挂不影响采集 |
| run_collection() 接受 auto_analyze 参数（默认 True） | CLI/测试可关闭分析副作用；一处设置覆盖所有路径 |
| run_analysis_for_collection() 独立函数 | 支持单独重跑分析，不依赖重跑采集 |
| 分析包在 try/except 内，含 traceback + 结构化日志 | 失败不往上抛但完整可追溯 |

### 1.1 CollectionRun 状态机

拆分单一 `status` 为双字段：

```
collection_status: pending | running | completed | partial | failed
analysis_status:  not_started | running | completed | failed | skipped
```

状态流转：

```
[触发采集] → collection_status=running, analysis_status=not_started
    ↓
[采集完成] → collection_status=completed|partial|failed
    ↓ (completed/partial + 达到阈值)
[自动触发分析] → analysis_status=running
    ↓
[分析完成] → analysis_status=completed|failed
```

若 `collection_status=failed` 或未达阈值 → `analysis_status=skipped`

### 1.2 错误隔离

```python
# CollectionRun 新增字段
collection_status: str          # pending|running|completed|partial|failed
analysis_status: str            # not_started|running|completed|failed|skipped
collection_error_summary: dict | None   # 平台级错误分布
analysis_error_message: str | None
analysis_error_trace: str | None
collection_completed_at: datetime | None
analysis_started_at: datetime | None
analysis_completed_at: datetime | None
```

Dashboard 分别展示：本轮采集是否完整、哪个平台失败、分析是否成功、若分析失败是否仍可查看原始 QueryResult。

### 1.3 Partial 触发分析阈值

```python
# config.py 新增
MIN_SUCCESS_PLATFORMS_FOR_ANALYSIS = 2
MIN_SUCCESS_QUERIES_FOR_ANALYSIS = 10
```

触发条件：

```
collection_status in ("completed", "partial")
AND success_platform_count >= MIN_SUCCESS_PLATFORMS_FOR_ANALYSIS
AND success_query_count >= MIN_SUCCESS_QUERIES_FOR_ANALYSIS
```

未达阈值 → `analysis_status = "skipped"`，Dashboard 显示"本轮成功数据不足以进行有意义的分析"。

### 1.4 auto_analyze 开关

```python
async def run_collection(..., auto_analyze: bool = True):
    ...
    if auto_analyze and _should_analyze(run):
        await run_analysis_for_collection(run.id, run.organization_id, db)

async def run_analysis_for_collection(collection_run_id, org_id, db):
    """独立函数，支持单独重跑分析。"""
    try:
        ...
    except Exception as e:
        # 更新 analysis_status + error_message + traceback
        # logger.exception(...)
```

### 1.5 数据血缘

| 模型 | collection_run_id | 当前状态 | 操作 |
|---|---|---|---|
| QueryResult | 已有 | NOT NULL FK | 不变 |
| MetricsSnapshot | 已有 | nullable FK | 写入时必填 |
| HallucinationResult | 无 | 通过 query_result_id 间接关联 | **新增**直接 FK |
| InsightSummary | 无 | 新模型 | **新增** FK |

HallucinationResult 增加 `collection_run_id` 的直接好处：Dashboard 查询"本轮采集检出多少幻觉"不需要 JOIN QueryResult。

---

## Section 2: 反思总结框架

### 2.1 工程过程元反思: `docs/retrospectives/`

```
docs/retrospectives/
├── INDEX.md       # 时间线索引: [日期] [标题](文件) — 一句话教训
├── TEMPLATE.md    # 5 段式: 问题/方案/结果/教训
└── YYYY-MM-DD-<topic>.md
```

**触发条件:** 卡了超过 30 分钟的问题、架构级决策、上线后发现的 bug

**执行绑定（写入 agentic worker 规则）:**
1. 任务开始前读取 `docs/retrospectives/INDEX.md`
2. 搜索与当前任务关键词相关的复盘记录
3. 在实现说明中列出已参考的教训
4. 若本次踩坑超过 30 分钟，新增 retrospective

### 2.2 数据层反思: Dashboard 采集摘要卡片

每次 CollectionRun + Analysis 完成后自动生成 InsightSummary，Dashboard 展示四栏：

```
┌─ 平台健康 ─────────────────────────────────────┐
│ DeepSeek ✅ 22/22 (5.2s)  豆包 ✅ 22/22 (7.1s) │
│ Kimi ⚠️ 9/22 (21.3s, 429限流)  文心 ❌ 未就绪 │
└────────────────────────────────────────────────┘

┌─ 品牌表现 (5 KPI 跨平台聚合) ─────────────────┐
│ SOV: 78%  首次推荐: 65%  准确率: 82%           │
│ 完整度: 71%  引用率: 43%  P0 幻觉: 2          │
└────────────────────────────────────────────────┘

┌─ 关键发现 ────────────────────────────────────┐
│ · DeepSeek 引用率仅 31%，建议增加官方链接       │
│ · 同一地址在 3 平台均错误 → P0，品牌自身问题   │
│ · Kimi 引用率最高(67%)但温度=1.0致回答不稳定   │
│                                                  │
│ 每条 insight 带 severity + confidence + evidence │
└────────────────────────────────────────────────┘

┌─ 本轮数据可信度 ─────────────────────────────┐
│ 采集完成度: 66/88  成功平台: 3/4              │
│ 可用于 KPI: 是  可跨平台判断: 是              │
│ 建议人工复核: P0 错误 3 条                     │
└────────────────────────────────────────────────┘
```

### 2.3 Insight 结构与可信度

```json
{
  "type": "cross_platform_p0_error | platform_diff | system_improvement",
  "title": "多个平台误判品牌行业归属",
  "severity": "P0",
  "confidence": "high",
  "evidence": [
    {"platform": "kimi", "query_result_id": "...", "claim": "..."},
    {"platform": "doubao", "query_result_id": "...", "claim": "..."}
  ],
  "interpretation": "多平台同时出错，更可能是品牌公开语义锚点不足。",
  "recommended_action": "优先修正官网首页和 About 页面中的品牌定位描述。"
}
```

可信度规则：

| 级别 | 条件 |
|---|---|
| high | 3+ 平台出现同一 P0/P1 问题 |
| medium | 2 平台出现同类问题 |
| low | 单平台问题或样本量不足 |

### 2.4 InsightSummary 数据模型

新版增加独立模型，避免 Dashboard 每次加载都实时计算：

```python
class InsightSummary(Base):
    __tablename__ = "insight_summaries"
    id: UUID PK
    organization_id: UUID FK
    brand_id: UUID FK
    collection_run_id: UUID FK
    platform_health_json: JSONB
    brand_performance_json: JSONB
    key_findings_json: JSONB       # list of insight dicts
    data_reliability_json: JSONB   # 采集完成度、可信度标记
    confidence_level: str          # overall: high|medium|low
    generated_at: datetime
```

### 2.5 优先级拆分

| 阶段 | 内容 |
|---|---|
| 本次 | 状态机 + 血缘 + auto_analyze + 采集摘要卡片 + InsightSummary 模型 |
| 本次 | retrospectives/ 目录 + TEMPLATE + Kimi 429 复盘 + 执行绑定 |
| 下次 | 多周趋势图（需 2+ 周数据） |
| 下次 | 竞品对比 Dashboard |
| 后续 | 系统健康仪表盘（API 延迟/成本/成功率） |

---

## Section 3: 平台限流通用机制

原设计将 Kimi 429 作为"顺手修"，现升级为通用平台限流：

```python
# config.py
PLATFORM_CONCURRENCY_LIMITS = {
    "kimi": 2, "deepseek": 4, "doubao": 4, "wenxin": 2,
}

PLATFORM_RETRY_CONFIG = {
    "kimi": {"max_retries": 2, "backoff_seconds": [2, 4]},
    "deepseek": {"max_retries": 2, "backoff_seconds": [1, 2]},
    "doubao": {"max_retries": 2, "backoff_seconds": [1, 2]},
    "wenxin": {"max_retries": 2, "backoff_seconds": [2, 4]},
}
```

QueryResult 记录限流详情：

```python
retry_count: int
rate_limited: bool
final_error_code: str
```

---

## Section 4: 改动范围与测试

### 4.1 文件改动

```
新增:
  src/analyzer/insights.py
  src/analyzer/collection_analysis.py    # run_analysis_for_collection()
  src/models/insight_summary.py
  docs/retrospectives/TEMPLATE.md
  docs/retrospectives/INDEX.md
  docs/retrospectives/2026-05-29-kimi-429-concurrency.md
  scripts/search_retrospectives.py       # 可选

修改:
  src/collector/engine.py                # +auto_analyze +平台并发 +重试
  src/collector/tasks.py                 # 微调返回信息
  src/api/collection_runs.py             # HTTP → Celery delay, 202
  src/analyzer/pipeline.py               # +insights 生成调用
  src/api/dashboard.py                   # 扩展返回 insights 数据
  src/templates/dashboard/index.html     # +采集摘要卡片
  src/models/collection_run.py           # 拆分状态 + 错误字段
  src/models/hallucination.py            # +collection_run_id FK
  src/models/metrics_snapshot.py         # collection_run_id 改为必填（若当前 nullable）
  src/models/query_result.py             # +rate_limited +final_error_code
  src/config.py                          # 平台限流配置 + 分析阈值
```

### 4.2 测试清单

**保留原有:**

| 测试 | 备注 |
|---|---|
| collection_triggers_analysis | 改为检查 analysis_status |
| analysis_failure_doesnt_kill_collection | 改为检查 collection_status 不变 |
| kimi_429_retry | 泛化为 platform_retry |
| per_platform_concurrency | 不变 |
| trigger_endpoint_returns_202 | 不变 |
| insights_cross_platform_p0 | 增加 confidence 字段检查 |
| insights_platform_diff | 不变 |
| insights_system_improvements | 不变 |

**新增:**

| 测试 | 目的 |
|---|---|
| collection_run_status_transition | 验证 collection_status 与 analysis_status 合法流转 |
| partial_below_threshold_skips_analysis | 数据不足时 analysis_status=skipped |
| analysis_not_duplicated_on_retry | Celery retry 不重复写 MetricsSnapshot |
| metrics_snapshot_has_collection_run_id | 验证指标血缘 FK 非空 |
| hallucination_has_collection_run_id | 验证幻觉记录血缘 |
| dashboard_summary_uses_latest_collection_run | Dashboard 不混用历史批次 |
| rerun_analysis_for_collection | 独立重跑分析不重复采集 |
| auto_analyze_false_skips_pipeline | CLI/测试可关闭自动分析 |

### 4.3 不改的范围

Celery beat 调度、Analyzer 6 个计算模块（sov/first_rec/accuracy/completeness/citation/hallucination）、Action Engine、Auth/Brand API、文心适配器。

---

## Section 5: 执行阶段

| 阶段 | 内容 |
|---|---|
| **1. 数据模型** | CollectionRun 状态机拆分 → HallucinationResult +collection_run_id → InsightSummary 新模型 → MetricsSnapshot FK 必填 → QueryResult 限流字段 → migration → 模型测试 |
| **2. 采集→分析衔接** | run_collection(auto_analyze=True) → run_analysis_for_collection() → 阈值检查 → 状态更新 + 错误记录 + 结构化日志 |
| **3. 异步 API** | POST /collections → Celery delay → 202 + task_id + collection_run_id |
| **4. 平台限流** | PLATFORM_CONCURRENCY_LIMITS + PLATFORM_RETRY_CONFIG → collector engine 按平台 Semaphore → 429 写入 QueryResult |
| **5. Insights + Dashboard** | generate_insights() → InsightSummary → Dashboard 四栏卡片（平台健康/品牌表现/关键发现/数据可信度）→ 空状态和部分失败状态解释 |
| **6. Retrospectives** | Kimi 429 复盘 → 执行绑定规则 → 可选检索脚本 |
