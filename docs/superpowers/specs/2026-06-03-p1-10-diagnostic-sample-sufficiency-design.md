# P1-10: 诊断有效样本数 — 设计规格

**日期:** 2026-06-03
**状态:** 待审阅
**父项:** P1 功能增强 (P1-10)

## 动机

当前 `report_publishable` 判断是二值的——发布或不发布。但"不能发布"的原因被混在一起：采集完全失败（0 条 QueryResult）和采集部分成功但样本不够可靠分析是两种完全不同的情况。P1-10 使诊断系统能区分"无数据"和"数据不足"，并在报告质量摘要中提供细粒度样本充分度评估。

## 设计决策

| 决策 | 选择 |
|------|------|
| 样本充分度维度 | 按平台 × question_type × KPI 三个维度分别评估 |
| 判定标准 | 可配置阈值：每平台 >= N 条成功、每 qtype >= M 条成功 |
| 与现有系统关系 | 扩展 `report_quality_summary_json` 新增 `sample_sufficiency` 节，不影响现有 `report_publishable` |
| 展示 | 报告首页显示样本充分度仪表盘，按维度标注 ✅/⚠️/❌ |

---

## 1. 数据模型

### 1.1 新增：SampleSufficiencyConfig

`src/schemas/sample_sufficiency.py`:

```python
class SampleSufficiencyConfig(BaseModel):
    schema_version: str = "sample_sufficiency_v1"
    min_queries_per_platform: int = 3       # 每平台最少有效 QueryResult
    min_queries_per_qtype: int = 2           # 每 question_type 最少有效
    min_queries_per_kpi: int = 5             # 每 KPI 最少有效样本
    min_total_queries: int = 10              # 全局最少有效 QueryResult
    min_platforms: int = 2                   # 最少成功平台数
    require_all_platforms: bool = False      # 是否要求所有平台都有数据
```

### 1.2 新增：SampleSufficiencyResult

```python
class SampleSufficiencyResult(BaseModel):
    data_status: str          # "ok" | "no_data" | "insufficient" | "partial"
    total_valid_queries: int
    total_platforms: int
    successful_platforms: int
    platform_breakdown: dict  # {platform: {success, error, total}}
    qtype_breakdown: dict     # {qtype: {success, min_required, sufficient}}
    kpi_breakdown: dict       # {kpi: {eligible_queries, min_required, sufficient}}
    warnings: list[str]
    recommendation: str       # human-readable recommendation
```

data_status 枚举:
- `ok` — 所有维度达标
- `no_data` — 无任何成功 QueryResult（采集完全失败或未开始）
- `insufficient` — 有数据但至少一个关键维度不达标
- `partial` — 部分平台无数据但其他平台达标

---

## 2. 集成点

### 2.1 `analyzer/pipeline.py` — `compute_and_save_metrics()` 末尾

```
1. 收集所有 QueryResult (platform, status, template_id)
2. 按 platform / question_type 聚合
3. 应用 SampleSufficiencyConfig 判定
4. 写入 run.report_quality_summary_json.sample_sufficiency
```

### 2.2 `analyzer/quality.py` — `compute_report_publishable()`

- `data_status = no_data` → `report_publishable = false`，首要阻断原因
- `data_status = insufficient` → `report_publishable = false`，附带详细维度说明
- `data_status = partial` → `report_publishable` 取决于其他质量指标

### 2.3 `reports/diagnostic.py` — 报告首页

- 新增"样本充分度"区块
- 显示 platform / qtype / KPI 三维度的 ✅⚠️❌
- 推荐操作：补充采集 / 添加平台 / 当前可用

### 2.4 `CollectionRun` 扩展

- `report_quality_summary_json.sample_sufficiency` — 快照

---

## 3. 阈值来源

```
品牌级 industry_config_override.sample_sufficiency (最高优先级)
  ↓
行业配置 IndustryTemplate.sample_sufficiency
  ↓
全局默认 SampleSufficiencyConfig()
```

通过 P1-9 的 `resolve_industry_config()` 统一读取。

---

## 4. API

```
GET /api/runs/{run_id}/sample-sufficiency
→ SampleSufficiencyResult
```

---

## 5. Migration

- `industry_templates` 新增 `sample_sufficiency JSONB`
- `brands.industry_config_override` 已存在（P1-9），支持 `sample_sufficiency` 字段
- 无需新列：`CollectionRun.report_quality_summary_json` 结构中新增 `sample_sufficiency` 键

---

## 6. 测试

| 场景 | 覆盖点 |
|------|--------|
| 全平台全 qtype 达标 | `test_all_dimensions_sufficient` |
| 0 QueryResult | `test_no_data_status` |
| 仅 1 平台达标 | `test_insufficient_min_platforms` |
| 某 qtype 样本不足 | `test_qtype_insufficient` |
| KPI eligible 样本不足 | `test_kpi_insufficient_eligible` |
| 行业配置覆盖阈值 | `test_industry_threshold_override` |
| data_status=no_data 阻断发布 | `test_no_data_blocks_publish` |
| data_status=insufficient 阻断发布 | `test_insufficient_blocks_publish` |
| 报告页面展示样本仪表盘 | `test_report_shows_sufficiency_dashboard` |
