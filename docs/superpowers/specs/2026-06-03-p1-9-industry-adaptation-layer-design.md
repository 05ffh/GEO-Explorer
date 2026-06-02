# P1-9: 行业适配层 — 设计规格

**日期:** 2026-06-03
**状态:** 待审阅
**父项:** P1 功能增强 (P1-9)

## 动机

当前 GEO Explorer 的 KPI 权重、模板选择、幻觉检测阈值对所有品牌使用相同配置。不同行业（餐饮、旅游、SaaS、金融）对"品牌可见度"的定义不同——餐饮关注 citation，SaaS 关注 sov（share of voice），旅游关注 cross_platform_consistency。P1-9 提供可配置的行业适配层，使分析口径按行业差异调整。

## 设计决策

| 决策 | 选择 |
|------|------|
| 配置载体 | `IndustryTemplate` 扩展 + 行业级 JSON 配置 |
| 适配内容 | KPI 权重、模板推荐、幻觉检测阈值、competitor_rules |
| 生效方式 | 品牌关联 `industry_template_id`，采集/分析时读取行业配置 |
| 配置优先级 | 行业配置 > 全局默认，品牌级覆盖 > 行业配置 |

---

## 1. 行业配置能力

### 1.1 KPI 权重（行业差异化最重要的维度）

每个行业可配置 5 核心 KPI 的权重（总和 1.0）：

```json
{
  "kpi_weights": {
    "accuracy": 0.30,
    "completeness": 0.15,
    "citation": 0.10,
    "sov": 0.25,
    "first_rec": 0.20
  }
}
```

**预设示例：**

| 行业 | accuracy | completeness | citation | sov | first_rec |
|------|----------|-------------|----------|-----|-----------|
| 餐饮连锁 | 0.15 | 0.15 | **0.40** | 0.15 | 0.15 |
| SaaS | 0.20 | 0.20 | 0.10 | **0.35** | 0.15 |
| 旅游酒店 | 0.20 | 0.10 | 0.15 | 0.20 | **0.35** |
| 金融 | **0.35** | 0.25 | 0.20 | 0.10 | 0.10 |
| 通用（默认） | 0.30 | 0.15 | 0.10 | 0.25 | 0.20 |

### 1.2 幻觉检测阈值

```json
{
  "hallucination_thresholds": {
    "n_gram_similarity_min": 0.05,
    "n_gram_similarity_max": 0.35,
    "llm_fallback_enabled": true,
    "high_risk_fields": ["official_name", "founding_year", "headquarters"],
    "field_signal_overrides": {
      "official_name": ["legal_name", "trademark_name"],
      "industry": ["sector", "vertical"]
    }
  }
}
```

### 1.3 模板策略

```json
{
  "template_strategy": {
    "min_questions_per_qtype": 3,
    "max_questions_per_qtype": 8,
    "required_qtypes": ["brand_definition", "brand_trust"],
    "recommended_qtypes": ["brand_comparison", "scenario_solution"],
    "brand_directed_min": 0.5
  }
}
```

## 2. 配置优先级与合并

```
品牌级覆盖 (Brand.industry_config_override)
  ↓ 覆盖
行业配置 (IndustryTemplate.kpi_weights / thresholds / template_strategy)
  ↓ 覆盖
全局默认 (config.py 中的硬编码默认值)
```

合并逻辑：深合并 JSON，品牌级覆盖只替换明确指定的 key。

## 3. 数据模型

- `IndustryTemplate` 现有字段 `kpi_weights`（已有，用于模板推荐）可直接复用和增强
- 新增 `hallucination_thresholds JSONB` — 行业级幻觉检测阈值
- 新增 `template_strategy JSONB` — 行业级模板策略
- `Brand` 新增 `industry_config_override JSONB` — 品牌级覆盖

## 4. 消费点

| 模块 | 如何使用行业配置 |
|------|-----------------|
| `analyzer/pipeline.py` | `compute_and_save_metrics()` 读取行业 KPI 权重计算加权总分 |
| `analyzer/hallucination.py` | `_classify_relevance()` / `verify_claim()` 读取 `high_risk_fields` 和 `field_signal_overrides` |
| `collector/engine.py` | `run_collection()` 读取行业 `template_strategy` 筛选推荐模板 |
| `reports/health_score.py` | 健康分计算使用行业 KPI 权重 |

## 5. API

```
GET  /api/industries                          — 列出所有行业
GET  /api/industries/{id}                     — 行业配置详情
PUT  /api/industries/{id}/kpi-weights         — 更新 KPI 权重
PUT  /api/industries/{id}/thresholds          — 更新幻觉检测阈值
PUT  /api/industries/{id}/template-strategy   — 更新模板策略
POST /api/brands/{id}/industry-config         — 品牌级覆盖
```

## 6. Migration

- `industry_templates` 新增 `hallucination_thresholds JSONB`，`template_strategy JSONB`
- `brands` 新增 `industry_config_override JSONB`
- 为现有行业模板填充默认值

## 7. 测试

| 场景 | 覆盖点 |
|------|--------|
| 餐饮行业 KPI 权重使 citation 占比 40% | `test_restaurant_kpi_weights` |
| 品牌覆盖行业 KPI 配置 | `test_brand_override_kpi_weights` |
| 行业阈值控制幻觉检测严格度 | `test_industry_hallucination_thresholds` |
| 全球默认兜底 | `test_fallback_to_global_defaults` |
| 深合并 JSON 逻辑 | `test_deep_merge_config` |
| 行业模板策略约束采集问题数 | `test_template_strategy_limits_questions` |
