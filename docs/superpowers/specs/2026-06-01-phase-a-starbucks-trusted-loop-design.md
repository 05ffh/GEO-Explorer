# Phase A: 星巴克重跑前最小可信闭环 — 设计规格 v3

> 日期: 2026-06-01 | 状态: Define Final (四轮审阅整合)
> 覆盖 A0→A8 全部 9 个子任务，含函数契约/Pydantic校验/DenominatorType枚举/Go命令/数据保全/失败回写/Done Definition

---

## 1. 目标

完成星巴克完整链路重跑，使其成为 GEO Explorer 诊断可信度体系的第一次正式验收。重跑前必须建立最小可信闭环：数据结构落库、报告分层、模板健康度前置检查、Template→Metric 映射、回归测试。

### 验收总则

```
template_error_p0_count = 0
generic_statement_p0_count = 0
gt_insufficient_p0_count = 0
report_publishable = true
md/docx/pdf 三格式可打开 + 内容一致
修复前后对比报告证明误报降低
```

---

## 2. 新增文件

| 文件 | 用途 |
|------|------|
| `src/analyzer/enums.py` | 统一枚举：TemplateLevel, QuestionType, QuestionScope, SubjectType, HallucinationVerdict, Severity, DenominatorType |
| `src/analyzer/schemas.py` | Pydantic 校验：ReportQualitySummaryModel, TemplateHealthReportModel, CoverageReportModel, GoNoGoResultModel, BlockingReason |
| `src/analyzer/quality.py` | `build_report_quality_summary()` + `compute_report_publishable()` |
| `config/metric_template_mapping.yaml` | 10 KPI × 8 question_type 映射矩阵（含 schema_version + mapping_version） |
| `scripts/phase_a_go_no_go.py` | Go/No-Go 命令（支持 --dry-run） |
| `artifacts/go_no_go/` | Go/No-Go artifact 归档目录 |
| `artifacts/phase_a/starbucks/{timestamp}/` | A6 星巴克重跑完整归档目录 |
| `tests/migrations/test_phase_a_migration.py` | Migration pre/post 检查 |
| `tests/regression/hallucination/` | 回归测试样本 + 测试代码 |

### 修改文件

| 文件 | 变更内容 |
|------|------|
| `src/models/collection_run.py` | +`report_quality_summary_json` JSONB, `template_health_report_json` JSONB, `report_publishable` bool, `blocking_reasons_json` JSONB |
| `src/models/query_template.py` | +`template_level` String(20), `question_scope` String(30) (预留) |
| `src/models/hallucination.py` | +`claim_text` Text, `subject_type` String(50), `matched_gt_field` String(100), `reason` Text, `needs_human_review` bool (预留) |
| `src/collector/engine.py` | `_preflight_templates()` 增强：三级分级 + `TemplateHealthReport` 输出 + 写入 CollectionRun |
| `src/analyzer/pipeline.py` | `compute_and_save_metrics()` 末尾调用 quality 模块：`build_report_quality_summary()` → `compute_report_publishable()` |
| `src/reports/delivery.py` | 报告首页渲染 ReportQualitySummary + 四层问题来源展示 |

---

## 2.1 枚举统一 (`src/analyzer/enums.py`)

**目的:** 所有配置、数据库、测试、报告都使用同一套枚举值，防止自由字符串导致的口径不一致（如 `generic_statement` vs `generic`、`P0` vs `p0`）。

```python
from enum import Enum

class TemplateLevel(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"

class QuestionType(str, Enum):
    BRAND_DEFINITION = "brand_definition"
    BRAND_ATTRIBUTE = "brand_attribute"
    BRAND_COMPARISON = "brand_comparison"
    BRAND_TRUST = "brand_trust"
    CATEGORY_RECOMMENDATION = "category_recommendation"
    SCENARIO_SOLUTION = "scenario_solution"
    USER_RECOMMENDATION = "user_recommendation"
    GENERIC_ADVICE = "generic_advice"

class QuestionScope(str, Enum):
    BRAND_DIRECTED = "brand_directed"
    BRAND_ADJACENT = "brand_adjacent"
    CATEGORY_DIRECTED = "category_directed"
    SCENARIO_DIRECTED = "scenario_directed"
    GENERIC = "generic"

class SubjectType(str, Enum):
    TARGET_BRAND = "target_brand"
    COMPETITOR = "competitor"
    CATEGORY = "category"
    GENERIC = "generic"
    UNKNOWN = "unknown"

class HallucinationVerdict(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNSUPPORTED = "unsupported"
    TEMPLATE_INVALID = "template_invalid"
    GENERIC_STATEMENT = "generic_statement"
    NOT_ABOUT_BRAND = "not_about_brand"
    GT_INSUFFICIENT = "gt_insufficient"
    NOT_CHECKABLE = "not_checkable"
    AMBIGUOUS = "ambiguous"

class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    INFO = "Info"

class DenominatorType(str, Enum):
    RECOMMENDATION_LIST_RESPONSES = "recommendation_list_responses"
    RANKED_RECOMMENDATION_RESPONSES = "ranked_recommendation_responses"
    BRAND_MENTION_ELIGIBLE_RESPONSES = "brand_mention_eligible_responses"
    CHECKABLE_TARGET_BRAND_CLAIMS = "checkable_target_brand_claims"
    EXPECTED_BRAND_FIELDS = "expected_brand_fields"
    SOURCE_CITATION_ELIGIBLE_RESPONSES = "source_citation_eligible_responses"
    COMPETITOR_COMPARISON_CLAIMS = "competitor_comparison_claims"
    SCENARIO_ELIGIBLE_RESPONSES = "scenario_eligible_responses"
    TRUST_RISK_ELIGIBLE_RESPONSES = "trust_risk_eligible_responses"
```

**KPI → DenominatorType 对应表：**

| KPI | denominator_type |
|---|---|
| sov | recommendation_list_responses |
| first_rec_rate | ranked_recommendation_responses |
| brand_mention_rate | brand_mention_eligible_responses |
| information_accuracy | checkable_target_brand_claims |
| completeness_rate | expected_brand_fields |
| citation_rate | source_citation_eligible_responses |
| competitor_accuracy | competitor_comparison_claims |
| scenario_coverage | scenario_eligible_responses |
| trust_risk_rate | trust_risk_eligible_responses |
| hallucination_rate | checkable_target_brand_claims |

**规则：** denominator_type 必须使用枚举值，不允许自由字符串。分母为 0 时 value 应为 null / "insufficient_sample"，不输出误导性 0 分。

**验收:**
```
未知字符串在加载时 assert/fail
CI 能发现拼写不一致
config/metric_template_mapping.yaml 用枚举值校验
```

---

## 2.2 JSONB Schema Version

所有关键 JSON 结构都包含 `schema_version` 字段，确保后续字段变化时历史报告和新报告可区分。

