# Phase 11: 可信度加固 实现计划 v2

> **审阅:** GEO 产品架构负责人 / 可信 AI 系统交付评审专家 / 工程实施计划审查人  
> **结论:** 方向通过。按本文 7 阶段执行，补齐数据模型、迁移、审核流、KPI 持久化、语义判定、ActionTheme 生命周期、Content 治理、API/E2E 验收。

**Goal:** 将 GEO Explorer 从"功能完整的内部 MVP"升级为"可信交付的生产级系统"。

**Architecture:** 7 阶段递进。数据模型先行 → GT 可信底座 → KPI 可解释 → 幻觉语义级 → Action 聚合 → Content 治理 → E2E 验收。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / PostgreSQL 16

---

## 阶段 1: 数据模型与迁移（1 天）

### 1.1 扩展 GroundTruthEvidence

**Files:**
- Modify: `src/models/gt_evidence.py`
- Generate: Migration via autogenerate

**新增字段:**

```python
# src/models/gt_evidence.py — 在现有字段后追加
source_tier: Mapped[str] = mapped_column(String(10), default="C")  # S/A/B/C/D
human_confirmed: Mapped[bool] = mapped_column(default=False)
review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/reviewed/flagged
```

**Migration:**

```bash
alembic revision --autogenerate -m "add source_tier and review fields to gt_evidences"
alembic upgrade head
```

**验证:** `pytest tests/test_models.py -v` — 4 tests pass.

### 1.2 新增 ActionTheme 模型

**Files:**
- Create: `src/models/action_theme.py`
- Modify: `src/models/__init__.py`

```python
# src/models/action_theme.py
class ActionTheme(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "action_themes"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="P1")  # P0/P1/P2
    issue_type: Mapped[str] = mapped_column(String(100), default="")
    affected_fields: Mapped[list] = mapped_column(JSONB, default=list)
    affected_platforms: Mapped[list] = mapped_column(JSONB, default=list)
    hallucination_result_ids: Mapped[list] = mapped_column(JSONB, default=list)
    action_plan_ids: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    typical_ai_claims: Mapped[list] = mapped_column(JSONB, default=list)
    recommended_content_types: Mapped[list] = mapped_column(JSONB, default=list)
    expected_kpi_impact: Mapped[dict] = mapped_column(JSONB, default=dict)
    effort_level: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="detected")

THEME_TRANSITIONS = {
    "detected": ["confirmed", "dismissed"],
    "confirmed": ["content_generating", "dismissed"],
    "content_generating": ["content_ready"],
    "content_ready": ["approved", "dismissed"],
    "approved": ["published_marked"],
    "published_marked": ["verification_pending"],
    "verification_pending": ["verified"],
    "verified": [],
    "dismissed": [],
}
```

**Migration:**

```bash
alembic revision --autogenerate -m "add action_themes table"
alembic upgrade head
```

### 1.3 扩展 ContentPackage 治理字段

**Files:**
- Modify: `src/models/content_package.py`
- Generate: Migration

**新增字段:**

```python
risk_level: Mapped[str] = mapped_column(String(10), default="low")  # low/medium/high
fact_source_map: Mapped[dict] = mapped_column(JSONB, default=dict)  # sentence → {gt_field, source_url, tier, confirmed}
publish_url: Mapped[str] = mapped_column(Text, default="")  # 发布后回填
verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

**状态机替换:**

```python
CONTENT_PACKAGE_TRANSITIONS = {
    "draft": ["fact_checked", "cancelled"],
    "fact_checked": ["needs_review", "approved"],
    "needs_review": ["approved", "draft"],
    "approved": ["exported"],
    "exported": ["published"],
    "published": ["verification_pending"],
    "verification_pending": ["verified"],
    "verified": [],
    "cancelled": [],
}
```

### 1.4 conftest.py TRUNCATE_ALL 更新

追加 `action_themes` 到 TRUNCATE 列表。

**验证:** `pytest tests/test_models.py -v` — all pass.

---

## 阶段 2: GT 可信度体系（1 天）

### 2.1 来源等级体系 (S/A/B/C/D)

**Files:**
- Modify: `src/schemas/ground_truth.py`

```python
SOURCE_TIERS = {
    "S": {"label": "官方/权威来源", "score": 1.0,
          "examples": ["官网", "官方文档", "政府/工商/交易所"]},
    "A": {"label": "权威第三方", "score": 0.7,
          "examples": ["权威媒体", "行业数据库", "专业评测"]},
    "B": {"label": "线索来源", "score": 0.4,
          "examples": ["搜索摘要", "百科", "聚合页"]},
    "C": {"label": "AI 候选", "score": 0.2,
          "examples": ["AI 平台回答"]},
    "D": {"label": "不可信", "score": 0.0,
          "examples": ["论坛", "自媒体", "未知站点"],
          "usage": "不进入正式 GT"},
}

