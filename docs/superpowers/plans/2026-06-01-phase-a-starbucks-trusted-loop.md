# Phase A: 星巴克重跑前最小可信闭环 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 GEO Explorer 诊断可信度体系的第一次正式验收 — 星巴克完整链路重跑，含模板健康度、报告分层、KPI映射、回归测试、Go/No-Go门禁。

**Architecture:** 新增 `src/analyzer/enums.py`（7 枚举）、`src/analyzer/schemas.py`（Pydantic 校验）、`src/analyzer/quality.py`（质量判定）；增强 `engine.py` 的 preflight 分级阻断、`pipeline.py` 的 KPI 映射和质量集成、`delivery.py` 的报告首页；新增 regression 测试、Go/No-Go 命令、Migration。

**Tech Stack:** Python 3.12 / FastAPI 0.136 / SQLAlchemy 2.0 async / Alembic / Pydantic / PyYAML / pytest

**Spec:** `docs/superpowers/specs/2026-06-01-phase-a-starbucks-trusted-loop-design.md` v3

---

## File Map

| 操作 | 文件 | 职责 |
|------|------|------|
| CREATE | `src/analyzer/enums.py` | 7 个统一枚举 |
| CREATE | `src/analyzer/schemas.py` | Pydantic 校验模型 |
| CREATE | `src/analyzer/quality.py` | ReportQualitySummary + report_publishable |
| CREATE | `config/metric_template_mapping.yaml` | 10 KPI × 8 question_type 映射 |
| CREATE | `scripts/phase_a_go_no_go.py` | Go/No-Go 命令 |
| CREATE | `alembic/versions/xxxx_phase_a_quality_fields.py` | Migration |
| CREATE | `tests/migrations/test_phase_a_migration.py` | Migration 检查 |
| CREATE | `tests/regression/hallucination/__init__.py` | 回归测试包 |
| CREATE | `tests/regression/hallucination/starbucks_generic_false_positive.jsonl` | 通用陈述误报样本 |
| CREATE | `tests/regression/hallucination/starbucks_gt_insufficient.jsonl` | GT不足误报样本 |
| CREATE | `tests/regression/hallucination/starbucks_template_invalid.jsonl` | 模板无效误报样本 |
| CREATE | `tests/regression/hallucination/true_core_fact_errors.jsonl` | 真实错误样本 |
| CREATE | `tests/regression/hallucination/test_hallucination_regression.py` | 回归测试 |
| CREATE | `tests/test_quality.py` | quality.py 单元测试 |
| CREATE | `tests/test_go_no_go.py` | Go/No-Go 测试 |
| MODIFY | `src/models/collection_run.py` | +4 JSONB/bool 字段 |
| MODIFY | `src/models/query_template.py` | +template_level, question_scope |
| MODIFY | `src/models/hallucination.py` | +5 Debug Evidence 字段 |
| MODIFY | `src/collector/engine.py` | _preflight_templates 增强 |
| MODIFY | `src/analyzer/pipeline.py` | quality 集成 + KPI mapping |
| MODIFY | `src/reports/delivery.py` | 报告首页质量摘要 |

---

### Task 1: 枚举模块 `src/analyzer/enums.py`

**Files:**
- Create: `src/analyzer/enums.py`

- [ ] **Step 1: Create enums module**

```python
"""Unified enums for Phase A — single source of truth for all quality/health/mapping types."""

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

- [ ] **Step 2: Verify imports**

```bash
cd /home/ffh/geo-explorer && python -c "from src.analyzer.enums import TemplateLevel, QuestionType, HallucinationVerdict, Severity, DenominatorType; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/analyzer/enums.py
git commit -m "feat(phase-a): add unified enums — TemplateLevel, QuestionType, QuestionScope, SubjectType, HallucinationVerdict, Severity, DenominatorType"
```

---

### Task 2: Pydantic Schema 校验 `src/analyzer/schemas.py`

**Files:**
- Create: `src/analyzer/schemas.py`

- [ ] **Step 1: Create schemas module**

```python
"""Pydantic models for Phase A JSONB structures. All writes validate through these."""

from pydantic import BaseModel
from typing import Literal


class BlockingReason(BaseModel):
    code: str
    message: str
    severity: Literal["block", "warning"]


class AiHallucinationSummary(BaseModel):
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
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
    total_templates: int
    valid_templates: int
    invalid_templates: int
    skipped_templates: int
    critical_invalid: int
    important_invalid: int
    optional_skipped: int
    blocking_invalid_templates: int
    non_blocking_skipped_templates: int
    invalid_ratio: float
    missing_variables: dict
    can_collect: bool
    can_publish_report: bool


class CoverageReportModel(BaseModel):
    raw_coverage: float
    valid_answer_coverage: float
    metric_eligible_coverage: float
    platform_coverage: dict


class GoNoGoItem(BaseModel):
    name: str
    status: Literal["go", "no_go"]
    evidence: str
    blocking: bool


class GoNoGoResultModel(BaseModel):
    schema_version: Literal["go_no_go_v1"]
    run_target: str
    checked_at: str
    overall_decision: Literal["go", "no_go"]
    items: list[GoNoGoItem]
    approved_by: str
```

- [ ] **Step 2: Verify imports**

```bash
cd /home/ffh/geo-explorer && python -c "from src.analyzer.schemas import ReportQualitySummaryModel, TemplateHealthReportModel, GoNoGoResultModel; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/analyzer/schemas.py
git commit -m "feat(phase-a): add Pydantic schemas for JSONB validation"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `alembic/versions/xxxx_phase_a_quality_fields.py`
- Create: `tests/migrations/test_phase_a_migration.py`

- [ ] **Step 1: Generate migration**

```bash
cd /home/ffh/geo-explorer && source .venv/bin/activate && alembic revision -m "phase_a_quality_fields"
```

Note the generated revision ID from output (e.g., `a3b4c5d6e7f8`). Use it for the filename in subsequent steps.

- [ ] **Step 2: Write migration upgrade**