```json
// ReportQualitySummary
{ "schema_version": "report_quality_summary_v1", "generated_at": "...", "..." }

// TemplateHealthReport
{ "schema_version": "template_health_v1", "generated_at": "...", "..." }

// MetricDetails 中 denominator 元数据
{ "schema_version": "metric_details_v1", "generated_at": "...", "..." }

// GoNoGoResult
{ "schema_version": "go_no_go_v1", "checked_at": "...", "..." }
```

**验收:**
```
历史报告知道使用哪版质量结构
后续 Phase B/C 增字段不破坏旧报告
report delivery 兼容缺少 schema_version 的旧数据（fallback 为 "unknown"）
```

---

## 2.3 Alembic Migration 详情

### 新增列 + 默认值

```sql
-- CollectionRun
ALTER TABLE collection_runs ADD COLUMN report_quality_summary_json JSONB DEFAULT '{}'::jsonb;
ALTER TABLE collection_runs ADD COLUMN template_health_report_json JSONB DEFAULT '{}'::jsonb;
ALTER TABLE collection_runs ADD COLUMN report_publishable BOOLEAN DEFAULT false;
ALTER TABLE collection_runs ADD COLUMN blocking_reasons_json JSONB DEFAULT '[]'::jsonb;

-- QueryTemplate
ALTER TABLE query_templates ADD COLUMN template_level VARCHAR(20) DEFAULT 'important';
ALTER TABLE query_templates ADD COLUMN question_scope VARCHAR(30);

-- HallucinationResult
ALTER TABLE hallucination_results ADD COLUMN claim_text TEXT DEFAULT '';
ALTER TABLE hallucination_results ADD COLUMN subject_type VARCHAR(50) DEFAULT '';
ALTER TABLE hallucination_results ADD COLUMN matched_gt_field VARCHAR(100) DEFAULT '';
ALTER TABLE hallucination_results ADD COLUMN reason TEXT DEFAULT '';
ALTER TABLE hallucination_results ADD COLUMN needs_human_review BOOLEAN DEFAULT false;
```

### 索引

```sql
CREATE INDEX IF NOT EXISTS ix_collection_runs_report_publishable ON collection_runs (report_publishable);
CREATE INDEX IF NOT EXISTS ix_hallucination_results_subject_type ON hallucination_results (subject_type);
CREATE INDEX IF NOT EXISTS ix_hallucination_results_severity ON hallucination_results (severity);
CREATE INDEX IF NOT EXISTS ix_query_templates_question_type ON query_templates (question_type);
CREATE INDEX IF NOT EXISTS ix_query_templates_template_level ON query_templates (template_level);
```

### 存量数据

```
现有 CollectionRun: report_publishable 默认 false（不改变历史报告的可发布状态）
现有 HallucinationResult: 新字段默认空字符串（历史数据不补填）
现有 QueryTemplate: template_level 默认 important（不强制分级）
```

### 回滚

```sql
-- Downgrade 策略：删列（不丢核心业务数据）
ALTER TABLE collection_runs DROP COLUMN report_quality_summary_json;
-- ... (其他列同理)
DROP INDEX IF EXISTS ix_collection_runs_report_publishable;
-- ...
```

**验收:**
```
空库 migration 通过
存量库 migration 通过
已有 CollectionRun report_publishable = false
已有模板 template_level = 'important'
downgrade 不丢核心业务数据
```

---

## 2.4 Pydantic / JSON Schema 校验 (`src/analyzer/schemas.py`)

所有写入 CollectionRun 的 JSONB 结构在写入前校验。

```python
from pydantic import BaseModel
from typing import Literal

class BlockingReason(BaseModel):
    code: str
    message: str
    severity: Literal["block", "warning"]

class AiHallucinationSummary(BaseModel):
    p0_count: int = 0; p1_count: int = 0; p2_count: int = 0
    confirmed_claim_count: int = 0
    p0_explanation: str = ""
    excluded_explanation: str = ""

class TemplateIssueSummary(BaseModel):
    invalid_template_count: int = 0
    unresolved_variable_count: int = 0
    affected_query_count: int = 0

class GtInsufficientSummary(BaseModel):
    unsupported_claim_count: int = 0
    missing_gt_fields: list[str] = []

class NotAboutBrandSummary(BaseModel):
    generic_statement_count: int = 0
    irrelevant_response_count: int = 0

class ReportQualitySummaryModel(BaseModel):
    schema_version: Literal["report_quality_summary_v1"]
    generated_at: str
    ai_hallucination: AiHallucinationSummary
    template_issue: TemplateIssueSummary
    gt_insufficient: GtInsufficientSummary
    not_about_brand: NotAboutBrandSummary
    report_publishable: bool
    blocking_reasons: list[BlockingReason] = []

class TemplateHealthReportModel(BaseModel):
    schema_version: Literal["template_health_v1"]
    generated_at: str
    total_templates: int; valid_templates: int
    invalid_templates: int; skipped_templates: int
    critical_invalid: int; important_invalid: int; optional_skipped: int
    blocking_invalid_templates: int; non_blocking_skipped_templates: int
    invalid_ratio: float; missing_variables: dict
    can_collect: bool; can_publish_report: bool

class CoverageReportModel(BaseModel):
    raw_coverage: float; valid_answer_coverage: float
    metric_eligible_coverage: float
    platform_coverage: dict

class GoNoGoItem(BaseModel):
    name: str; status: Literal["go", "no_go"]
    evidence: str; blocking: bool

class GoNoGoResultModel(BaseModel):
    schema_version: Literal["go_no_go_v1"]
    run_target: str; checked_at: str
    overall_decision: Literal["go", "no_go"]
    items: list[GoNoGoItem]
    approved_by: str
```

**验收:**
```
写入 CollectionRun 前先 .model_validate()
验证失败 → report_publishable=false + blocking_reason=SCHEMA_VALIDATION_FAILED
CI 覆盖 schema 校验
历史旧数据缺 schema_version → fallback 为 "unknown"
```

---

### 2.5 Migration Pre/Post 检查 (`tests/migrations/test_phase_a_migration.py`)

**Pre-check:** 确认表存在、新增列不存在、统计行数、检查重名索引。
**Post-check:** 确认新增列存在、默认值正确、行数未变、index 创建成功、旧记录默认值验证。

```python
async def test_phase_a_migration_pre_check(db):
    # 确认列不存在
    ...
async def test_phase_a_migration_post_check(db):
    # 列存在 + 默认值 + 行数不变
    old_run = await db.get(CollectionRun, old_run_id)
    assert old_run.report_publishable == False
    old_tmpl = await db.get(QueryTemplate, old_tmpl_id)
    assert old_tmpl.template_level == "important"
```

---

## 3. 数据结构定义