# 高风险字段所需最小来源等级
HIGH_RISK_FIELD_TIER_REQUIREMENTS = {
    "official_name": "S",
    "positioning": "S",
    "pricing": "S",
    "certifications": "S",
    "funding": "S",
    "customer_cases": "A",  # A+ 可接受但需用户确认
    "proof_points": "A",
}
```

### 2.2 GT 采集时持久化证据（含 source_tier）

**Files:**
- Modify: `src/collector/gt_collector.py`

采集完成后，遍历 field_results，为每个 source 创建 `GroundTruthEvidence` 记录，写入 `source_tier` 字段。

AI 来源 → tier="C"，搜索来源 → 根据 URL 推断 tier（.gov.cn→"S", tianyancha→"A", 百科→"B", 其他→"C"）。

### 2.3 分层置信度计算（不混用 tier→quality 映射）

**Files:**
- Modify: `src/analyzer/gt_confidence.py`

```python
def compute_field_confidence(sources: list[dict], field_name: str = "") -> str:
    """Tier-weighted confidence. S-tier sources carry more weight than A-tier."""
    if not sources: return "low"
    
    tiers = [s.get("source_tier", "C") for s in sources]
    scores = [SOURCE_TIERS.get(t, {}).get("score", 0.2) for t in tiers]
    avg_score = sum(scores) / len(scores)
    
    has_s = any(t == "S" for t in tiers)
    has_a_or_s = any(t in ("S", "A") for t in tiers)
    
    # Conflict detection is field-type-aware
    from src.analyzer.gt_conflict_detector import detect_field_conflict
    conflict = detect_field_conflict(field_name, sources)
    
    if has_s and not conflict["has_conflict"] and avg_score >= 0.8:
        return "high"
    if has_a_or_s and not conflict["has_conflict"] and avg_score >= 0.5:
        return "medium"
    if avg_score >= 0.3 and not conflict["has_conflict"]:
        return "low"
    if conflict["has_conflict"]:
        return "uncertain"
    return "low"
```

### 2.4 字段类型感知冲突检测

**Files:**
- Modify: `src/analyzer/gt_conflict_detector.py`

```python
def normalize_field_value(field_name: str, value) -> str:
    """Normalize value based on field type for comparison."""
    if field_name in ("official_domains",):
        return str(value).lower().replace("https://", "").replace("http://", "").rstrip("/")
    if field_name in ("official_name",):
        return str(value).strip().lower()
    return str(value)[:200].strip()

def detect_field_conflict(field_name: str, sources: list[dict]) -> dict:
    """Field-type-aware conflict detection."""
    normalized = [normalize_field_value(field_name, s.get("value", "")) for s in sources if s.get("value")]
    unique = set(normalized)
    return {
        "has_conflict": len(unique) > 1,
        "conflict_type": "value_mismatch" if len(unique) > 1 else "none",
        "normalized_values": list(unique)[:5],
        "explanation": f"{len(unique)} distinct values found" if len(unique) > 1 else "All sources agree",
    }
