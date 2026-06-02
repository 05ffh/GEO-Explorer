# P1-10: 诊断有效样本数 — 设计规格（修订版）

**日期:** 2026-06-03
**状态:** 已确认（含审阅补齐清单）
**父项:** P1 功能增强 (P1-10)

## 动机

`report_publishable` 是二值的，但不发布的原因被混在一起。P1-10 区分"无数据"和"数据不足"，按 platform × question_type × KPI 三维评估样本充分度。

## 设计原则（11 条硬约束）

1. **四层有效口径** — raw / success / valid_answer / metric_eligible 严格区分
2. **reasoning_content / template_invalid / empty_response 不得计入 valid_answer**
3. **KPI 分母复用 MetricResult.denominator_json** — 不另写逻辑
4. **qtype 使用模板版本快照** — 不读当前 QueryTemplate
5. **data_status 按 no_data → insufficient → partial → ok 状态机**计算
6. **partial 发布规则** — critical platform/qtype/kpi 缺失不得发布
7. **SampleSufficiencyConfig 接入 P1-9 IndustryConfig** — schema 校验
8. **SampleSufficiencyResult 含 config_snapshot + blocking_dimensions + actions**
9. **compute_report_publishable 转 blocking_reasons**
10. **报告首页说明"样本不足不等于品牌表现差"**
11. **API 默认读快照** — 行业配置更新不改变历史 run

---

## 1. 有效样本口径（P0-1）

```python
# 四层口径
raw_query_count        # 应采集的总 QueryResult 数
successful_query_count # 平台成功返回 (无 timeout/auth/rate_limit/empty)
valid_answer_count     # 有内容、template_valid、非系统错误
metric_eligible_count   # 满足 KPI eligibility 过滤的样本

# 排除规则
NOT valid_answer: reasoning_content | template_invalid | empty_response |
                  content_filtered | system_error
IS valid_answer:  answer_text 非空 AND template render_status=ok AND status=success
IS metric_eligible: valid_answer AND passes KPI eligibility filter
```

| 维度 | 使用口径 |
|------|---------|
| platform_breakdown | valid_answer_count |
| qtype_breakdown | valid_answer_count |
| kpi_breakdown | metric_eligible per KPI |
| total_valid_queries | valid_answer_count |

---

## 2. Pydantic Schema

### 2.1 SampleSufficiencyConfig（P0-3）

```python
class SampleSufficiencyConfig(BaseModel):
    schema_version: str = "sample_sufficiency_v1"
    min_queries_per_platform: int = Field(default=3, ge=0)
    min_queries_per_qtype: int = Field(default=2, ge=0)
    min_queries_per_kpi_default: int = Field(default=5, ge=0)
    min_queries_by_kpi: dict[str, int] = Field(default_factory=dict)    # P1-2
    min_total_queries: int = Field(default=10, ge=0)
    min_platforms: int = Field(default=2, ge=1)
    require_all_platforms: bool = False
    critical_platforms: list[str] = Field(default_factory=list)         # P0-8
    critical_qtypes: list[str] = Field(default_factory=list)
    critical_kpis: list[str] = Field(default_factory=list)
    min_queries_by_platform: dict[str, int] = Field(default_factory=dict) # P1-3
    min_queries_by_qtype: dict[str, int] = Field(default_factory=dict)   # P1-4
    optional_platforms: list[str] = Field(default_factory=list)
```

### 2.2 SampleSufficiencyResult（P0-2）

```python
class SampleSufficiencyResult(BaseModel):
    schema_version: str = "sample_sufficiency_result_v1"
    generated_at: str
    data_status: str  # ok | no_data | insufficient | partial
    config_snapshot: SampleSufficiencyConfig
    config_source: dict  # {industry_code, source_layers}
    total_raw_queries: int
    total_successful_queries: int
    total_valid_queries: int
    total_metric_eligible_queries: int
    total_platforms: int
    enabled_platforms: int
    successful_platforms: int
    platform_breakdown: dict  # P0-4
    qtype_breakdown: dict
    kpi_breakdown: dict   # P0-6
    blocking_dimensions: list[dict]
    warnings: list[dict]
    recommended_actions: list[dict]  # P0-10
    recommendation_summary: str
```

### 2.3 SampleSufficiencyAction（P0-10）

```python
class SampleSufficiencyAction(BaseModel):
    action_type: str  # retry_platform | add_templates | add_platform | collect_more | fix_auth | wait_rate_limit | review_gt
    target: str | None
    reason: str
    priority: str  # high | medium | low
```

---

## 3. data_status 状态机（P0-7）

```python
def compute_data_status(result, config) -> str:
    if result.total_valid_queries == 0:
        return "no_data"
    if result.total_valid_queries < config.min_total_queries:
        return "insufficient"
    if result.successful_platforms < config.min_platforms:
        return "insufficient"
    if config.require_all_platforms and result.successful_platforms < result.enabled_platforms:
        return "insufficient"
    if any critical_qtype insufficient:
        return "insufficient"
    if any critical_kpi insufficient:
        return "insufficient"
    if any critical_platform missing:
        return "insufficient"
    if any non-critical platform/qtype insufficient:
        return "partial"
    return "ok"
```

---

## 4. 各维度 breakdown

### 4.1 platform_breakdown（P0-4）