### 3.1 CollectionRun 新增字段

```python
# CollectionRun 新增
report_quality_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
template_health_report_json: Mapped[dict] = mapped_column(JSONB, default=dict)
report_publishable: Mapped[bool] = mapped_column(Boolean, default=False)
blocking_reasons_json: Mapped[list] = mapped_column(JSONB, default=list)
```

### 3.2 QueryTemplate 新增字段

```python
template_level: Mapped[str] = mapped_column(String(20), default="important")
# critical / important / optional

question_scope: Mapped[str] = mapped_column(String(30), nullable=True)
# brand_directed / brand_adjacent / category_directed / scenario_directed / generic
# 阶段A预留，阶段B实现逻辑
```

### 3.3 HallucinationResult 新增字段

```python
# Debug Evidence 最小字段（阶段A）
claim_text: Mapped[str] = mapped_column(Text, default="")
subject_type: Mapped[str] = mapped_column(String(50), default="")
matched_gt_field: Mapped[str] = mapped_column(String(100), default="")
reason: Mapped[str] = mapped_column(Text, default="")

# 人审闭环预留（阶段A预留，阶段C实现）
needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
```

HallucinationResult 已有字段足够：`verdict`, `severity`, `ai_claim`, `field_name`, `ground_truth_value`

### 3.4 ReportQualitySummary

```json
{
  "schema_version": "report_quality_summary_v1",
  "generated_at": "2026-06-01T00:00:00Z",
  "ai_hallucination": {
    "p0_count": 0, "p1_count": 0, "p2_count": 0, "confirmed_claim_count": 0,
    "p0_explanation": "仅统计目标品牌核心事实与 GT 明确冲突的声明",
    "excluded_explanation": "模板问题、GT 不足、回答无关不计入 AI 幻觉"
  },
  "template_issue": {
    "invalid_template_count": 0, "unresolved_variable_count": 0, "affected_query_count": 0
  },
  "gt_insufficient": {
    "unsupported_claim_count": 0, "missing_gt_fields": []
  },
  "not_about_brand": {
    "generic_statement_count": 0, "irrelevant_response_count": 0
  },
  "report_publishable": true,
  "blocking_reasons": []
}
```

### 3.5 TemplateHealthReport

**修正：** `invalid_templates` 统计所有无效模板（含 optional skipped）。`blocking_invalid_templates` 区分阻断型和非阻断型。

```json
{
  "schema_version": "template_health_v1",
  "generated_at": "...",
  "total_templates": 23,
  "valid_templates": 21,
  "invalid_templates": 2,
  "skipped_templates": 1,
  "critical_invalid": 0,
  "important_invalid": 1,
  "optional_skipped": 1,
  "blocking_invalid_templates": 1,
  "non_blocking_skipped_templates": 1,
  "invalid_ratio": 0.087,
  "missing_variables": {},
  "can_collect": true,
  "can_publish_report": true
}
```

**口径说明：**
- `invalid_templates` = 所有 `render_status != "ok"` 的模板（完整计数，不减 optional）
- `skipped_templates` = 所有被跳过的模板
- `optional_skipped` = skipped 中 template_level=optional 的子集
- `critical_invalid` = invalid 中 template_level=critical 的子集
- `blocking_invalid_templates` = critical_invalid + important_invalid（会阻断发布的无效模板数）
- `non_blocking_skipped_templates` = optional_skipped（不阻断发布的跳过数）
- `invalid_ratio` = invalid_templates / total_templates（与 invalid_templates 口径一致）

### 3.6 KPI Denominator 元数据

每个 KPI 的 `details` 中增加：

```json
{
  "metric_key": "information_accuracy",
  "value": 0.86,
  "numerator": 43,
  "denominator": 50,
  "denominator_type": "checkable_target_brand_claims",
  "included_query_count": 12,
  "excluded_query_count": 11,
  "exclusion_reasons": {
    "generic_statement": 4,
    "gt_insufficient": 3,
    "not_about_brand": 4
  }
}
```

---

## 4. 模块设计

### 4.1 `src/analyzer/quality.py` — 函数契约

```python
async def build_report_quality_summary(
    collection_run_id: str,
    template_health: dict | None,
    coverage_report: dict | None,
    db: AsyncSession,
) -> ReportQualitySummary:
```

**输入契约:**
- `collection_run_id` 必须存在对应的 CollectionRun
- `template_health` 可为 None → template_issue 标记 `unknown`
- `coverage_report` 可为 None → coverage 相关 warning
- HallucinationResult 为空 → ai_hallucination 全部为 0，confirmed_claim_count=0

**输出契约:**
- 永远返回 ReportQualitySummary（不抛异常）
- `schema_version` 必填 `"report_quality_summary_v1"`
- `generated_at` 必填 ISO8601
- 所有 count 字段 int，默认 0
- `blocking_reasons` 初始为 `[]`

**异常策略:**
- DB 查询失败 → 抛异常，pipeline 标记 `analysis_status=failed`
- 字段缺失 → 不抛异常，写 warning blocking_reason
- 枚举未知 → `report_publishable=false` + blocking_reason=UNKNOWN_ENUM

```python
def compute_report_publishable(
    template_health: dict | None,
    coverage_report: dict | None,
    quality_summary: ReportQualitySummary,
    metric_results: dict | None,
) -> tuple[bool, list[BlockingReason]]:
```

**输入契约:**
- `coverage_report` 必须有 `metric_eligible_coverage`，否则 hard block: COVERAGE_DATA_MISSING
- `metric_results` 必须包含核心 KPI denominator，否则 hard block: METRIC_DATA_MISSING
- `quality_summary` 必须包含 `schema_version`，否则 hard block: QUALITY_SCHEMA_MISSING
- `template_health` 为 None → hard block: TEMPLATE_HEALTH_MISSING

**输出契约:**
- `publishable: bool`
- `blocking_reasons: list[BlockingReason]`（每项 `{code, message, severity}`）
- 所有输出可 JSON 序列化

**硬阻断条件（任一命中 → false）：**

```python
HARD_BLOCKS = [
    ("CRITICAL_TEMPLATE_INVALID", "存在 critical 模板无效"),
    ("CANNOT_COLLECT", "模板健康度判定 can_collect=false"),
    ("METRIC_COVERAGE_LOW", "metric_eligible_coverage < 60%"),
    ("TEMPLATE_ERROR_AS_P0", "template_error 被计入 P0"),
    ("GENERIC_AS_P0", "generic_statement 被计入 P0"),
    ("GT_INSUFFICIENT_AS_P0", "gt_insufficient 被计入 P0"),
    ("CORE_KPI_ZERO_DENOMINATOR", "核心 KPI denominator=0"),
    ("P0_MISSING_GT_EVIDENCE", "P0 hallucination 缺少 GT evidence"),
]
```

