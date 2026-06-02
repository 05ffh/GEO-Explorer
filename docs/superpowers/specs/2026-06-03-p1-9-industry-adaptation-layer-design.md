# P1-9: 行业适配层 — 设计规格（修订版）

**日期:** 2026-06-03
**状态:** 已确认（含审阅补齐清单）
**父项:** P1 功能增强 (P1-9)

## 动机

GEO Explorer 各行业对"品牌可见度"的定义不同。P1-9 提供行业级可配置诊断口径，并确保配置可校验、可追溯、不可破坏历史报告。

## 设计原则（11 条硬约束）

1. **不允许自由 JSON 入生产** — 所有配置必须通过 Pydantic schema 校验
2. **KPI 权重强校验** — 总和必须 = 1.0，品牌级 kpi_weights override 必须完整提交
3. **deep merge 明确规则** — 数组/null/kpi_weights/field_signal_overrides 各有明文
4. **resolve_industry_config(brand_id)** — 返回 merged_config + source_layers + warnings
5. **CollectionRun 快照** — `industry_config_snapshot_json` 钉定，历史报告不受后续配置修改影响
6. **template_strategy 影响模板选择** — collector 输出 selection summary
7. **hallucination_thresholds 影响 detector** — high_risk_fields 来自 GT Field Registry
8. **competitor_rules 完整** — 影响竞品模板/SOV/first_rec/报告
9. **API 权限 + reason + expected_config_version + AuditLog**
10. **星巴克验证** — 识别为 restaurant_chain，citation=0.40 权重跑通
11. **全部测试** — schema/merge/权重/template_strategy/detector/API audit/snapshot

---

## 1. 行业分类体系（P0-1）

### 1.1 IndustryCode 枚举

`src/config/industry_profiles.py`:

```python
class IndustryCode(str, Enum):
    DEFAULT = "default"
    RESTAURANT_CHAIN = "restaurant_chain"
    SAAS = "saas"
    TRAVEL_HOTEL = "travel_hotel"
    FINANCIAL_SERVICES = "financial_services"
    EDUCATION_TRAINING = "education_training"
    CONSUMER_BRAND = "consumer_brand"
    RETAIL_ECOMMERCE = "retail_ecommerce"
    HEALTHCARE = "healthcare"
    AUTOMOTIVE = "automotive"
    REAL_ESTATE = "real_estate"

INDUSTRY_PROFILES = {
    IndustryCode.DEFAULT: IndustryProfile(
        industry_code="default",
        industry_group="general",
        display_name="通用",
        aliases=[],
    ),
    IndustryCode.RESTAURANT_CHAIN: IndustryProfile(
        industry_code="restaurant_chain",
        industry_group="local_consumer_service",
        display_name="餐饮连锁",
        aliases=["连锁餐饮", "咖啡餐饮", "餐饮零售", "快餐连锁"],
    ),
    # ... etc
}
```

### 1.2 品牌行业识别（P0-2）

三层优先级：
1. **手动优先**: `Brand.industry_template_id` 已存在 → 直接使用
2. **GT 辅助**: 从 GT v2 的 `industry`/`category`/`business_model_type` 字段映射
3. **规则建议**: 无绑定时输出 `suggested_industry_code` + confidence + evidence，需用户确认

新增 Brand 字段: `industry_detection_status`, `industry_detection_confidence`, `industry_detection_evidence_json`, `industry_confirmed_by`, `industry_confirmed_at`

---

## 2. 配置 Schema（P0-3）

### 2.1 新文件：`src/schemas/industry_config.py`

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class QuestionType(str, Enum):
    brand_definition = "brand_definition"
    brand_attribute = "brand_attribute"
    brand_comparison = "brand_comparison"
    brand_trust = "brand_trust"
    category_recommendation = "category_recommendation"
    scenario_solution = "scenario_solution"
    user_recommendation = "user_recommendation"
    generic_advice = "generic_advice"

class KpiWeightsConfig(BaseModel):
    accuracy: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    citation: float = Field(ge=0, le=1)
    sov: float = Field(ge=0, le=1)
    first_rec: float = Field(ge=0, le=1)

    @field_validator("accuracy", "completeness", "citation", "sov", "first_rec")
    @classmethod
    def check_sum(cls, v, info):
        # cross-field validation in model_validator
        return v

    @model_validator(mode="after")
    def validate_sum(self):
        total = self.accuracy + self.completeness + self.citation + self.sov + self.first_rec
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"KPI weights sum must be 1.0, got {total}")
        return self