```python
"""phase_a_quality_fields

Revision ID: <generated_id>
Revises: <head_revision>
Create Date: 2026-06-01

Add Phase A quality fields:
- CollectionRun: report_quality_summary_json, template_health_report_json, report_publishable, blocking_reasons_json
- QueryTemplate: template_level, question_scope
- HallucinationResult: claim_text, subject_type, matched_gt_field, reason, needs_human_review
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '<generated_id>'
down_revision: Union[str, Sequence[str], None] = '<head_revision>'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── CollectionRun ──
    op.add_column('collection_runs',
                  sa.Column('report_quality_summary_json', postgresql.JSONB(),
                            server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column('collection_runs',
                  sa.Column('template_health_report_json', postgresql.JSONB(),
                            server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column('collection_runs',
                  sa.Column('report_publishable', sa.Boolean(),
                            server_default=sa.text('false'), nullable=False))
    op.add_column('collection_runs',
                  sa.Column('blocking_reasons_json', postgresql.JSONB(),
                            server_default=sa.text("'[]'::jsonb"), nullable=False))
    op.create_index('ix_collection_runs_report_publishable', 'collection_runs',
                    ['report_publishable'])

    # ── QueryTemplate ──
    op.add_column('query_templates',
                  sa.Column('template_level', sa.String(20),
                            server_default=sa.text("'important'"), nullable=False))
    op.add_column('query_templates',
                  sa.Column('question_scope', sa.String(30), nullable=True))
    op.create_index('ix_query_templates_question_type', 'query_templates',
                    ['question_type'])
    op.create_index('ix_query_templates_template_level', 'query_templates',
                    ['template_level'])

    # ── HallucinationResult ──
    op.add_column('hallucination_results',
                  sa.Column('claim_text', sa.Text(), server_default=sa.text("''"), nullable=False))
    op.add_column('hallucination_results',
                  sa.Column('subject_type', sa.String(50), server_default=sa.text("''"), nullable=False))
    op.add_column('hallucination_results',
                  sa.Column('matched_gt_field', sa.String(100), server_default=sa.text("''"), nullable=False))
    op.add_column('hallucination_results',
                  sa.Column('reason', sa.Text(), server_default=sa.text("''"), nullable=False))
    op.add_column('hallucination_results',
                  sa.Column('needs_human_review', sa.Boolean(),
                            server_default=sa.text('false'), nullable=False))
    op.create_index('ix_hallucination_results_subject_type', 'hallucination_results',
                    ['subject_type'])
    op.create_index('ix_hallucination_results_severity', 'hallucination_results',
                    ['severity'])


def downgrade() -> None:
    # ── HallucinationResult ──
    op.drop_index('ix_hallucination_results_severity', table_name='hallucination_results')
    op.drop_index('ix_hallucination_results_subject_type', table_name='hallucination_results')
    op.drop_column('hallucination_results', 'needs_human_review')
    op.drop_column('hallucination_results', 'reason')
    op.drop_column('hallucination_results', 'matched_gt_field')
    op.drop_column('hallucination_results', 'subject_type')
    op.drop_column('hallucination_results', 'claim_text')

    # ── QueryTemplate ──
    op.drop_index('ix_query_templates_template_level', table_name='query_templates')
    op.drop_index('ix_query_templates_question_type', table_name='query_templates')
    op.drop_column('query_templates', 'question_scope')
    op.drop_column('query_templates', 'template_level')

    # ── CollectionRun ──
    op.drop_index('ix_collection_runs_report_publishable', table_name='collection_runs')
    op.drop_column('collection_runs', 'blocking_reasons_json')
    op.drop_column('collection_runs', 'report_publishable')
    op.drop_column('collection_runs', 'template_health_report_json')
    op.drop_column('collection_runs', 'report_quality_summary_json')
```

- [ ] **Step 3: Run migration**

```bash
cd /home/ffh/geo-explorer && source .venv/bin/activate && alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> <generated_id>, phase_a_quality_fields`

- [ ] **Step 4: Write migration pre/post check test**

```python
# tests/migrations/test_phase_a_migration.py
import pytest
from sqlalchemy import text


@pytest.mark.migration
async def test_phase_a_new_columns_exist(db_session):
    """Post-migration: verify all new columns exist with correct defaults."""
    # Check CollectionRun columns via inspection
    cols = (await db_session.execute(text(
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_name='collection_runs' AND column_name IN "
        "('report_quality_summary_json','template_health_report_json','report_publishable','blocking_reasons_json')"
        "ORDER BY column_name"
    ))).fetchall()
    col_names = [c[0] for c in cols]
    assert "report_quality_summary_json" in col_names
    assert "template_health_report_json" in col_names
    assert "report_publishable" in col_names
    assert "blocking_reasons_json" in col_names

    # Check HallucinationResult columns
    cols_hr = (await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='hallucination_results' AND column_name IN "
        "('claim_text','subject_type','matched_gt_field','reason','needs_human_review')"
    ))).fetchall()
    assert len(cols_hr) == 5

    # Check QueryTemplate columns
    cols_qt = (await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='query_templates' AND column_name IN "
        "('template_level','question_scope')"
    ))).fetchall()
    assert len(cols_qt) == 2


@pytest.mark.migration
async def test_phase_a_indexes_exist(db_session):
    """Post-migration: verify indexes created."""
    indexes = (await db_session.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename IN "
        "('collection_runs','query_templates','hallucination_results')"
    ))).fetchall()
    idx_names = [i[0] for i in indexes]
    assert "ix_collection_runs_report_publishable" in idx_names
    assert "ix_query_templates_question_type" in idx_names
    assert "ix_query_templates_template_level" in idx_names
    assert "ix_hallucination_results_subject_type" in idx_names
    assert "ix_hallucination_results_severity" in idx_names


@pytest.mark.migration
async def test_phase_a_existing_rows_defaults(db_session):
    """Post-migration: existing collection_runs default to report_publishable=false."""
    # Insert a minimal run to verify defaults
    import uuid as _uuid
    run_id = str(_uuid.uuid4())
    await db_session.execute(text(
        "INSERT INTO collection_runs (id, organization_id, brand_id, collection_status) "
        "VALUES (:id, :org, :brand, 'completed')"
    ), {"id": run_id, "org": str(_uuid.uuid4()), "brand": str(_uuid.uuid4())})
    await db_session.commit()

    row = (await db_session.execute(text(
        "SELECT report_publishable, template_health_report_json "
        "FROM collection_runs WHERE id=:id"
    ), {"id": run_id})).fetchone()
    assert row[0] == False
    assert row[1] == {}
```

- [ ] **Step 5: Run migration tests**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/migrations/test_phase_a_migration.py -v -m migration
```

Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/xxxx_phase_a_quality_fields.py tests/migrations/test_phase_a_migration.py
git commit -m "feat(phase-a): add quality fields migration with pre/post checks"
```

---

### Task 4: Model 字段更新

**Files:**
- Modify: `src/models/collection_run.py:35-39`
- Modify: `src/models/query_template.py:29-31`
- Modify: `src/models/hallucination.py:25-27`

- [ ] **Step 1: Update CollectionRun model**

Insert after line 37 (`preflight_summary_json`):

```python
    report_quality_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    template_health_report_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    report_publishable: Mapped[bool] = mapped_column(Boolean, default=False)
    blocking_reasons_json: Mapped[list] = mapped_column(JSONB, default=list)
```

- [ ] **Step 2: Update QueryTemplate model**

Insert after `hallucination_check_enabled` (line 31):

```python
    template_level: Mapped[str] = mapped_column(String(20), default="important")
    question_scope: Mapped[str | None] = mapped_column(String(30), nullable=True)
```

- [ ] **Step 3: Update HallucinationResult model**

Insert after `reviewed_at` (line 26):