**P0_MISSING_GT_EVIDENCE 判定规则：** 对所有 `verdict=contradicted, severity=P0, subject_type=target_brand` 的 HallucinationResult，必须满足：`matched_gt_field` 非空、`ground_truth_value` 非空、`reason` 非空、`claim_text` 非空。任一缺失 → hard block。

**软警告条件（不阻断）：**

```python
SOFT_WARNINGS = [
    ("OPTIONAL_SKIPPED", "optional 模板有跳过"),
    ("PLATFORM_LOW_COVERAGE", "某平台 coverage < 50%"),
    ("HIGH_GT_UNSUPPORTED", "GT unsupported_claim_count 较高"),
    ("RATE_LIMIT_IMPACT", "Kimi/Doubao rate limit 影响样本"),
]
```

**blocking_reasons 格式：**
```json
[{"code": "METRIC_COVERAGE_LOW", "message": "可进入指标计算的有效样本覆盖率低于 60%", "severity": "block"}]
```

### 4.1.1 Coverage Report 扩展 — metric_eligible_coverage

现有 `CollectionRun.coverage_report_json` 需扩展以支持 `METRIC_COVERAGE_LOW` 判定：

```json
{
  "raw_coverage": 0.85,
  "valid_answer_coverage": 0.72,
  "metric_eligible_coverage": 0.66,
  "platform_coverage": {
    "deepseek": 1.0,
    "kimi": 0.7,
    "doubao": 0.55
  }
}
```

**计算口径：**
```
raw_coverage = 有任何采集结果 / 应采集 query 数
valid_answer_coverage = answer_source=content 有效回答 / 应采集 query 数
metric_eligible_coverage = 可进入 KPI 计算的 QueryResult / 应进入 KPI 的 QueryResult
```

`report_publishable` 只看 `metric_eligible_coverage`。报告展示三类 coverage，避免误解。

### 4.2 `config/metric_template_mapping.yaml` — 新建

```yaml
# 10 KPI × 8 question_type 矩阵
# eligibility: always | conditional | never
# condition: target_brand_claim_only (仅当 conditional 时需要)

sov:
  allowed: [category_recommendation, scenario_solution, user_recommendation]
  conditional: {brand_comparison: target_brand_claim_only}
  excluded: [generic_advice]

first_rec_rate:
  allowed: [category_recommendation, scenario_solution, user_recommendation]
  conditional: {brand_comparison: target_brand_claim_only}
  excluded: [generic_advice]

brand_mention_rate:
  allowed: [brand_definition, brand_attribute, brand_comparison, brand_trust,
            category_recommendation, scenario_solution, user_recommendation]
  excluded: [generic_advice]

information_accuracy:
  allowed: [brand_definition, brand_attribute, brand_comparison, brand_trust]
  conditional:
    category_recommendation: target_brand_claim_only
    scenario_solution: target_brand_claim_only
    user_recommendation: target_brand_claim_only
  excluded: [generic_advice]

completeness_rate:
  allowed: [brand_definition, brand_attribute]
  conditional:
    brand_comparison: target_brand_claim_only
    brand_trust: target_brand_claim_only
  excluded: [category_recommendation, scenario_solution, user_recommendation, generic_advice]

citation_rate:
  allowed: [brand_definition, brand_attribute, brand_comparison, brand_trust]
  conditional:
    category_recommendation: target_brand_claim_only
    scenario_solution: target_brand_claim_only
    user_recommendation: target_brand_claim_only
  excluded: [generic_advice]

competitor_accuracy:
  allowed: [brand_comparison]
  conditional: {category_recommendation: target_brand_claim_only}
  excluded: [generic_advice]

scenario_coverage:
  allowed: [scenario_solution, user_recommendation]
  conditional:
    brand_attribute: target_brand_claim_only
    category_recommendation: target_brand_claim_only
  excluded: [generic_advice]

trust_risk_rate:
  allowed: [brand_trust]
  conditional: {brand_comparison: target_brand_claim_only}
  excluded: [generic_advice]

hallucination_rate:
  allowed: [brand_definition, brand_attribute, brand_comparison, brand_trust]
  conditional:
    category_recommendation: target_brand_claim_only
    scenario_solution: target_brand_claim_only
    user_recommendation: target_brand_claim_only
  excluded: [generic_advice]
```

**加载与使用：**

```python
# src/analyzer/metric_loader.py (新建或放在 pipeline.py)
import yaml
from pathlib import Path

_MAPPING = None

def load_metric_mapping() -> dict:
    global _MAPPING
    if _MAPPING is None:
        path = Path(__file__).parent.parent.parent / "config" / "metric_template_mapping.yaml"
        with open(path) as f:
            _MAPPING = yaml.safe_load(f)
    return _MAPPING

def is_query_eligible_for_kpi(
    query_template: QueryTemplate, kpi_key: str
) -> tuple[bool, str | None]:
    """返回 (eligible, condition)"""
    mapping = load_metric_mapping().get(kpi_key, {})
    qt = query_template.question_type
    if qt in mapping.get("excluded", []):
        return False, f"excluded question_type: {qt}"
    if qt in mapping.get("allowed", []):
        return True, None
    if qt in mapping.get("conditional", {}):
        return True, mapping["conditional"][qt]
    return False, f"unmapped question_type: {qt}"

def validate_metric_mapping(mapping: dict) -> list[str]:
    """校验 mapping 配置合法性，返回错误列表。启动时/CI 调用。"""
    from src.analyzer.enums import QuestionType
    errors = []
    known_kpis = {
        "sov", "first_rec_rate", "brand_mention_rate", "information_accuracy",
        "completeness_rate", "citation_rate", "competitor_accuracy",
        "scenario_coverage", "trust_risk_rate", "hallucination_rate",
    }
    known_qtypes = {e.value for e in QuestionType}
    known_conditions = {"target_brand_claim_only"}

    for kpi_key, cfg in mapping.items():
        if kpi_key not in known_kpis:
            errors.append(f"Unknown KPI key: {kpi_key}")
        # Check allowed question_types
        for qt in cfg.get("allowed", []):
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.allowed: unknown question_type '{qt}'")
        # Check conditional
        for qt, cond in cfg.get("conditional", {}).items():
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.conditional: unknown question_type '{qt}'")
            if cond not in known_conditions:
                errors.append(f"{kpi_key}.conditional[{qt}]: unknown condition '{cond}'")
        # Check excluded
        for qt in cfg.get("excluded", []):
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.excluded: unknown question_type '{qt}'")
        # generic_advice must be excluded from core KPIs
        core_kpis = {"information_accuracy", "completeness_rate", "citation_rate",
                     "hallucination_rate", "brand_mention_rate"}
        if kpi_key in core_kpis and "generic_advice" not in cfg.get("excluded", []):
            errors.append(f"{kpi_key}: generic_advice must be excluded")
        # Check for duplicate qtype across allowed/conditional/excluded
        all_qtypes = set(cfg.get("allowed", [])) | set(cfg.get("conditional", {}).keys()) | set(cfg.get("excluded", []))
        expected = len(cfg.get("allowed", [])) + len(cfg.get("conditional", {})) + len(cfg.get("excluded", []))
        if len(all_qtypes) != expected:
            errors.append(f"{kpi_key}: duplicate question_type across allowed/conditional/excluded")

    # Check all core KPIs present
    for kpi in known_kpis:
        if kpi not in mapping:
            errors.append(f"Missing KPI: {kpi}")

    return errors
```

