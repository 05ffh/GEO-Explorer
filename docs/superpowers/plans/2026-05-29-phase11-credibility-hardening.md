# Phase 11: 可信度加固 实现计划

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 GEO Explorer 从"功能完整的内部 MVP"升级为"可信交付的生产级系统"。对标本专家评审清单 P0-1/P0-2/P0-3/P0-4/P0-5。

**Architecture:** 5 Tasks，3 阶段。可信事实基础→KPI可解释→幻觉+Action聚合。所有改动在现有模块上增量进行。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / PostgreSQL 16

---

## Task 1: GT 来源等级体系 (S/A/B/C/D)

**Files:**
- Modify: `src/schemas/ground_truth.py` (source tier enum + field evidence reqs)
- Modify: `src/analyzer/gt_confidence.py` (tier-weighted scoring)
- Modify: `src/collector/gt_collector.py` (persist evidence to gt_evidences table)
- Modify: `src/api/ground_truth.py` (enhance promote with evidence checks)

**Step 1: 定义来源等级 + 字段证据要求**

```python
# src/schemas/ground_truth.py 追加

# Source tier enum
SOURCE_TIERS = {
    "S": {"label": "官方/权威来源", "score": 1.0,
          "examples": "官网、官方文档、政府/工商/交易所"},
    "A": {"label": "权威第三方", "score": 0.8,
          "examples": "权威媒体、行业数据库、专业评测"},
    "B": {"label": "线索来源", "score": 0.5,
          "examples": "搜索摘要、百科、聚合页"},
    "C": {"label": "AI 候选", "score": 0.3,
          "examples": "AI 平台回答"},
    "D": {"label": "不可信", "score": 0.0,
          "examples": "论坛、自媒体、未知站点"},
}

# Tier → legacy quality mapping
TIER_TO_QUALITY = {"S": "high", "A": "high", "B": "medium", "C": "low", "D": "very_low"}

# Field-level minimum evidence requirements
FIELD_EVIDENCE_REQUIREMENTS = {
    "official_name": {"min_tier": "S", "min_sources": 1},
    "category": {"min_tier": "A", "min_sources": 1},
    "positioning": {"min_tier": "S", "min_sources": 1},
    "core_products": {"min_tier": "A", "min_sources": 1},
    "target_users": {"min_tier": "A", "min_sources": 1},
    "core_scenarios": {"min_tier": "B", "min_sources": 1},
    "key_differentiators": {"min_tier": "B", "min_sources": 1},
    "target_competitors": {"min_tier": "B", "min_sources": 2},
    "official_domains": {"min_tier": "S", "min_sources": 1},
    "pricing": {"min_tier": "S", "min_sources": 1},
    "certifications": {"min_tier": "S", "min_sources": 1},
    "awards": {"min_tier": "S", "min_sources": 1},
    "customer_cases": {"min_tier": "A", "min_sources": 1},
    "funding": {"min_tier": "S", "min_sources": 1},
    "proof_points": {"min_tier": "A", "min_sources": 1},
    "forbidden_claims": {"min_tier": "B", "min_sources": 1},
}

# Risk level for content governance
FIELD_RISK_LEVELS = {
    "low": ["aliases", "subcategory", "scenario_keywords", "alternative_solutions",
            "common_misconceptions", "official_docs", "official_channels"],
    "medium": ["industry", "core_products", "core_features", "target_users",
               "core_scenarios", "best_fit_users", "preferred_recommendation_reasons"],
    "high": ["official_name", "category", "positioning", "target_competitors",
             "key_differentiators", "forbidden_claims", "source_of_truth_by_field",
             "proof_points", "pricing", "certifications", "customers", "awards", "funding"],
}
```

**Step 2: 升级置信度计算为分层加权**