class HallucinationThresholdsConfig(BaseModel):
    n_gram_similarity_min: float = Field(default=0.05, ge=0, le=1)
    n_gram_similarity_max: float = Field(default=0.35, ge=0, le=1)
    llm_fallback_enabled: bool = True
    high_risk_fields: list[str] = Field(default_factory=list)
    field_signal_overrides: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.n_gram_similarity_min >= self.n_gram_similarity_max:
            raise ValueError("n_gram_similarity_min must be < n_gram_similarity_max")
        return self

class TemplateStrategyConfig(BaseModel):
    min_questions_per_qtype: int = Field(default=1, ge=1)
    max_questions_per_qtype: int = Field(default=8, ge=1)
    required_qtypes: list[QuestionType] = Field(default_factory=list)
    recommended_qtypes: list[QuestionType] = Field(default_factory=list)
    brand_directed_min: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_qtypes(self):
        if self.min_questions_per_qtype > self.max_questions_per_qtype:
            raise ValueError("min must be <= max")
        return self

class CompetitorRulesConfig(BaseModel):
    min_competitors: int = Field(default=1, ge=0)
    max_competitors: int = Field(default=5, ge=1)
    require_same_category: bool = True
    allow_cross_category: bool = False
    competitor_source_priority: list[str] = Field(default=["gt", "industry_default", "manual"])
    competitor_types: list[str] = Field(default=["direct", "substitute"])
    exclude_self_brands: bool = True

class IndustryConfig(BaseModel):
    schema_version: str = "industry_config_v1"
    kpi_weights: KpiWeightsConfig
    hallucination_thresholds: HallucinationThresholdsConfig = HallucinationThresholdsConfig()
    template_strategy: TemplateStrategyConfig = TemplateStrategyConfig()
    competitor_rules: CompetitorRulesConfig = CompetitorRulesConfig()
```

### 2.2 预设行业配置

```python
INDUSTRY_DEFAULTS = {
    IndustryCode.DEFAULT: IndustryConfig(
        kpi_weights=KpiWeightsConfig(accuracy=0.30, completeness=0.15, citation=0.10, sov=0.25, first_rec=0.20),
        ...
    ),
    IndustryCode.RESTAURANT_CHAIN: IndustryConfig(
        kpi_weights=KpiWeightsConfig(accuracy=0.15, completeness=0.15, citation=0.40, sov=0.15, first_rec=0.15),
        hallucination_thresholds=HallucinationThresholdsConfig(
            high_risk_fields=["official_name", "core_products", "store_format"],
        ),
        template_strategy=TemplateStrategyConfig(
            min_questions_per_qtype=3, max_questions_per_qtype=8,
            required_qtypes=["brand_definition", "brand_trust"],
            recommended_qtypes=["brand_comparison", "scenario_solution"],
        ),
        competitor_rules=CompetitorRulesConfig(require_same_category=True),
    ),
    # ... SaaS, TravelHotel, FinancialServices, etc
}
```

---

## 3. 配置合并系统（P0-4, P0-5）

### 3.1 resolve_industry_config()

`src/services/industry_config_service.py`:

```python
def resolve_industry_config(brand: Brand, db: AsyncSession) -> MergedConfig:
    """
    Returns:
        config: IndustryConfig (fully merged + validated)
        source_layers: ["global_default", "industry:restaurant_chain", "brand_override"]
        warnings: list[str]
    """