**验收:**
```
mapping 缺失核心 KPI → CI fail
未知 question_type → CI fail
generic_advice 未 excluded → CI fail
duplicate qtype across sections → CI fail
运行时加载失败阻断 report_publishable
```

**调用点 (P0-4):**
```
1. 应用启动时调用 validate_metric_mapping()
2. CI 单元测试调用
3. A5 Go/No-Go 调用
4. compute_and_save_metrics 运行前兜底调用
```

**失败策略:**
```
启动时失败 → app 启动失败或 analyzer disabled (fatal)
CI 失败 → 阻断合并
A5 失败 → No-Go
运行时失败 → report_publishable=false, blocking_reason=MAPPING_INVALID
```

**YAML 版本号 (P1-4):**
```yaml
# config/metric_template_mapping.yaml 顶部
schema_version: metric_template_mapping_v1
mapping_version: phase_a_v1
```
报告中记录 `metric_mapping_version = phase_a_v1`，后续 KPI 口径变化可追溯。

### 4.3 `src/models/` — 修改

```python
# collection_run.py 新增（接在 preflight_summary_json 后面）
report_quality_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
template_health_report_json: Mapped[dict] = mapped_column(JSONB, default=dict)
report_publishable: Mapped[bool] = mapped_column(Boolean, default=False)
blocking_reasons_json: Mapped[list] = mapped_column(JSONB, default=list)

# query_template.py 新增（接在 hallucination_check_enabled 后面）
template_level: Mapped[str] = mapped_column(String(20), default="important")
question_scope: Mapped[str | None] = mapped_column(String(30), nullable=True)

# hallucination.py 新增（接在 reviewed_at 后面）
claim_text: Mapped[str] = mapped_column(Text, default="")
subject_type: Mapped[str] = mapped_column(String(50), default="")
matched_gt_field: Mapped[str] = mapped_column(String(100), default="")
reason: Mapped[str] = mapped_column(Text, default="")
needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
```

### 4.4 `src/collector/engine.py` — 修改 `_preflight_templates()`

当前 `_preflight_templates` 已返回模板健康信息（P0-1），阶段 A 增强：

1. 为每个模板确定 `template_level`：critical / important / optional
   - Critical: brand_definition, brand_attribute（品牌定义、行业、核心产品、服务）
   - Important: brand_comparison, brand_trust（对比评价、信任验证）
   - Optional: category_recommendation, scenario_solution, user_recommendation, generic_advice

2. 分级阻断：
   - `critical_invalid > 0` → `can_publish_report = false`
   - `overall invalid_ratio > 20%` → `can_collect = false`

3. 输出 `TemplateHealthReport` dict 写入 `CollectionRun.template_health_report_json`

```python
TEMPLATE_LEVEL_MAP = {
    "brand_definition": "critical",
    "brand_attribute": "critical",
    "brand_comparison": "important",
    "brand_trust": "important",
    "category_recommendation": "optional",
    "scenario_solution": "optional",
    "user_recommendation": "optional",
    "generic_advice": "optional",
}

def _build_template_health_report(preflight_results: list, template_level_map: dict) -> dict:
    """Build TemplateHealthReport from preflight results."""
    total = len(preflight_results)
    invalid = [r for r in preflight_results if r.render_status != "ok"]
    skipped = [r for r in preflight_results if r.render_status == "skipped_missing_variable"]

    def _level(r):
        return template_level_map.get(r.template.question_type, "important")

    critical_invalid = [r for r in invalid if _level(r) == "critical"]
    important_invalid = [r for r in invalid if _level(r) == "important"]
    optional_skipped = [r for r in skipped if _level(r) == "optional"]

    invalid_ratio = len(invalid) / total if total > 0 else 0.0
    can_collect = invalid_ratio <= 0.20
    can_publish_report = len(critical_invalid) == 0

    return {
        "schema_version": "template_health_v1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total_templates": total,
        "valid_templates": total - len(invalid),
        "invalid_templates": len(invalid),
        "skipped_templates": len(skipped),
        "critical_invalid": len(critical_invalid),
        "important_invalid": len(important_invalid),
        "optional_skipped": len(optional_skipped),
        "blocking_invalid_templates": len(critical_invalid) + len(important_invalid),
        "non_blocking_skipped_templates": len(optional_skipped),
        "invalid_ratio": round(invalid_ratio, 4),
        "missing_variables": _aggregate_missing_vars(invalid),
        "can_collect": can_collect,
        "can_publish_report": can_publish_report,
    }
```

### 4.5 `src/analyzer/pipeline.py` — 修改 `compute_and_save_metrics()`

在 `deliver_all_reports` 调用之前插入 quality 模块：

```python
# After _run_hallucination_detection, before deliver_all_reports:

# Build ReportQualitySummary
from src.analyzer.quality import build_report_quality_summary, compute_report_publishable

# Read template health from CollectionRun
run = await db.get(CollectionRun, collection_run_id)
template_health = run.template_health_report_json or {}
coverage = run.coverage_report_json or {}

quality_summary = await build_report_quality_summary(
    collection_run_id, template_health, coverage, db
)

# Read just-computed MetricsSnapshot for denominator data
metric_snapshot = (await db.execute(
    select(MetricsSnapshot).where(MetricsSnapshot.collection_run_id == collection_run_id)
)).scalar_one_or_none()
metric_results = metric_snapshot.details if metric_snapshot else {}

# Compute publishable
publishable, blocking_reasons = compute_report_publishable(
    template_health, coverage, quality_summary, metric_results,
)

# Write back to CollectionRun
run.report_quality_summary_json = _to_dict(quality_summary)
run.report_publishable = publishable
run.blocking_reasons_json = blocking_reasons
db.add(run)
await db.commit()
```

同时，各 KPI 计算函数在 `compute_and_save_metrics` 中调用时，传入 `query_results` 进行 mapping 过滤。

### 4.6 `src/reports/delivery.py` — 修改报告首页

在诊断报告 Markdown 模板中增加 `ReportQualitySummary` 章节（报告最前面）：