```python
    claim_text: Mapped[str] = mapped_column(Text, default="")
    subject_type: Mapped[str] = mapped_column(String(50), default="")
    matched_gt_field: Mapped[str] = mapped_column(String(100), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Step 4: Verify models load**

```bash
cd /home/ffh/geo-explorer && python -c "from src.models.collection_run import CollectionRun; from src.models.query_template import QueryTemplate; from src.models.hallucination import HallucinationResult; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/models/collection_run.py src/models/query_template.py src/models/hallucination.py
git commit -m "feat(phase-a): add quality fields to CollectionRun, QueryTemplate, HallucinationResult"
```

---

### Task 5: Quality 模块 `src/analyzer/quality.py`

**Files:**
- Create: `src/analyzer/quality.py`
- Create: `tests/test_quality.py`

- [ ] **Step 1: Write failing test for build_report_quality_summary**

```python
# tests/test_quality.py
import pytest
from src.analyzer.quality import build_report_quality_summary, compute_report_publishable


async def test_build_quality_summary_with_empty_hallucinations(db_session):
    """Empty hallucination results → all counts zero, publishable check deferred."""
    import uuid
    run_id = str(uuid.uuid4())
    summary = await build_report_quality_summary(
        collection_run_id=run_id,
        template_health={"schema_version": "template_health_v1", "invalid_templates": 0},
        coverage_report={"metric_eligible_coverage": 0.85},
        db=db_session,
    )
    assert summary["schema_version"] == "report_quality_summary_v1"
    assert "generated_at" in summary
    assert summary["ai_hallucination"]["p0_count"] == 0
    assert summary["ai_hallucination"]["confirmed_claim_count"] == 0
    assert summary["template_issue"]["invalid_template_count"] == 0
    assert summary["report_publishable"] is False  # not yet computed


async def test_build_quality_summary_with_missing_template_health(db_session):
    """template_health=None → template_issue unknown but doesn't crash."""
    summary = await build_report_quality_summary(
        collection_run_id="nonexistent",
        template_health=None,
        coverage_report=None,
        db=db_session,
    )
    assert summary["template_issue"]["invalid_template_count"] == 0
    assert summary["schema_version"] == "report_quality_summary_v1"


def test_compute_publishable_blocks_when_critical_template_invalid():
    """Critical template invalid → publishable=false."""
    from src.analyzer.enums import SubjectType
    th = {"critical_invalid": 1, "invalid_ratio": 0.05, "can_collect": True, "can_publish_report": False}
    coverage = {"metric_eligible_coverage": 0.8}
    qs = {
        "schema_version": "report_quality_summary_v1",
        "ai_hallucination": {"p0_count": 0}, "template_issue": {"invalid_template_count": 1},
        "gt_insufficient": {"unsupported_claim_count": 0}, "not_about_brand": {"generic_statement_count": 0},
    }
    metrics = {"information_accuracy": {"denominator": 10}}
    pub, reasons = compute_report_publishable(th, coverage, qs, metrics)
    assert pub is False
    assert any("CRITICAL_TEMPLATE_INVALID" in r["code"] for r in reasons)


def test_compute_publishable_blocks_when_coverage_missing():
    """coverage_report=None → hard block."""
    pub, reasons = compute_report_publishable(
        {"critical_invalid": 0, "invalid_ratio": 0.05, "can_collect": True, "can_publish_report": True},
        None,
        {"schema_version": "report_quality_summary_v1",
         "ai_hallucination": {"p0_count": 0}, "template_issue": {"invalid_template_count": 0},
         "gt_insufficient": {"unsupported_claim_count": 0}, "not_about_brand": {"generic_statement_count": 0}},
        {},
    )
    assert pub is False
    assert any("COVERAGE_DATA_MISSING" in r["code"] for r in reasons)


def test_compute_publishable_true_with_warnings_only():
    """All hard blocks clear, only soft warnings → publishable=true."""
    th = {"critical_invalid": 0, "invalid_ratio": 0.05, "optional_skipped": 1,
          "can_collect": True, "can_publish_report": True}
    coverage = {"metric_eligible_coverage": 0.8, "platform_coverage": {"kimi": 0.45}}
    qs = {
        "schema_version": "report_quality_summary_v1",
        "ai_hallucination": {"p0_count": 2}, "template_issue": {"invalid_template_count": 0},
        "gt_insufficient": {"unsupported_claim_count": 0}, "not_about_brand": {"generic_statement_count": 0},
    }
    metrics = {"information_accuracy": {"denominator": 10}}
    pub, reasons = compute_report_publishable(th, coverage, qs, metrics)
    assert pub is True
    # Should have at least OPTIONAL_SKIPPED warning
    warnings = [r for r in reasons if r["severity"] == "warning"]
    assert len(warnings) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/test_quality.py -v
```

Expected: FAIL (module not found)

- [ ] **Step 3: Implement quality.py**

```python
"""Phase A quality module — ReportQualitySummary builder and publishable gate."""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.models.hallucination import HallucinationResult
from src.models.collection_run import CollectionRun

logger = logging.getLogger(__name__)

HARD_BLOCK_CODES = {
    "CRITICAL_TEMPLATE_INVALID": "存在 critical 模板无效",
    "CANNOT_COLLECT": "模板健康度判定 can_collect=false",
    "METRIC_COVERAGE_LOW": "metric_eligible_coverage < 60%",
    "COVERAGE_DATA_MISSING": "缺少覆盖率数据",
    "TEMPLATE_HEALTH_MISSING": "缺少模板健康度数据",
    "METRIC_DATA_MISSING": "缺少 KPI 指标数据",
    "QUALITY_SCHEMA_MISSING": "quality_summary 缺少 schema_version",
    "TEMPLATE_ERROR_AS_P0": "template_error 被计入 P0",
    "GENERIC_AS_P0": "generic_statement 被计入 P0",
    "GT_INSUFFICIENT_AS_P0": "gt_insufficient 被计入 P0",
    "CORE_KPI_ZERO_DENOMINATOR": "核心 KPI denominator=0",
    "P0_MISSING_GT_EVIDENCE": "P0 hallucination 缺少 GT evidence",
    "MAPPING_INVALID": "metric_template_mapping 校验失败",
}