```python
# src/analyzer/gt_confidence.py 重写

def compute_field_confidence(sources: list[dict]) -> str:
    """Tier-weighted confidence scoring using S/A/B/C/D source tiers."""
    if not sources:
        return "low"

    tiers = [s.get("source_tier", "C") for s in sources]
    scores = [SOURCE_TIERS.get(t, {}).get("score", 0.3) for t in tiers]
    avg_score = sum(scores) / len(scores)

    has_s = any(t == "S" for t in tiers)
    has_a = any(t in ("S", "A") for t in tiers)
    unique_values = set(str(s.get("value", ""))[:100] for s in sources if s.get("value"))
    has_conflict = len(unique_values) > 1

    if has_s and not has_conflict and avg_score >= 0.8:
        return "high"
    if has_a and not has_conflict and avg_score >= 0.5:
        return "medium"
    if avg_score >= 0.3 and not has_conflict:
        return "low"
    if has_conflict:
        return "uncertain"
    return "low"
```

**Step 3: GT 采集时持久化证据到 gt_evidences 表**

```python
# src/collector/gt_collector.py collect_gt_candidate() 中追加

# After candidate creation, persist evidence
for field_name, result in field_results.items():
    for src in result.get("sources", []):
        evidence = GroundTruthEvidence(
            candidate_id=candidate.id,
            field_name=field_name,
            value=src.get("value", "")[:500],
            source_type=src.get("source_type", "unknown"),
            source_name=src.get("platform", ""),
            source_url=src.get("url", ""),
            excerpt=src.get("excerpt", ""),
            source_quality=TIER_TO_QUALITY.get(src.get("source_tier", "C"), "low"),
            confidence=compute_field_confidence([src]),
        )
        db.add(evidence)
```

**Step 4: Promote 时增加证据等级校验**

```python
# src/api/ground_truth.py promote_candidate_to_active() 中追加

# Check evidence sufficiency for high-risk fields
for field in settings.gt_high_risk_fields:
    if field not in candidate.candidate_json:
        continue
    min_tier = FIELD_EVIDENCE_REQUIREMENTS.get(field, {}).get("min_tier", "B")
    min_sources = FIELD_EVIDENCE_REQUIREMENTS.get(field, {}).get("min_sources", 1)
    evidence_count = 0
    has_sufficient = False
    for ev in evidence_rows:
        if ev.field_name == field:
            evidence_count += 1
            ev_tier_score = SOURCE_TIERS.get(ev.source_tier, {}).get("score", 0)
            min_tier_score = SOURCE_TIERS.get(min_tier, {}).get("score", 0)
            if ev_tier_score >= min_tier_score:
                has_sufficient = True
    if evidence_count < min_sources:
        raise HTTPException(400, f"Field '{field}' needs {min_sources}+ sources, has {evidence_count}")
```

**验证:** Run `pytest tests/ -k "gt" -v` — all GT-related tests pass. Manually verify that GT collection now creates gt_evidences rows.

---

## Task 2: KPI 指标解释卡 — 统一 metadata

**Files:**
- Modify: `src/analyzer/sov.py`, `first_rec.py`, `accuracy.py`, `completeness.py`, `citation.py`
- Create: `src/schemas/kpi_card.py` (KPI card schema)
- Modify: `src/api/dashboard.py` (expose KPI cards)

**Step 1: 定义 KPI 解释卡 schema**

```python
# src/schemas/kpi_card.py (新建)
from dataclasses import dataclass, field

@dataclass
class KPICard:
    key: str
    name_cn: str
    definition: str
    business_meaning: str
    value: float
    numerator: int
    denominator: int
    sample_size: int
    failure_count: int
    confidence: str
    platform_breakdown: dict = field(default_factory=dict)
    exclusion_rules: list = field(default_factory=list)
    evidence_summary: str = ""
```

**Step 2: 对齐 5 个基础 KPI 的返回格式**

给所有 KPI 函数添加 `numerator`/`denominator`/`confidence` 字段：

- `sov.py`: `numerator=mentioned, denominator=total_valid, confidence=high/medium/low based on sample_size`
- `first_rec.py`: `numerator=first_count, denominator=total_rec_answers, confidence`
- `accuracy.py`: `numerator=correct_fields, denominator=mentioned_fields, confidence`
- `completeness.py`: `numerator=complete_fields, denominator=required_fields, confidence`
- `citation.py`: `numerator=cited_contexts, denominator=mentioned_contexts, confidence`