```

### 2.5 Promote 阻断规则（证据 + 人工确认）

**Files:**
- Modify: `src/api/ground_truth.py`

```python
# Promote 校验顺序:
# 1. required_fields_complete
# 2. 高风险字段需 S/A 级证据
# 3. 高风险字段需人工逐字段确认
# 4. uncertain 字段不进入 active GT（除非用户显式 override）
```

**验证:** 新增 4 个测试：

```python
# tests/test_gt_review.py 追加
def test_high_risk_field_requires_s_or_a_tier_evidence():
def test_ai_only_evidence_cannot_promote_high_risk_field():
def test_promote_requires_human_review_for_high_risk_fields():
def test_uncertain_field_excluded_from_active_gt_without_override():
```

---

## 阶段 3: KPI 可解释体系（0.5 天）

### 3.1 统一 5 个基础 KPI 返回格式

**Files:**
- Modify: `src/analyzer/sov.py`, `first_rec.py`, `accuracy.py`, `completeness.py`, `citation.py`

每个 KPI 返回增加: `numerator`, `denominator`, `confidence`

### 3.2 多因子 KPI 置信度

**Files:**
- Create function in `src/analyzer/pipeline.py`

```python
def compute_metric_confidence(
    sample_size: int, platform_count: int, failure_rate: float,
    gt_confidence: str, collection_status: str,
) -> str:
    if sample_size >= 10 and platform_count >= 3 and failure_rate < 0.1:
        return "high"
    if sample_size >= 5 and platform_count >= 2 and failure_rate < 0.3:
        return "medium"
    if sample_size >= 1:
        return "low"
    return "uncertain"
```

### 3.3 KPI Card 持久化到 MetricsSnapshot.details

**Files:**
- Modify: `src/analyzer/pipeline.py`

在 `compute_and_save_metrics()` 中，生成 KPI cards 并存入 `details.kpi_cards`:

```json
{
  "kpi_cards": [{
    "key": "sov", "name_cn": "声量份额",
    "value": 0.652, "numerator": 43, "denominator": 66,
    "sample_size": 69, "confidence": "high",
    "platform_breakdown": {"deepseek": "20/22", "kimi": "14/22", "doubao": "9/22"},
    "evidence_summary": "品牌在定义类问题中表现较好，但在非品牌场景类问题中提及较少"
  }, ...]
}
```

### 3.4 Dashboard API 暴露 KPI Cards

**Files:**
- Modify: `src/api/dashboard.py`

新增 `GET /api/dashboard/kpi-cards?brand_id={id}` 返回最新采集的 KPI 解释卡。

**验证:** `pytest tests/test_kpi_extended.py -v` — 6 tests pass.

---

## 阶段 4: 语义级幻觉检测（1 天）

### 4.1 增强 Claim 和 Verification 数据结构

**Files:**
- Modify: `src/analyzer/hallucination.py`

```python
@dataclass
class ClaimVerification:
    verdict: str  # correct / incorrect / partial / unsupported / uncertain
    error_type: str | None
    severity: str
    gt_value: str
    similarity_score: float | None
    explanation: str
    needs_human_review: bool