```markdown
## 本次诊断可信度概览

| 类别 | 数量 | 说明 |
|------|:--:|------|
| AI 幻觉 (P0) | {p0_count} | 品牌核心事实与 GT 矛盾，需立即修正 |
| AI 幻觉 (P1/P2) | {p1_count}/{p2_count} | 次要/边缘事实偏差 |
| 模板问题 | {template_issues} | 模板变量未替换，不计入 AI 幻觉 |
| GT 不足 | {gt_insufficient} | GT 数据不足以核验，不计入 AI 幻觉 |
| 回答无关 | {not_about_brand} | 回答未涉及目标品牌，不计入 AI 幻觉 |
| 有效样本数 | {valid_samples} | 实际进入分析的样本 |

**报告状态:** {'可发布' if report_publishable else '⚠️ 不可发布'}

{blocking_reasons 展示}

> 本报告为 Phase A 可信度验收样本。已完成模板健康、报告分层、KPI denominator、回归测试。
> 行业适配、人审闭环、多证据 GT 将在后续阶段增强。
```

**前端 API 预留 (P1-2):**
```
GET /api/collections/{run_id}/quality
→ {report_quality_summary, template_health_report, coverage_report, report_publishable, blocking_reasons}
```

### 4.7 回归测试

#### 文件组织

```
tests/regression/hallucination/
  __init__.py
  starbucks_generic_false_positive.jsonl
  starbucks_gt_insufficient.jsonl
  starbucks_template_invalid.jsonl
  true_core_fact_errors.jsonl
  test_hallucination_regression.py
```

#### 样本格式

```json
{"sample_id": "starbucks_generic_001", "brand": "星巴克", "question": "小团队适合什么{品类}？", "render_status": "template_invalid", "response": "避开服装、3C配件等红海...", "expected_relevance": "category_general", "expected_subject_type": "generic", "expected_judgment": "generic_statement", "expected_severity": "Info", "must_not_be": ["contradicted", "P0"]}
```

#### 测试代码

```python
# test_hallucination_regression.py
import json
import pytest
from pathlib import Path

REGRESSION_DIR = Path(__file__).parent

def load_samples(filename: str) -> list[dict]:
    with open(REGRESSION_DIR / filename) as f:
        return [json.loads(line) for line in f if line.strip()]

@pytest.mark.parametrize("sample", load_samples("starbucks_generic_false_positive.jsonl"))
async def test_generic_statement_not_p0(sample, detector, starbucks_gt, db):
    """detector.detect() 接受 QueryResult+GT；test helper 从 sample dict 构造最小 QueryResult"""
    qr = _make_query_result_from_sample(sample)  # test helper
    results = await detector.detect(qr, starbucks_gt, db, brand_name="星巴克")
    for r in results:
        assert r.verdict not in ("contradicted",), \
            f"{sample['sample_id']}: generic statement wrongly marked contradicted"
        assert r.severity != "P0", \
            f"{sample['sample_id']}: generic statement wrongly marked P0"

# 类似 test_gt_insufficient_not_p0, test_template_invalid_not_hallucination

# 关键：真实核心事实错误召回测试 (P0-8)
@pytest.mark.parametrize("sample", load_samples("true_core_fact_errors.jsonl"))
async def test_true_core_fact_error_detected(sample, detector, starbucks_gt, db):
    """确保修复不把 detector 变成'什么都不报'"""
    qr = _make_query_result_from_sample(sample)
    results = await detector.detect(qr, starbucks_gt, db, brand_name="星巴克")
    p0_results = [r for r in results if r.severity == "P0" and r.verdict == "contradicted"]
    assert len(p0_results) > 0, \
        f"{sample['sample_id']}: true core fact error NOT detected"
    # 关键身份错误必须 100% 识别
    if sample["sample_id"].startswith("starbucks_true_p0"):
        assert any(r.field_name == sample["expected_matched_gt_field"] for r in p0_results), \
            f"{sample['sample_id']}: expected GT field '{sample['expected_matched_gt_field']}' not matched"
```

**true_core_fact_errors.jsonl 必须包含至少 5 类错误：**
```json
{"sample_id": "starbucks_true_p0_001", "brand": "星巴克", "response": "星巴克是一家主要销售智能手机的科技公司。", "expected_subject_type": "target_brand", "expected_judgment": "contradicted", "expected_severity": "P0", "expected_matched_gt_field": "industry"}
```
（还应包含：错误核心产品、错误品牌身份、错误竞品关系、错误门店/业务模式）

**CI Gate:**
```
真实核心事实错误召回率 >= 90%
关键身份错误 (industry/official_name/category) 必须 100% 识别
误报类 P0 必须为 0
```

---

## 5. Go/No-Go (A5)

### 5.1 Go/No-Go 命令与 Artifact

**生成命令:**
```bash
python scripts/phase_a_go_no_go.py --brand starbucks --collection-target phase_a
python scripts/phase_a_go_no_go.py --brand starbucks --dry-run  # 只检查不写 artifact
```

**输出路径:** `artifacts/go_no_go/starbucks_phase_a_go_no_go_{timestamp}.json`

**审批规则:**
- system_owner 或 operator 执行
- overall_decision=go 才允许 A6 official run
- artifact 不允许覆盖，按 timestamp 存档
- latest.json symlink 指向最新一次

**Artifact 格式:**
```json
{
  "schema_version": "go_no_go_v1",
  "run_target": "starbucks_phase_a",
  "checked_at": "2026-06-01T...",
  "overall_decision": "go",
  "items": [
    {"name": "GT", "status": "go", "evidence": "14 fields complete", "blocking": true},
    {"name": "Templates", "status": "go", "evidence": "23/23 rendered, no {xxx}", "blocking": true},
    {"name": "TemplateHealth", "status": "go", "evidence": "critical_invalid=0", "blocking": true},
    {"name": "Mapping", "status": "go", "evidence": "10 KPI mapping loaded, 0 validation errors", "blocking": true},
    {"name": "Regression", "status": "go", "evidence": "false_positive P0=0, true P0 recall>=90%", "blocking": true},
    {"name": "PlatformHealth", "status": "go", "evidence": "deepseek=healthy, kimi=healthy, doubao=healthy", "blocking": true},
    {"name": "Coverage", "status": "go", "evidence": "estimated metric_eligible>=60%", "blocking": true},
    {"name": "ReportDelivery", "status": "go", "evidence": "md/docx/pdf templates tested", "blocking": true}
  ],
  "approved_by": "system_owner"
}
```

**规则:**
- A6 执行前读取 latest Go artifact
- No-Go 时 official_report=false，只做技术验证
- dry-run 不写正式 artifact，只输出检查结果
- Go artifact 与最终报告一起归档

### 5.2 平台健康自动检查

Go/No-Go 中 PlatformHealth 项从平台状态自动读取（而非人工判断）：
```
检查 platform_health_json.last_rate_limit_at
计算 cooldown_until = last_rate_limit_at + 30min
如果 now < cooldown_until → No-Go
```