**验证:** `pytest tests/test_kpi_extended.py -v` — 所有 KPI 测试通过。

---

## Task 3: 幻觉检测升级 — 语义级 + 错误类型分类

**Files:**
- Modify: `src/analyzer/hallucination.py` (错误类型分类 + 语义判定)
- Modify: `src/analyzer/evaluator.py` (增加语义相似度)

**Step 1: 定义错误类型**

```python
HALLUCINATION_ERROR_TYPES = {
    "identity_error": "品牌身份错误",
    "category_error": "行业/品类错误",
    "positioning_error": "定位描述错误",
    "feature_error": "功能/产品描述错误",
    "competitor_confusion": "竞品混淆",
    "unsupported_claim": "无来源支撑的声明",
    "outdated_claim": "过时信息",
    "overclaim": "夸大声明（领先/第一/最大）",
    "negative_hallucination": "负面幻觉（遗漏关键信息）",
}
```

**Step 2: 增强 verify_claim 返回错误类型**

在 `verify_claim()` 返回中新增 `error_type` 字段，根据 claim 内容和 GT 差异自动分类。

**验证:** `pytest tests/test_analyzer.py -v` — hallucination tests pass with error types。

---

## Task 4: Action Plan 聚合为 Action Theme

**Files:**
- Modify: `src/analyzer/pipeline.py` (`_run_hallucination_detection` 聚合逻辑)
- Create: `src/models/action_theme.py` (聚合主题模型)

**Step 1: 聚合逻辑**

1364 条 Action Plans → 按字段分组 → 合并同字段同类错误 → 生成 Action Theme（5-10 个主题），每个 Theme 包含：
- 主题名称、优先级、涉及平台、涉及问题数、典型 AI 原句、对应 GT 字段、预期影响 KPI

**Step 2: Content Package 生成改为按 Theme 输出**

4 个硬编码主题 → 改为从 Action Theme 动态生成。

**验证:** Run full pipeline on 星巴克, verify output is 5-10 themes instead of 1364 individual plans.

---

## Task 5: Content Package 治理 — 风险分级 + 审核状态机

**Files:**
- Modify: `src/models/content_package.py` (状态机)
- Modify: `src/actions/fact_checker.py` (风险分级)
- Modify: `src/actions/executor.py` (事实来源映射)

**Step 1: Content Package 状态机**

```python
CONTENT_PACKAGE_TRANSITIONS = {
    "draft": ["fact_checked", "needs_review", "cancelled"],
    "fact_checked": ["needs_review", "approved"],
    "needs_review": ["approved", "draft"],
    "approved": ["exported", "cancelled"],
    "exported": ["published", "cancelled"],
    "published": ["verification_pending"],
    "verification_pending": ["verified"],
    "verified": [],
    "cancelled": [],
}
```

**Step 2: 事实来源映射**

内容中每个事实性句子追踪来源：`gt_field → source_url → evidence_tier → human_confirmed`

**Step 3: 内容风险分级**

根据涉及字段的 FIELD_RISK_LEVELS 自动标记风险等级（低/中/高）。

**验证:** `pytest tests/test_action_executor.py -v` — content package tests pass.

---

## Summary

| Task | 内容 | 测试 | 预估工作量 |
|------|------|------|-----------|
| 1 | GT 来源等级 S/A/B/C/D | 现有 GT tests | 2h |
| 2 | KPI 解释卡 — metadata 对齐 | test_kpi_extended | 1h |
| 3 | 幻觉检测语义升级 | test_analyzer | 1.5h |
| 4 | Action 聚合为 Theme | test_pipeline | 1h |
| 5 | Content Package 治理 | test_action_executor | 1.5h |

**执行顺序: 1 → 2 → 3 → 4 → 5（线性依赖，GT 先行）**