```

### 4.2 错误类型分类

```python
HALLUCINATION_ERROR_TYPES = {
    "identity_error": "品牌身份错误",
    "category_error": "行业/品类错误", 
    "positioning_error": "定位描述错误",
    "feature_error": "功能/产品描述错误",
    "competitor_confusion": "竞品混淆",
    "unsupported_claim": "无来源支撑的声明",
    "outdated_claim": "过时信息",
    "overclaim": "夸大声明",
    "negative_hallucination": "遗漏关键信息",
}
```

### 4.3 人工复核规则

```python
# P0 字段 incorrect → needs_human_review = True
# unsupported_claim 涉及客户/融资/奖项/认证 → needs_human_review = True
# uncertain → 不生成 P0 Action
```

**验证:** `pytest tests/test_analyzer.py -v` — all pass.

---

## 阶段 5: Action Theme 聚合（1 天）

### 5.1 多维度聚类

**Files:**
- Modify: `src/analyzer/pipeline.py` (`_run_hallucination_detection` 追加聚合逻辑)

聚合维度: `field_name + error_type + severity + platform_count`

### 5.2 生成 ActionTheme 记录

每个 cluster 生成一条 ActionTheme，包含:
- title（自动生成，如"品类定位纠偏"）
- 关联的 `action_plan_ids` 和 `hallucination_result_ids`
- `typical_ai_claims`（最多 3 条示例）
- `expected_kpi_impact`（如 `{"accuracy_rate": "+15%"}`）

目标: 每次诊断输出 5-10 个 ActionTheme。

### 5.3 Content Package 改为基于 Theme 生成

**Files:**
- Modify: `src/analyzer/pipeline.py` (`_generate_content_packages`)

读取 ActionTheme → 为每个 theme 生成一个 ContentPackage。

**验证:** 运行星巴克全流程，确认输出 5-10 个 Theme + 对应 ContentPackage。

---

## 阶段 6: Content Package 治理（1 天）

### 6.1 风险分级

**Files:**
- Modify: `src/actions/executor.py`

根据涉及字段的 `FIELD_RISK_LEVELS` 自动标记:
- 包含 `high` 风险字段 → `risk_level = "high"` → status → `needs_review`
- 包含 `medium` 字段 → `risk_level = "medium"` → status → `needs_review`
- 仅 `low` 字段 → `risk_level = "low"` → status → `fact_checked`

### 6.2 状态流转权限

| 状态变更 | 条件 |
|----------|------|
| draft → fact_checked | 事实检查完成 + 低风险 |
| draft → needs_review | 中/高风险 |
| needs_review → approved | 人工审核通过 |
| approved → exported | 用户导出 |
| exported → published | 用户填写 publish_url |
| published → verification_pending | 到达复测时间 |

### 6.3 事实来源映射

生成内容时记录: `{sentence_index: {gt_field, source_url, tier, human_confirmed}}`

**验证:** `pytest tests/test_action_executor.py -v` — all pass.

---

## 阶段 7: E2E 回归与验收（0.5 天）

### 7.1 E2E 验收流程

```text
输入品牌 → GT采集 → 证据持久化(带tier) → 用户审核 → Promote(阻断规则生效)
→ Brand采集 → KPI Cards → 幻觉检测(带error_type) → Action Theme → 
Content Package(带风险分级) → 报告导出
```

### 7.2 验收标准

- [ ] 高风险 GT 字段无 S/A 证据时 Promote 返回 400
- [ ] KPI Card 包含 numerator/denominator/confidence/platform_breakdown
- [ ] P0 错误声明标记 needs_human_review=True
- [ ] Action Theme 数量 5-10 个
- [ ] 高风险 Content Package 进入 needs_review
- [ ] 所有现有 89 tests 继续通过

### 7.3 回归测试

```bash
pytest tests/ -v  # 89+ tests, 0 failures
```

---

## Summary

| 阶段 | 核心产出 | 新增测试 | 预估 |
|------|----------|----------|------|
| 1 | 数据模型 + 3 migrations | 模型测试 | 1d |
| 2 | GT 来源等级 + 证据追溯 + Promote 阻断 | 4 个 GT 审查测试 | 1d |
| 3 | KPI 统一格式 + Cards + 多因子置信度 | KPI 测试更新 | 0.5d |
| 4 | 语义幻觉 + error_type + 人工复核 | 5 个幻觉测试 | 1d |
| 5 | ActionTheme 模型 + 多维度聚合 | 4 个 Theme 测试 | 1d |
| 6 | Content 风险分级 + 状态机 + 事实映射 | 5 个治理测试 | 1d |
| 7 | E2E 验收 + 全量回归 | 1 个 E2E | 0.5d |

**总计: 约 5-6 天 | 新增 20+ 测试 | 89 现有测试保持通过**