### 5.3 采集顺序

```
DeepSeek → Doubao → Kimi
Kimi 使用付费参数但保持 rate limiter
失败平台单独 retry
```

### 5.4 失败路径 (P0-10)

**Kimi/Doubao 触发限流:**
```
标记 PLATFORM_RATE_LIMITED
等待 30min
只重跑失败平台（不重跑 DeepSeek）
更新 coverage_report
```

**metric_eligible_coverage < 60%:**
```
report_publishable = false
不生成正式报告
生成技术诊断报告（含补采建议）
```

**三格式任一失败:**
```
report_publishable = false
保留成功格式
标记 REPORT_FORMAT_FAILURE
修复格式后重新生成（不重跑采集）
```

**回归测试失败:**
```
禁止执行 A6
先修 detector / template / GT
重新跑 CI
```

---

## 6. 星巴克重跑验收 (A6)

| 模块 | 验收标准 |
|------|------|
| GT | 14 字段完整，缺失字段列表为空 |
| 模板 | 23/23 渲染成功，无 `{xxx}` |
| 模板健康 | critical_invalid = 0, optional_skipped = 0 (星巴克模式) |
| 采集 | 69 查询完成，平台覆盖率达标 |
| 幻觉检测 | 0 template_invalid sent to AI |
| 通用陈述 | 0 generic_statement counted as P0 |
| GT 不足 | 0 gt_insufficient counted as P0 |
| 模板错误 | 0 template_error counted as P0 |
| KPI | 每个 KPI 有 denominator + denominator_type |
| P0 幻觉 | Top 10 均有 target_brand subject + GT evidence |
| ReportQualitySummary | 报告首页展示，report_publishable = true |
| 样本覆盖 | metric_eligible_coverage >= 60% |
| 输出 | md/docx/pdf 三格式可打开 + 质量检查通过 |

### 6.1 A6 数据保全 (P0-7)

重跑完成后，必须归档到 `artifacts/phase_a/starbucks/{timestamp}/`：

```
artifacts/phase_a/starbucks/{timestamp}/
  go_no_go.json
  collection_run_snapshot.json
  coverage_report.json
  template_health_report.json
  report_quality_summary.json
  metrics_snapshot.json
  report.md
  report.docx
  report.pdf
  before_after_comparison.md
```

**必须保存的 ID:**
```
collection_run_id
metrics_snapshot_id
report_artifact_ids
go_no_go_artifact_path
baseline_collection_run_id = 6f51457c
baseline_report_artifact_id
```

**验收:** 星巴克重跑结果可复盘；报告与 Go/No-Go artifact 可对应；不依赖临时数据库状态。

---

## 7. 三格式报告质量检查 (A7)

### 自动化检查

```
文件存在性：md/docx/pdf 文件存在
文件大小：> 0 bytes
内容关键字：markdown 包含"本次诊断可信度概览"
格式完整性：docx 可打开（python-docx 提取文本非空）、pdf 可打开（PyPDF2 页数 > 0）
质量字段：三格式都包含 report_publishable 字样
```

### 人工检查

| 格式 | 检查项 |
|------|------|
| Markdown | 章节完整、表格不乱、ReportQualitySummary 可读 |
| DOCX | 标题层级正确、表格可读、中文字体正常、分页合理 |
| PDF | 中文不乱码、表格不溢出、关键图/表完整、页眉页脚正常 |
| 内容 | 三格式内容一致 |
| 语义 | 报告不出现"模板问题被计入 AI 幻觉"的描述 |
| 质量信息 | 三格式均包含质量摘要、有效样本数、排除项说明 |

### 7.1 格式失败回写 (P0-8)

如果 A7 检查发现任一格式失败：

```
CollectionRun.report_publishable = false
CollectionRun.blocking_reasons_json append REPORT_FORMAT_FAILURE
ReportQualitySummary.report_publishable = false
ReportQualitySummary.blocking_reasons append REPORT_FORMAT_FAILURE
ReportArtifact.status = failed 或 partial
```

修复格式后可重新生成报告（不重跑采集）。失败不只在日志，报告状态和质量摘要同步更新。

---

## 8. 修复前后对比报告 (A8)

10 节结构：

1. 总体结论
2. P0 幻觉数量变化
3. 误报类型变化
4. template_invalid 变化
5. generic_statement 误报变化
6. gt_insufficient 误报变化
7. KPI 变化
8. 有效样本数变化
9. 仍需人工复核的 P0
10. 下一步建议

对比表：

| 指标 | 修复前 (6f51457c) | 修复后 | 变化 | 解释 |
|------|:--:|:--:|:--:|------|
| confirmed_target_brand_p0_count | — | — | — | 真实品牌事实错误 |
| template_error_p0_count | — | 0 | — | 模板问题不再计入 P0 |
| generic_statement_p0_count | — | 0 | — | 通用陈述被排除 |
| gt_insufficient_p0_count | — | 0 | — | GT 不足单独归类 |
| template_skipped_count | 18 | 0 | -18 | GT 补齐后无跳过 |

**误报下降率:** `false_positive_reduction_rate = (old_fp - new_fp) / old_fp`，作为 Phase A 完成指标。

### Baseline 数据来源 (P0-9)

```
baseline_collection_run_id = 6f51457c
baseline_report_artifact_id = <from previous run>
baseline_metrics_snapshot_id = <from previous run>
baseline_hallucination_summary_json = <from previous run>
```

如果旧数据不完整：A8 中明确标注"修复前部分指标不可得"（unavailable），不用空值强行计算下降率。误报下降率只在 old_fp 可得且 >0 时计算。每个修复前数字必须可追溯到旧 Run。

---

## 8.1 P1 建议补齐项

| 编号 | 内容 | 状态 |
|------|------|:--:|
| P1-1 | QualitySummary 解释字段 | 已纳入 3.4 |
| P1-2 | 前端 API 预留 | 已纳入 4.6 |
| P1-3 | A7 半自动化检查 | 已纳入 A7 |
| P1-4 | 平台健康自动接入 Go/No-Go | 已纳入 5.2 |
| P1-5 | 误报下降率指标 | 已纳入 A8 |
| P1-6 | 报告版本说明 (Phase A disclaimer) | 已纳入 4.6 |
| P1-7 | 样本不足说明 | 当 report_publishable=false 时报告注明"部分结论受样本覆盖/平台限流/GT不足影响，未计入AI幻觉不代表无风险" |
| P1-8 | Soft warning 分级 | severity: notice / warning / review_recommended（OPTIONAL_SKIPPED→notice, PLATFORM_LOW_COVERAGE→warning, HIGH_GT_UNSUPPORTED→review_recommended） |
| P1-9 | Go/No-Go dry-run | `--dry-run` 标志（已纳入 5.1） |
| P1-10 | Metric Mapping 版本号 | YAML 加 schema_version + mapping_version（已纳入 4.2） |
| P1-11 | 回归样本 sample_source | 每条样本含 sample_source + created_reason（标注来自哪个 run，为什么进入回归集） |