```

合并规则：
- dict: 递归合并
- scalar: 覆盖
- **array: 整体替换**
- **null: 显式清空**
- **kpi_weights: 整体替换，不允许 partial**（P0-4）
- required_qtypes / recommended_qtypes: 整体替换
- field_signal_overrides: 按字段 dict 合并
- high_risk_fields: 整体替换
- competitor_rules: dict 递归合并

### 3.2 KPI 权重校验规则（P0-4）

- 每个权重 >= 0, <= 1
- 总和 0.999 ~ 1.001
- 品牌级 kpi_weights override 必须提交完整 5 项
- 缺失/未知 KPI key → 报错
- validated 在每层合并后执行

---

## 4. 消费点实现

### 4.1 health_score（P0-4, P0-9）

`src/reports/health_score.py`: 从 CollectionRun.industry_config_snapshot_json 读取权重

### 4.2 template_strategy 模板选择算法（P0-6）

`src/collector/engine.py` — `run_collection()`:

1. 过滤 `applicable_industries` / `excluded_industries`
2. 优先 required_qtypes
3. 每个 required_qtype >= min_questions_per_qtype
4. recommended_qtypes 预算允许下补充
5. 每个 qtype <= max_questions_per_qtype
6. brand_directed 比例 >= brand_directed_min
7. 不足 → TemplateStrategyViolation（不静默降级）
8. 输出 selection_summary: selected/excluded/qtype_counts/brand_directed_ratio/violations

### 4.3 hallucination_thresholds（P0-7）

- `high_risk_fields` 中 contradicted → severity >= P1
- official_name/industry/core_products 冲突 → 可升 P0
- LLM fallback 只用于 ambiguous/low-confidence，不绕过 GT evidence
- field_signal_overrides 按行业扩展，key 必须来自 GT Field Registry

### 4.4 competitor_rules（P0-8）

- `{竞品}` 模板变量填充
- SOV 竞争集 / first_rec 竞争排序解析
- `require_same_category=true` 避免餐饮 vs SaaS 跨行业竞品
- 竞品不足 → GT insufficient / template skipped

---

## 5. 配置版本化（P0-9）

### CollectionRun 快照

```python
CollectionRun.industry_config_snapshot_json = {
    "schema_version": "industry_config_v1",
    "industry_code": "restaurant_chain",
    "industry_template_id": "...",
    "config_version": 3,
    "merged_config": {...},
    "source_layers": ["global_default", "industry:restaurant_chain"],
    "brand_override_applied": False,
    "pinned_at": "2026-06-03T00:00:00Z",
}
```

采集/分析开始时针定。报告使用 snapshot，不被行业配置修改影响。

---

## 6. API（P0-10）

| 端点 | 方法 | 权限 | 用途 |
|------|------|------|------|
| `/api/industries` | GET | viewer+ | 行业列表 |
| `/api/industries/{id}` | GET | viewer+ | 行业配置详情 |
| `/api/industries/{id}/config` | PUT | system_admin | 更新行业配置 |
| `/api/brands/{id}/industry-config` | POST | brand_admin+ | 品牌级覆盖 |

权限矩阵: viewer=只读, brand_admin=品牌覆盖, system_admin=行业配置, system_owner=发布/回滚

每次修改: `reason` 必填, `expected_config_version` 校验（409 冲突）, AuditLog 写入。

---

## 7. Migration

- `industry_templates`: +`hallucination_thresholds JSONB`, +`template_strategy JSONB`, +`competitor_rules JSONB`, +`config_version INTEGER DEFAULT 1`
- `brands`: +`industry_template_id`, +`industry_detection_status`, +`industry_detection_confidence`, +`industry_detection_evidence_json`, +`industry_confirmed_by`, +`industry_confirmed_at`, +`industry_config_override JSONB`
- `collection_runs`: +`industry_config_snapshot_json JSONB`
- 填充: DEFAULT/RESTAURANT_CHAIN/SAAS/TRAVEL_HOTEL/FINANCIAL_SERVICES 五行业预设

---

## 8. 实现顺序

| Step | 内容 |
|------|------|
| 0 | IndustryCode 枚举 + IndustryConfig Pydantic + 5 行业默认配置 |
| 1 | IndustryConfigService (resolve + deep merge + validate) |
| 2 | Migration: 表扩展 + 预设填充 |
| 3 | health_score 接入行业 KPI 权重 |
| 4 | hallucination detector 接入行业阈值 |
| 5 | collector template strategy 接入 |
| 6 | competitor_rules 接入竞品模板/SOV/first_rec |
| 7 | CollectionRun.industry_config_snapshot_json 快照 |
| 8 | API + 权限 + AuditLog + version conflict |
| 9 | Brand 行业识别/fallback |
| 10 | 测试全部 |

---

## 9. 测试清单

- Schema: weights_sum, unknown_key, threshold_ranges, qtype_enum, config_valid
- Merge: global_fallback, industry_override, brand_override, deep_merge_dict, array_replaces, partial_kpi_rejected, null_behavior
- Detection: manual_binding, suggested_industry, starbucks→restaurant_chain, low_confidence→confirm
- KPI: restaurant_citation_40%, saas_sov_35%, financial_accuracy_35%, snapshot_used, historical_not_changed
- Template: required_first, min_per_qtype, max_per_qtype, brand_directed_min, violation_when_missing
- Hallucination: high_risk_fields, signal_overrides, financial_stricter, llm_fallback_ambiguous_only
- Competitor: same_category, fill_template_var, insufficient→gt_insufficient, report_source
- API: system_admin_required, brand_admin_override, reason_required, version_conflict_409, audit_log

---

## 10. Done Definition

1. IndustryCode 枚举 + 5 行业默认配置
2. IndustryConfig Pydantic schema 完整可用
3. KPI 权重强校验（sum=1.0, complete override）
4. deep merge 规则 + resolve_industry_config()
5. CollectionRun.industry_config_snapshot_json 快照
6. health_score 使用行业权重
7. hallucination detector 使用行业阈值
8. collector 使用 template_strategy 选择模板
9. competitor_rules 影响竞品逻辑
10. API 权限 + reason + version_conflict + AuditLog
11. 品牌未绑定时 fallback/suggested
12. Migration + 预设填充
13. 全部测试通过
14. 星巴克用 restaurant_chain 跑通（citation=0.40）