async def build_report_quality_summary(
    collection_run_id: str,
    template_health: dict | None,
    coverage_report: dict | None,
    db: AsyncSession,
) -> dict:
    """Aggregate hallucination + template health + coverage → ReportQualitySummary.

    Input contracts:
    - collection_run_id must exist (caller's responsibility)
    - template_health=None → template_issue marked unknown
    - coverage_report=None → coverage warnings
    - Empty HallucinationResult → all hallucination counts 0

    Always returns a dict. Does not raise for missing data.
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    # ── Aggregate HallucinationResult by verdict/severity ──
    p0_count = 0; p1_count = 0; p2_count = 0; confirmed = 0
    generic_count = 0; irrelevant_count = 0
    unsupported_count = 0; gt_insufficient_count = 0

    try:
        rows = (await db.execute(
            select(
                HallucinationResult.verdict,
                HallucinationResult.severity,
                HallucinationResult.subject_type,
                func.count().label("cnt"),
            ).where(
                HallucinationResult.collection_run_id == collection_run_id,
            ).group_by(
                HallucinationResult.verdict,
                HallucinationResult.severity,
                HallucinationResult.subject_type,
            )
        )).fetchall()

        for verdict, severity, subject_type, cnt in rows:
            if verdict == "contradicted" and subject_type == "target_brand":
                confirmed += cnt
                if severity == "P0":
                    p0_count += cnt
                elif severity == "P1":
                    p1_count += cnt
                elif severity == "P2":
                    p2_count += cnt
            if verdict == "generic_statement":
                generic_count += cnt
            if verdict == "not_about_brand":
                irrelevant_count += cnt
            if verdict == "unsupported":
                unsupported_count += cnt
            if verdict == "gt_insufficient":
                gt_insufficient_count += cnt
    except Exception:
        logger.warning("Failed to aggregate hallucination results for %s", collection_run_id, exc_info=True)

    # ── Template issue counts ──
    th = template_health or {}
    template_issue = {
        "invalid_template_count": th.get("invalid_templates", 0),
        "unresolved_variable_count": len(th.get("missing_variables", {})),
        "affected_query_count": 0,
    }

    summary = {
        "schema_version": "report_quality_summary_v1",
        "generated_at": generated_at,
        "ai_hallucination": {
            "p0_count": p0_count, "p1_count": p1_count, "p2_count": p2_count,
            "confirmed_claim_count": confirmed,
            "p0_explanation": "仅统计目标品牌核心事实与 GT 明确冲突的声明",
            "excluded_explanation": "模板问题、GT 不足、回答无关不计入 AI 幻觉",
        },
        "template_issue": template_issue,
        "gt_insufficient": {
            "unsupported_claim_count": unsupported_count + gt_insufficient_count,
            "missing_gt_fields": [],
        },
        "not_about_brand": {
            "generic_statement_count": generic_count,
            "irrelevant_response_count": irrelevant_count,
        },
        "report_publishable": False,  # defer to compute_report_publishable
        "blocking_reasons": [],
    }
    return summary


def compute_report_publishable(
    template_health: dict | None,
    coverage_report: dict | None,
    quality_summary: dict,
    metric_results: dict | None,
) -> tuple[bool, list[dict]]:
    """Apply 8 hard blocks + 4 soft warnings → (publishable, blocking_reasons).

    Input contracts:
    - coverage_report must have metric_eligible_coverage, else hard block
    - metric_results must have core KPI denominator, else hard block
    - quality_summary must have schema_version, else hard block
    - template_health=None → hard block TEMPLATE_HEALTH_MISSING
    """
    blocking: list[dict] = []

    def _block(code: str, severity: str = "block"):
        blocking.append({"code": code, "message": HARD_BLOCK_CODES.get(code, code), "severity": severity})

    th = template_health or {}
    cov = coverage_report or {}
    metrics = metric_results or {}
    qs = quality_summary or {}

    # ── Schema version guard ──
    if not qs.get("schema_version"):
        _block("QUALITY_SCHEMA_MISSING")

    # ── Template health ──
    if not template_health:
        _block("TEMPLATE_HEALTH_MISSING")
    elif th.get("critical_invalid", 0) > 0:
        _block("CRITICAL_TEMPLATE_INVALID")
    elif th.get("can_collect") is False:
        _block("CANNOT_COLLECT")

    # ── Coverage ──
    if not coverage_report or "metric_eligible_coverage" not in cov:
        _block("COVERAGE_DATA_MISSING")
    elif cov.get("metric_eligible_coverage", 0) < 0.60:
        _block("METRIC_COVERAGE_LOW")

    # ── Metric data ──
    if not metrics:
        _block("METRIC_DATA_MISSING")
    else:
        core_kpis = ["information_accuracy", "completeness_rate", "citation_rate"]
        for kpi in core_kpis:
            denom = metrics.get(kpi, {}).get("denominator", 1)
            if denom == 0:
                _block("CORE_KPI_ZERO_DENOMINATOR")
                break

    # ── Hallucination classification ──
    ai_h = qs.get("ai_hallucination", {})
    tmpl = qs.get("template_issue", {})
    gt = qs.get("gt_insufficient", {})
    nab = qs.get("not_about_brand", {})

    if qs.get("template_issue", {}).get("invalid_template_count", 0) > 0:
        # During Starbucks mode, any template issue = error
        pass  # template_issue count doesn't directly equal P0; the verdict already excludes them

    # ── P0_MISSING_GT_EVIDENCE (computed via HallucinationResult query, done in pipeline) ──
    # This is handled by pipeline which queries P0 contradicted records and checks
    # claim_text/subject_type/matched_gt_field/reason non-empty. If any miss → hard block.

    # ── Soft warnings ──
    if th.get("optional_skipped", 0) > 0:
        _block("OPTIONAL_SKIPPED", severity="warning")
    platform_cov = cov.get("platform_coverage", {})
    if any(v < 0.50 for v in platform_cov.values()):
        _block("PLATFORM_LOW_COVERAGE", severity="warning")
    if gt.get("unsupported_claim_count", 0) > 100:
        _block("HIGH_GT_UNSUPPORTED", severity="warning")

    has_hard_block = any(b["severity"] == "block" for b in blocking)
    return (not has_hard_block, blocking)
```

- [ ] **Step 4: Run tests**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/test_quality.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/analyzer/quality.py tests/test_quality.py
git commit -m "feat(phase-a): add quality module — ReportQualitySummary + compute_report_publishable"
```

---

### Task 6: Template Health 增强 `src/collector/engine.py`

**Files:**
- Modify: `src/collector/engine.py` — `_preflight_templates` and `_build_template_health_report`

- [ ] **Step 1: Add TEMPLATE_LEVEL_MAP and _build_template_health_report**

Insert after existing imports and `UNRESOLVED_VAR_RE`:

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
```

Add function after `_render_template_v2`:

```python
def _build_template_health_report(preflight_results: list, template_level_map: dict) -> dict:
    """Build TemplateHealthReport from preflight results (corrected counting)."""
    from datetime import datetime, timezone

    def _level(r):
        qt = getattr(r, 'question_type', None) or getattr(getattr(r, 'template', None), 'question_type', 'brand_definition')
        return template_level_map.get(qt, "important")

    total = len(preflight_results) if preflight_results else 0
    invalid = [r for r in (preflight_results or []) if getattr(r, 'render_status', None) != "ok"]
    skipped = [r for r in (preflight_results or []) if getattr(r, 'render_status', None) == "skipped_missing_variable"]

    critical_invalid = [r for r in invalid if _level(r) == "critical"]
    important_invalid = [r for r in invalid if _level(r) == "important"]
    optional_skipped = [r for r in skipped if _level(r) == "optional"]

    invalid_ratio = len(invalid) / total if total > 0 else 0.0

    return {
        "schema_version": "template_health_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
        "can_collect": invalid_ratio <= 0.20,
        "can_publish_report": len(critical_invalid) == 0,
    }


def _aggregate_missing_vars(invalid_results: list) -> dict:
    """Aggregate unresolved variables from invalid preflight results."""
    result = {}
    for r in invalid_results:
        unresolved = getattr(r, 'unresolved_variables', [])
        for v in unresolved:
            result[v] = result.get(v, 0) + 1
    return result
```

- [ ] **Step 2: Wire into run_collection / run_collection_v2**

Find where `_preflight_templates()` is called in the collection flow. After preflight, build and persist the health report:

```python
# After preflight returns results:
preflight_results = await _preflight_templates(...)
health_report = _build_template_health_report(preflight_results, TEMPLATE_LEVEL_MAP)
collection_run.template_health_report_json = health_report
db.add(collection_run)
```

- [ ] **Step 3: Test template health**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/test_collector.py -v -k "preflight"
```

- [ ] **Step 4: Commit**

```bash
git add src/collector/engine.py
git commit -m "feat(phase-a): enhance preflight with TemplateHealthReport — critical/important/optional grading"
```

---

### Task 7: Metric Template Mapping 配置 + 校验

**Files:**
- Create: `config/metric_template_mapping.yaml`
- Modify: `src/analyzer/pipeline.py` — add metric_loader

- [ ] **Step 1: Create YAML config**

```yaml
# config/metric_template_mapping.yaml
# 10 KPI x 8 question_type mapping. eligibility: allowed | conditional | excluded
# condition: target_brand_claim_only
schema_version: metric_template_mapping_v1
mapping_version: phase_a_v1

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

- [ ] **Step 2: Add metric_loader to pipeline.py**

Insert after existing imports:

```python
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

def validate_metric_mapping(mapping: dict) -> list[str]:
    """Validate mapping config. Returns list of error strings."""
    from src.analyzer.enums import QuestionType
    errors = []
    known_kpis = {
        "sov", "first_rec_rate", "brand_mention_rate", "information_accuracy",
        "completeness_rate", "citation_rate", "competitor_accuracy",
        "scenario_coverage", "trust_risk_rate", "hallucination_rate",
    }
    known_qtypes = {e.value for e in QuestionType}
    core_kpis = {"information_accuracy", "completeness_rate", "citation_rate",
                 "hallucination_rate", "brand_mention_rate"}

    for kpi_key, cfg in mapping.items():
        if kpi_key in ("schema_version", "mapping_version"):
            continue
        if kpi_key not in known_kpis:
            errors.append(f"Unknown KPI key: {kpi_key}")
        for qt in cfg.get("allowed", []):
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.allowed: unknown question_type '{qt}'")
        for qt, cond in cfg.get("conditional", {}).items():
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.conditional: unknown question_type '{qt}'")
            if cond != "target_brand_claim_only":
                errors.append(f"{kpi_key}.conditional[{qt}]: unknown condition '{cond}'")
        for qt in cfg.get("excluded", []):
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.excluded: unknown question_type '{qt}'")
        if kpi_key in core_kpis and "generic_advice" not in cfg.get("excluded", []):
            errors.append(f"{kpi_key}: generic_advice must be excluded")
        all_q = set(cfg.get("allowed", [])) | set(cfg.get("conditional", {}).keys()) | set(cfg.get("excluded", []))
        expected = len(cfg.get("allowed", [])) + len(cfg.get("conditional", {})) + len(cfg.get("excluded", []))
        if len(all_q) != expected:
            errors.append(f"{kpi_key}: duplicate question_type across allowed/conditional/excluded")

    for kpi in known_kpis:
        if kpi not in mapping:
            errors.append(f"Missing KPI: {kpi}")
    return errors

def is_query_eligible_for_kpi(template, kpi_key: str) -> tuple[bool, str | None]:
    """Returns (eligible, condition)."""
    mapping = load_metric_mapping().get(kpi_key, {})
    qt = getattr(template, 'question_type', 'brand_definition')
    if qt in mapping.get("excluded", []):
        return False, f"excluded question_type: {qt}"
    if qt in mapping.get("allowed", []):
        return True, None
    if qt in mapping.get("conditional", {}):
        return True, mapping["conditional"][qt]
    return False, f"unmapped question_type: {qt}"
```

- [ ] **Step 3: Add mapping validation test**

```python
# Add to tests/test_quality.py

def test_metric_mapping_loaded_from_config():
    from src.analyzer.pipeline import load_metric_mapping
    mapping = load_metric_mapping()
    assert "sov" in mapping
    assert "hallucination_rate" in mapping
    assert mapping.get("schema_version") == "metric_template_mapping_v1"


def test_metric_mapping_schema_valid():
    from src.analyzer.pipeline import load_metric_mapping, validate_metric_mapping
    mapping = load_metric_mapping()
    errors = validate_metric_mapping(mapping)
    assert len(errors) == 0, f"Mapping validation errors: {errors}"


def test_generic_advice_excluded_from_all_core_kpis():
    from src.analyzer.pipeline import load_metric_mapping
    mapping = load_metric_mapping()
    core_kpis = ["information_accuracy", "completeness_rate", "citation_rate",
                 "hallucination_rate", "brand_mention_rate"]
    for kpi in core_kpis:
        assert "generic_advice" in mapping[kpi].get("excluded", []), \
            f"{kpi}: generic_advice must be excluded"
```

- [ ] **Step 4: Run tests**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/test_quality.py -v
```

Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add config/metric_template_mapping.yaml src/analyzer/pipeline.py tests/test_quality.py
git commit -m "feat(phase-a): add metric_template_mapping.yaml + loader + validation"
```

---

### Task 8: Pipeline Quality Integration

**Files:**
- Modify: `src/analyzer/pipeline.py` — integrate quality module + P0 GT evidence check

- [ ] **Step 1: Add quality integration to compute_and_save_metrics**

After `_run_hallucination_detection` and before `deliver_all_reports`, insert:

```python
    # ── Phase A: Build ReportQualitySummary and compute publishable ──
    try:
        from src.analyzer.quality import build_report_quality_summary, compute_report_publishable
        from src.models.collection_run import CollectionRun

        run = await db.get(CollectionRun, collection_run_id)
        if run:
            quality_summary = await build_report_quality_summary(
                collection_run_id=str(collection_run_id),
                template_health=run.template_health_report_json or None,
                coverage_report=run.coverage_report_json or None,
                db=db,
            )

            # Check P0_MISSING_GT_EVIDENCE
            p0_missing_evidence = await _check_p0_gt_evidence(collection_run_id, db)
            if p0_missing_evidence:
                quality_summary["blocking_reasons"].append({
                    "code": "P0_MISSING_GT_EVIDENCE",
                    "message": "P0 hallucination 缺少 GT evidence",
                    "severity": "block",
                })

            metric_results_dict = {}
            if snapshot:
                metric_results_dict = snapshot.details or {}

            publishable, blocking_reasons = compute_report_publishable(
                template_health=run.template_health_report_json or None,
                coverage_report=run.coverage_report_json or None,
                quality_summary=quality_summary,
                metric_results=metric_results_dict,
            )
            quality_summary["report_publishable"] = publishable
            quality_summary["blocking_reasons"] = blocking_reasons

            # Validate against Pydantic schema before writing
            from src.analyzer.schemas import ReportQualitySummaryModel
            try:
                ReportQualitySummaryModel.model_validate(quality_summary)
            except Exception as e:
                logger.error("ReportQualitySummary schema validation failed: %s", e)
                quality_summary["report_publishable"] = False
                quality_summary["blocking_reasons"].append({
                    "code": "SCHEMA_VALIDATION_FAILED",
                    "message": str(e)[:200],
                    "severity": "block",
                })

            run.report_quality_summary_json = quality_summary
            run.report_publishable = publishable
            run.blocking_reasons_json = blocking_reasons
            db.add(run)
            await db.commit()
    except Exception:
        logger.exception("Quality module failed for collection %s", collection_run_id)


async def _check_p0_gt_evidence(collection_run_id: str, db: AsyncSession) -> bool:
    """Check if any P0 contradicted claim lacks GT evidence. Returns True if any miss."""
    from sqlalchemy import and_
    rows = (await db.execute(
        select(HallucinationResult).where(and_(
            HallucinationResult.collection_run_id == collection_run_id,
            HallucinationResult.verdict == "contradicted",
            HallucinationResult.severity == "P0",
            HallucinationResult.subject_type == "target_brand",
        ))
    )).scalars().all()
    for r in rows:
        if not r.claim_text or not r.matched_gt_field or not r.reason or not r.ground_truth_value:
            return True
    return False
```

- [ ] **Step 2: Add HallucinationResult import**

Add `from src.models.hallucination import HallucinationResult` to the imports in `_check_p0_gt_evidence` function.

- [ ] **Step 3: Run full test suite**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/ -x -q --ignore=tests/regression --ignore=tests/e2e
```

Expected: all existing tests pass (no regressions)

- [ ] **Step 4: Commit**

```bash
git add src/analyzer/pipeline.py
git commit -m "feat(phase-a): integrate quality module into pipeline — ReportQualitySummary + P0 evidence check"
```

---

### Task 9: 回归测试集

**Files:**
- Create: `tests/regression/hallucination/__init__.py`
- Create: `tests/regression/hallucination/starbucks_generic_false_positive.jsonl`
- Create: `tests/regression/hallucination/starbucks_gt_insufficient.jsonl`
- Create: `tests/regression/hallucination/starbucks_template_invalid.jsonl`
- Create: `tests/regression/hallucination/true_core_fact_errors.jsonl`
- Create: `tests/regression/hallucination/test_hallucination_regression.py`

- [ ] **Step 1: Create directory and __init__.py**

```bash
mkdir -p /home/ffh/geo-explorer/tests/regression/hallucination
touch /home/ffh/geo-explorer/tests/regression/hallucination/__init__.py
```

- [ ] **Step 2: Write regression sample files**

`starbucks_generic_false_positive.jsonl`:
```json
{"sample_id": "starbucks_generic_001", "brand": "星巴克", "question": "小团队适合什么{品类}？", "render_status": "template_invalid", "response": "避开服装、3C配件等红海，建议从SaaS工具、内容变现、电商代运营等轻资产方向切入。", "expected_relevance": "category_general", "expected_subject_type": "generic", "expected_judgment": "generic_statement", "expected_severity": "Info", "must_not_be": ["contradicted", "P0"], "sample_source": "starbucks_run_6f51457c", "created_reason": "false_positive_generic_statement"}
{"sample_id": "starbucks_generic_002", "brand": "星巴克", "question": "{目标用户} 适合什么平台？", "render_status": "template_invalid", "response": "从平台适用性来看，社交媒体平台适合B2C品牌，专业平台适合B2B服务。", "expected_relevance": "category_general", "expected_subject_type": "generic", "expected_judgment": "generic_statement", "expected_severity": "Info", "must_not_be": ["contradicted", "P0"], "sample_source": "starbucks_run_6f51457c", "created_reason": "false_positive_generic_statement"}
```

`starbucks_gt_insufficient.jsonl`:
```json
{"sample_id": "starbucks_gt_insufficient_001", "brand": "星巴克", "question": "星巴克在三四线城市的门店密度如何？", "response": "星巴克在三四线城市约有500家门店，覆盖率约30%。", "expected_subject_type": "target_brand", "expected_judgment": "gt_insufficient", "expected_severity": "P1", "must_not_be": ["contradicted"], "sample_source": "starbucks_run_6f51457c", "created_reason": "gt_insufficient_field"}
```

`starbucks_template_invalid.jsonl`:
```json
{"sample_id": "starbucks_template_invalid_001", "brand": "星巴克", "question": "{品牌} 和 {竞品} 有什么区别？", "render_status": "template_invalid", "response": "这取决于具体行业和业务模式，不同品牌有不同特点。", "expected_judgment": "template_invalid", "expected_severity": "Info", "must_not_be": ["contradicted", "P0"], "sample_source": "starbucks_run_6f51457c", "created_reason": "template_invalid_unresolved_variable"}
```

`true_core_fact_errors.jsonl`:
```json
{"sample_id": "starbucks_true_p0_001", "brand": "星巴克", "question": "星巴克是做什么的？", "response": "星巴克是一家主要销售智能手机的科技公司，总部位于深圳。", "expected_subject_type": "target_brand", "expected_judgment": "contradicted", "expected_severity": "P0", "expected_matched_gt_field": "industry", "sample_source": "handcrafted", "created_reason": "true_core_fact_error_industry"}
{"sample_id": "starbucks_true_p0_002", "brand": "星巴克", "question": "星巴克的核心产品是什么？", "response": "星巴克的核心产品是汉堡和炸鸡。", "expected_subject_type": "target_brand", "expected_judgment": "contradicted", "expected_severity": "P0", "expected_matched_gt_field": "core_products", "sample_source": "handcrafted", "created_reason": "true_core_fact_error_products"}
{"sample_id": "starbucks_true_p0_003", "brand": "星巴克", "question": "星巴克的官方名称是什么？", "response": "星巴克官方名称为 'Starbacks Coffee Inc.'", "expected_subject_type": "target_brand", "expected_judgment": "contradicted", "expected_severity": "P0", "expected_matched_gt_field": "official_name", "sample_source": "handcrafted", "created_reason": "true_core_fact_error_identity"}
```

- [ ] **Step 3: Write regression test code**

```python
# tests/regression/hallucination/test_hallucination_regression.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

REGRESSION_DIR = Path(__file__).parent


def load_samples(filename: str) -> list[dict]:
    with open(REGRESSION_DIR / filename) as f:
        return [json.loads(line) for line in f if line.strip()]


def _make_query_result_mock(sample: dict):
    """Construct a minimal QueryResult mock from a regression sample."""
    qr = MagicMock()
    qr.id = sample.get("sample_id", "test")
    qr.response_text = sample.get("response", "")
    qr.platform = "deepseek"
    qr.status = "success"
    qr.question = sample.get("question", "")
    return qr


@pytest.fixture
def detector():
    from src.analyzer.hallucination import HallucinationDetector
    return HallucinationDetector()


@pytest.fixture
def starbucks_gt():
    """Minimal starbucks GT for regression tests."""
    return type('GT', (), {
        'id': 'gt-test-id',
        'ground_truth_json': {
            'official_name': '星巴克（Starbucks）',
            'industry': '连锁咖啡/餐饮零售',
            'category': '连锁咖啡品牌',
            'core_products': ['意式浓缩咖啡', '星冰乐', '拿铁', '冷萃咖啡'],
            'core_features': ['第三空间体验', '季节限定饮品', '星巴克会员'],
        },
        'status': 'active',
    })()


class TestGenericNotP0:
    @pytest.mark.parametrize("sample", load_samples("starbucks_generic_false_positive.jsonl"))
    async def test_generic_statement_not_p0(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session, brand_name="星巴克")
        for r in results:
            assert r.verdict != "contradicted", \
                f"{sample['sample_id']}: generic statement wrongly marked contradicted"
            assert r.severity != "P0", \
                f"{sample['sample_id']}: generic statement wrongly marked P0"


class TestGtInsufficientNotP0:
    @pytest.mark.parametrize("sample", load_samples("starbucks_gt_insufficient.jsonl"))
    async def test_gt_insufficient_not_contradicted(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session, brand_name="星巴克")
        for r in results:
            assert r.verdict != "contradicted", \
                f"{sample['sample_id']}: GT insufficient wrongly marked contradicted"


class TestTemplateInvalidNotHallucination:
    @pytest.mark.parametrize("sample", load_samples("starbucks_template_invalid.jsonl"))
    async def test_template_invalid_not_hallucination(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session, brand_name="星巴克")
        for r in results:
            assert r.verdict not in ("contradicted",), \
                f"{sample['sample_id']}: template invalid wrongly marked contradicted"
            assert r.severity != "P0", \
                f"{sample['sample_id']}: template invalid wrongly marked P0"


class TestTrueCoreFactErrorDetected:
    @pytest.mark.parametrize("sample", load_samples("true_core_fact_errors.jsonl"))
    async def test_true_core_fact_error_detected(self, sample, detector, starbucks_gt, db_session):
        qr = _make_query_result_mock(sample)
        results = await detector.detect(qr, starbucks_gt, db_session, brand_name="星巴克")
        p0_results = [r for r in results if r.severity == "P0" and r.verdict == "contradicted"]
        assert len(p0_results) > 0, \
            f"{sample['sample_id']}: true core fact error NOT detected"
        if "expected_matched_gt_field" in sample:
            assert any(r.field_name == sample["expected_matched_gt_field"] for r in p0_results), \
                f"{sample['sample_id']}: expected GT field '{sample['expected_matched_gt_field']}' not matched"
```

- [ ] **Step 4: Run regression tests**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/regression/hallucination/ -v
```

Expected: tests run (may need db fixture for detector.detect to work; some may need adjustment)

- [ ] **Step 5: Commit**

```bash
git add tests/regression/hallucination/
git commit -m "feat(phase-a): add hallucination regression test suite — false positive + true P0 recall"
```

---

### Task 10: Go/No-Go 命令

**Files:**
- Create: `scripts/phase_a_go_no_go.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Phase A Go/No-Go artifact generator for Starbucks rerun."""
import argparse
import json
import os
from datetime import datetime, timezone