---

## 9. 实施顺序 (含 Gate)

```
Step 0: 冻结枚举 (enums.py: 含 DenominatorType) + Pydantic schemas.py
Step 1: Alembic migration + pre/post 检查测试
Step 2: quality.py (build_report_quality_summary + 函数契约)
Step 3: quality.py (compute_report_publishable + 函数契约)
Step 4: engine.py (_build_template_health_report 口径修正 + 写入 CollectionRun)
Step 5: config/metric_template_mapping.yaml + validate_metric_mapping() + YAML 版本号
Step 6: metric_loader + is_query_eligible_for_kpi() + 启动/CI/A5 校验调用
Step 7: pipeline.py KPI mapping 过滤 + denominator 输出 + quality 模块集成
Step 8: regression jsonl 样本 + false_positive 排除测试 + true P0 召回测试
Step 9: Go/No-Go 命令 + artifact + dry-run
── GATE: CI 全部通过, Go artifact 生成 ──
Step 10: 星巴克 V2 采集 + 失败补采
Step 11: 分析 pipeline + 质量判定 + 报告生成
Step 12: A6 数据归档到 artifacts/phase_a/starbucks/{timestamp}/
Step 13: md/docx/pdf 自动检查 + 人工检查 + 失败回写
Step 14: 修复前后对比报告 (baseline=6f51457c)
Step 15: Phase A Done Definition 验收
Step 16: 用户验收确认
```

---

## 9.1 Phase A Done Definition (P0-10)

Phase A 完成必须同时满足：

```
□ A0-A8 全部实现
□ 新增测试全部通过
□ Go/No-Go artifact = go
□ 星巴克 69 查询完成或失败平台补采完成
□ metric_eligible_coverage >= 60%
□ report_publishable = true
□ md/docx/pdf 三格式质量检查通过
□ 修复前后对比报告生成
□ false_positive_reduction_rate 可计算或明确说明不可计算
□ 所有 Phase A artifact 归档到 artifacts/phase_a/starbucks/{timestamp}/
□ 用户审阅确认通过
```

**核心原则：不以"代码实现完"作为完成标准，以"可信报告验收通过"作为完成标准。**

---

## 10. 验收测试清单

### Migration / Schema
```
test_phase_a_migration_empty_db
test_phase_a_migration_existing_db
test_quality_json_schema_version_present
test_old_collection_run_defaults_report_publishable_false
```

### Enum / Mapping
```
test_all_question_types_are_known_enums
test_metric_mapping_schema_valid
test_metric_mapping_has_all_core_kpis
test_generic_advice_excluded_from_all_core_kpis
test_unknown_question_type_fails_mapping_validation
```

### 数据结构与发布判断
```
test_report_quality_summary_persisted
test_report_publishable_false_when_critical_template_invalid
test_report_publishable_false_when_metric_coverage_low
test_report_publishable_false_when_generic_p0_exists
test_report_publishable_false_when_p0_missing_gt_evidence
test_report_publishable_false_when_core_kpi_denominator_zero
test_report_publishable_true_with_warnings_only
test_blocking_reasons_are_human_readable
```

### Template Health
```
test_template_health_critical_invalid_blocks_publish
test_template_health_optional_missing_variable_skipped
test_template_health_starbucks_23_templates_all_valid
test_template_health_report_written_to_collection_run
test_invalid_templates_count_includes_all_invalid
test_blocking_invalid_templates_count_correct
test_template_health_starbucks_mode_requires_zero_skipped
test_template_health_production_mode_allows_optional_skipped
```

### Metric Mapping
```
test_metric_mapping_loaded_from_config
test_metric_denominator_excludes_wrong_question_type
test_metric_result_records_included_and_excluded_queries
test_generic_advice_excluded_from_all_core_kpis
```

### Regression CI
```
test_regression_template_error_never_p0
test_regression_generic_statement_never_p0
test_regression_gt_insufficient_never_contradicted
test_regression_true_core_fact_error_still_detected
test_true_identity_error_detected_p0
test_true_product_error_detected_p0
test_template_invalid_never_detected_as_hallucination
test_generic_statement_never_contradicted
test_gt_insufficient_never_contradicted
```

### Go/No-Go / Reports
```
test_go_no_go_artifact_written
test_no_go_blocks_official_report_generation
test_starbucks_go_no_go_all_go
test_report_quality_summary_in_markdown_docx_pdf
test_report_format_failure_marks_unpublishable
test_before_after_comparison_contains_false_positive_reduction
test_starbucks_report_quality_summary_publishable
test_starbucks_p0_top10_have_gt_evidence
test_starbucks_compare_before_after_false_positives_reduced
test_starbucks_outputs_md_docx_pdf
```

### Quality Function Contracts
```
test_build_quality_summary_with_empty_hallucinations
test_build_quality_summary_with_missing_template_health
test_compute_publishable_blocks_when_coverage_missing
test_compute_publishable_blocks_when_template_health_none
test_compute_publishable_outputs_json_serializable_reasons
```

### JSON Schema Validation
```
test_report_quality_summary_schema_valid
test_template_health_report_schema_valid
test_go_no_go_schema_valid
test_metric_details_schema_valid
test_schema_validation_failure_blocks_publishable
```

### Go/No-Go Execution
```
test_phase_a_go_no_go_command_writes_timestamped_artifact
test_phase_a_go_no_go_no_go_blocks_official_run
test_phase_a_go_no_go_dry_run_does_not_write_official_artifact
```

### Artifact Preservation
```
test_phase_a_artifact_directory_contains_required_files
test_report_artifacts_link_to_go_no_go_artifact
test_before_after_baseline_ids_present
test_baseline_unavailable_fields_marked_unavailable
```

### Report Format Failure
```
test_report_format_failure_updates_collection_run_publishable_false
test_report_format_failure_updates_quality_summary
test_report_format_regeneration_without_collection_rerun
```

---

## 11. 复盘参考

- **Kimi 429:** 连续采集触发限流，重跑间隔 > 30min，顺序 DeepSeek → Doubao → Kimi
- **Starlette 1.1.0:** TemplateResponse 签名 `(request, name, context)`
- **Jinja2:** `vm["items"]` 不是 `vm.items`
- **Tailwind CDN:** 不支持 `@apply`

---

*Define Final v3. 四轮审阅整合 — 函数契约/Pydantic校验/Migration检查/DenominatorType枚举/Mapping调用点/Go命令/数据保全/失败回写/Baseline来源/Done Definition。Build Ready。*