每平台:
```json
{
  "enabled": true, "attempted": true,
  "raw_queries": 23, "success_queries": 4, "valid_answer_queries": 3,
  "metric_eligible_queries": 2, "error_queries": 19,
  "error_breakdown": {"rate_limit": 19},
  "sufficient": false, "min_required": 3,
  "status": "rate_limited"
}
```
status: ok | insufficient | not_attempted | disabled | rate_limited | timeout_heavy | auth_failed | no_valid_answer | partial

### 4.2 qtype_breakdown（P0-5）

- 优先: `QueryResult.template_version_id → QueryTemplateVersion.question_type`
- Fallback: `CollectionRun.template_version_ids` snapshot
- Legacy: `QueryTemplate.question_type` + "legacy_template_qtype" warning

### 4.3 kpi_breakdown（P0-6）

```json
{
  "information_accuracy": {
    "denominator_type": "checkable_target_brand_claims",
    "denominator": 12, "min_required": 5, "sufficient": true
  }
}
```

直接读取 `MetricResult.denominator_json`。不存在则预计算。

---

## 5. partial 发布规则（P0-8）

**可发布**条件（全部满足）:
- `metric_eligible_coverage >= 60%`
- 核心 KPI denominator 全达标
- `successful_platforms >= min_platforms`
- 无 critical platform/qtype 缺失
- 无其他 hard block

**不可发布**: critical platform 缺失 | critical KPI 不足 | require_all_platforms 不满足

---

## 6. blocking_reasons / warnings（P0-9）

| Code | Severity | 含义 |
|------|----------|------|
| NO_DATA | block | 无成功 QueryResult |
| SAMPLE_TOTAL_TOO_LOW | block | total_valid < min_total |
| SAMPLE_PLATFORM_TOO_LOW | block | successful_platforms < min |
| SAMPLE_QTYPE_TOO_LOW | block | critical qtype 不足 |
| SAMPLE_KPI_TOO_LOW | block | critical KPI 分母不足 |
| SAMPLE_CRITICAL_PLATFORM_MISSING | block | critical 平台无数据 |
| SAMPLE_PARTIAL_PLATFORM | warning | 非关键平台不足 |
| SAMPLE_NON_CRITICAL_QTYPE_LOW | warning | 非关键 qtype 不足 |
| SAMPLE_LEGACY_TEMPLATE_VERSION | warning | 使用旧模板版本 |

---

## 7. P1-9 集成（P1-1）

`IndustryConfig` 新增:

```python
sample_sufficiency: SampleSufficiencyConfig = Field(default_factory=SampleSufficiencyConfig)
```

`resolve_industry_config(brand_id)` 返回合并后的 sample_sufficiency。

---

## 8. API

```
GET /api/runs/{run_id}/sample-sufficiency
  → 默认读 report_quality_summary_json.sample_sufficiency 快照
  → ?recompute=true 重新计算，标注 temporary，不覆盖快照
```

---

## 9. 集成点

- `analyzer/pipeline.py`: `compute_and_save_metrics()` → 调用 assessor → 写 snapshot
- `analyzer/quality.py`: `compute_report_publishable()` → data_status=no_data/insufficient → blocking
- `reports/diagnostic.py`: 报告首页"样本充分度"仪表盘 + "样本不足不等于品牌表现差"
- `CollectionRun.report_quality_summary_json.sample_sufficiency`

---

## 10. 实现顺序

| Step | 内容 |
|------|------|
| 0 | SampleSufficiencyConfig / Result / Action schema |
| 1 | 接入 P1-9 IndustryConfig |
| 2 | 四层有效样本口径 + compute_valid_query_counts() |
| 3 | platform_breakdown |
| 4 | qtype_breakdown (template_version 优先) |
| 5 | kpi_breakdown (复用 MetricResult.denominator_json) |
| 6 | data_status 状态机 |
| 7 | blocking_reasons / warnings / recommended_actions |
| 8 | 写入 report_quality_summary_json.sample_sufficiency |
| 9 | compute_report_publishable 接入 |
| 10 | API + 报告首页 |
| 11 | 测试 + 星巴克验证 |

---

## 11. 测试清单

- Schema: config_valid, threshold_rejects, require_all_platforms, industry_override
- 有效样本: reasoning_not_valid, template_invalid_not_valid, empty_not_valid, not_about_brand_valid_but_not_eligible
- Platform: ok/rate_limited/disabled/critical_missing_blocks/optional_missing_warns
- Qtype: template_version_used, legacy_fallback_warning, required_insufficient_blocks
- KPI: uses_denominator_json, zero_insufficient, kpi_specific_min, accuracy_checkable_claims
- Status: no_data → insufficient → partial → ok (5 cases)
- Publishable: no_data_blocks, insufficient_blocks_with_dimensions, partial_publishable_with_warning, critical_missing_blocks
- API: reads_snapshot, recompute_temporary
- Report: sufficiency_dashboard, explains_insufficient_not_brand_bad, recommended_actions

---

## 12. Done Definition

1. Schema 完成
2. P1-9 IndustryConfig 集成
3. 四层有效样本口径统一
4. platform/qtype/kpi breakdown 完成
5. data_status 状态机 + 测试
6. blocking_reasons / warnings / actions
7. report_quality_summary_json.sample_sufficiency 快照
8. compute_report_publishable 接入
9. API 读快照
10. 报告首页仪表盘 + 解释文案
11. 全部测试通过
12. 星巴克区分"平台限流导致样本不足" vs "品牌表现差"