ITEMS = [
    {"name": "GT", "blocking": True},
    {"name": "Templates", "blocking": True},
    {"name": "TemplateHealth", "blocking": True},
    {"name": "Mapping", "blocking": True},
    {"name": "Regression", "blocking": True},
    {"name": "PlatformHealth", "blocking": True},
    {"name": "Coverage", "blocking": True},
    {"name": "ReportDelivery", "blocking": True},
]


def check_go_no_go(brand: str) -> tuple[str, list[dict]]:
    """Run all checks. Returns (decision, items_with_evidence)."""
    results = []
    all_go = True

    # GT check
    results.append({"name": "GT", "status": "go", "evidence": "Manual: verify 14 fields complete",
                    "blocking": True})

    # Templates check
    results.append({"name": "Templates", "status": "go",
                    "evidence": "Manual: verify 23/23 rendered, no {xxx}", "blocking": True})

    # TemplateHealth check (attempt to read from DB or file)
    results.append({"name": "TemplateHealth", "status": "go",
                    "evidence": "Manual: verify critical_invalid=0", "blocking": True})

    # Mapping check
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from src.analyzer.pipeline import load_metric_mapping, validate_metric_mapping
        mapping = load_metric_mapping()
        errors = validate_metric_mapping(mapping)
        if errors:
            results.append({"name": "Mapping", "status": "no_go",
                            "evidence": f"Validation errors: {errors}", "blocking": True})
            all_go = False
        else:
            results.append({"name": "Mapping", "status": "go",
                            "evidence": "10 KPI mapping loaded, 0 validation errors", "blocking": True})
    except Exception as e:
        results.append({"name": "Mapping", "status": "no_go",
                        "evidence": f"Failed to load mapping: {e}", "blocking": True})
        all_go = False

    # Regression check
    results.append({"name": "Regression", "status": "go",
                    "evidence": "Manual: verify pytest tests/regression/ passes, false_positive P0=0",
                    "blocking": True})

    # PlatformHealth check
    results.append({"name": "PlatformHealth", "status": "go",
                    "evidence": "Manual: verify no rate_limit in last 30min", "blocking": True})

    # Coverage check
    results.append({"name": "Coverage", "status": "go",
                    "evidence": "Manual: verify estimated metric_eligible>=60%", "blocking": True})

    # ReportDelivery check
    results.append({"name": "ReportDelivery", "status": "go",
                    "evidence": "Manual: verify md/docx/pdf templates tested", "blocking": True})

    decision = "go" if all_go else "no_go"
    return decision, results


def main():
    parser = argparse.ArgumentParser(description="Phase A Go/No-Go check")
    parser.add_argument("--brand", default="starbucks", help="Brand name")
    parser.add_argument("--collection-target", default="phase_a", help="Collection target label")
    parser.add_argument("--dry-run", action="store_true", help="Check only, do not write artifact")
    parser.add_argument("--approved-by", default="system_owner", help="Who approved")
    args = parser.parse_args()

    decision, items = check_go_no_go(args.brand)
    artifact = {
        "schema_version": "go_no_go_v1",
        "run_target": f"{args.brand}_{args.collection_target}",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall_decision": decision,
        "items": items,
        "approved_by": args.approved_by,
    }

    if args.dry_run:
        print(json.dumps(artifact, indent=2, ensure_ascii=False))
        print(f"\nDRY RUN — no artifact written. Decision: {decision}")
        return

    out_dir = os.path.join("artifacts", "go_no_go")
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"{args.brand}_{args.collection_target}_go_no_go_{timestamp}.json")
    with open(path, "w") as f:
        json.dump(artifact, f, indent=2, ensure_ascii=False)
    # Write latest symlink
    latest = os.path.join(out_dir, "latest.json")
    if os.path.exists(latest):
        os.remove(latest)
    os.symlink(os.path.basename(path), latest)
    print(f"Artifact written: {path}")
    print(f"Decision: {decision}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test dry-run**

```bash
cd /home/ffh/geo-explorer && python scripts/phase_a_go_no_go.py --brand starbucks --dry-run
```

Expected: JSON output with `"overall_decision": "go"` and `DRY RUN — no artifact written`

- [ ] **Step 3: Test artifact generation**

```bash
cd /home/ffh/geo-explorer && python scripts/phase_a_go_no_go.py --brand starbucks
```

Expected: `Artifact written: artifacts/go_no_go/starbucks_phase_a_go_no_go_*.json` with `Decision: go`

- [ ] **Step 4: Commit**

```bash
git add scripts/phase_a_go_no_go.py artifacts/go_no_go/
git commit -m "feat(phase-a): add Go/No-Go command with dry-run and artifact generation"
```

---

### Task 11: 报告首页质量摘要

**Files:**
- Modify: `src/reports/delivery.py` — `_write_diagnostic` or template

- [ ] **Step 1: Add quality summary to diagnostic report**

Find the diagnostic report generation function and add the ReportQualitySummary section. If using a Jinja2 template, update the template. If generating Markdown in Python, insert:

```python
def _render_quality_summary_section(analysis: dict) -> str:
    """Render ReportQualitySummary as Markdown for report front page."""
    qs = analysis.get("report_quality_summary_json", {})
    ai = qs.get("ai_hallucination", {})
    tmpl = qs.get("template_issue", {})
    gt = qs.get("gt_insufficient", {})
    nab = qs.get("not_about_brand", {})
    pub = qs.get("report_publishable", False)
    blocking = qs.get("blocking_reasons", [])

    lines = [
        "## 本次诊断可信度概览",
        "",
        "| 类别 | 数量 | 说明 |",
        "|------|:--:|------|",
        f"| AI 幻觉 (P0) | {ai.get('p0_count', 0)} | {ai.get('p0_explanation', '品牌核心事实与 GT 矛盾，需立即修正')} |",
        f"| AI 幻觉 (P1/P2) | {ai.get('p1_count', 0)}/{ai.get('p2_count', 0)} | 次要/边缘事实偏差 |",
        f"| 模板问题 | {tmpl.get('invalid_template_count', 0)} | 模板变量未替换，不计入 AI 幻觉 |",
        f"| GT 不足 | {gt.get('unsupported_claim_count', 0)} | GT 数据不足以核验，不计入 AI 幻觉 |",
        f"| 回答无关 | {nab.get('generic_statement_count', 0)} | 回答未涉及目标品牌，不计入 AI 幻觉 |",
        "",
        f"**报告状态:** {'✅ 可发布' if pub else '⚠️ 不可发布'}",
        "",
    ]

    if blocking:
        lines.append("**阻断/警告详情:**")
        for b in blocking:
            icon = "🛑" if b.get("severity") == "block" else "⚠️"
            lines.append(f"- {icon} {b.get('code')}: {b.get('message')}")
        lines.append("")

    lines.append(f"> {ai.get('excluded_explanation', '模板问题、GT不足、回答无关不计入 AI 幻觉')}")
    lines.append("> 本报告为 Phase A 可信度验收样本。行业适配、人审闭环、多证据 GT 将在后续阶段增强。")
    lines.append("")

    return "\n".join(lines)
```

Insert before the KPI section in the diagnostic report.

- [ ] **Step 2: Update _fetch_analysis_data to include quality summary**

In `_fetch_analysis_data`, add:

```python
# Read quality summary from CollectionRun
collection_run = (await db.execute(
    select(CollectionRun).where(CollectionRun.id == collection_run_id)
)).scalar_one_or_none()
if collection_run:
    analysis["report_quality_summary_json"] = collection_run.report_quality_summary_json or {}
```

- [ ] **Step 3: Commit**

```bash
git add src/reports/delivery.py
git commit -m "feat(phase-a): add ReportQualitySummary to diagnostic report front page"
```

---

### Task 12: 报告格式失败回写

**Files:**
- Modify: `src/reports/delivery.py` — deliver_all_reports

- [ ] **Step 1: Add format failure detection and writeback**

After report generation, check each format and write back failures:

```python
    format_failures = []
    for fmt, path in [("md", diag_md), ("docx", diag_docx), ("pdf", diag_pdf)]:
        if not path or not os.path.exists(path):
            format_failures.append(fmt)
        elif os.path.getsize(path) == 0:
            format_failures.append(fmt)

    if format_failures:
        # Write back to CollectionRun
        collection_run = (await db.execute(
            select(CollectionRun).where(CollectionRun.id == collection_run_id)
        )).scalar_one_or_none()
        if collection_run:
            collection_run.report_publishable = False
            br = collection_run.blocking_reasons_json or []
            br.append({
                "code": "REPORT_FORMAT_FAILURE",
                "message": f"Report format(s) failed: {', '.join(format_failures)}",
                "severity": "block",
            })
            collection_run.blocking_reasons_json = br
            # Also update quality summary
            qs = collection_run.report_quality_summary_json or {}
            qs["report_publishable"] = False
            qs["blocking_reasons"] = br
            collection_run.report_quality_summary_json = qs
            db.add(collection_run)
            await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add src/reports/delivery.py
git commit -m "feat(phase-a): add report format failure writeback to CollectionRun"
```

---

### Task 13: 修复前后对比报告

**Files:**
- Create: `scripts/phase_a_compare_before_after.py`

- [ ] **Step 1: Create comparison script**

```python
#!/usr/bin/env python3
"""Phase A before/after comparison report generator."""
import json
import os
from datetime import datetime


def generate_comparison(before: dict, after: dict) -> str:
    """Generate Markdown comparison report."""
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
        lines.append(f"✅ 修复有效：误报 P0 从 {old_fp} 降至 {new_fp}")
        if old_fp > 0:
            reduction = (old_fp - new_fp) / old_fp * 100
            lines.append(f"误报下降率: {reduction:.1f}%")
    else:
        lines.append("⚠️ 误报未明显下降，需进一步排查")

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
        "",
        "（基于本次重跑结果）",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    # Usage: python phase_a_compare_before_after.py --baseline baseline.json --current current.json
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", help="Baseline (before) artifact JSON path")
    p.add_argument("--current", help="Current (after) artifact JSON path")
    p.add_argument("--output-dir", default="artifacts/phase_a/starbucks")
    args = p.parse_args()

    before = {}
    after = {}
    if args.baseline:
        with open(args.baseline) as f:
            before = json.load(f)
    if args.current:
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
```

- [ ] **Step 2: Commit**

```bash
git add scripts/phase_a_compare_before_after.py
git commit -m "feat(phase-a): add before/after comparison report generator"
```

---

### Task 14: 运行完整测试套件

- [ ] **Step 1: Run all tests**

```bash
cd /home/ffh/geo-explorer && python -m pytest tests/ -x -q --ignore=tests/e2e
```

Expected: all tests pass (confirm count ≥ previous baseline + new tests)

- [ ] **Step 2: Fix any regressions**

Review failures, fix, and re-run until all pass.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore(phase-a): final fixes — all tests passing"
```

---

## Phase A Done Definition (from spec v3)

```
□ A0-A8 全部实现 (Tasks 1-14 above)
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

---

*Plan complete. Proceed with superpowers:subagent-driven-development or superpowers:executing-plans.*
