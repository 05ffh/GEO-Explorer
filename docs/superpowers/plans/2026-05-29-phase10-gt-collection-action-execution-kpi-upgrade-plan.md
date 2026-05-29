# Phase 10: GT 自动采集 + Action 内容执行准备 + KPI 升级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补齐 GT 自动采集（含候选/证据/审核三层模型）、新增 5 个 KPI、Action 内容执行准备器，将 GEO Explorer 从监测工具升级为品牌 AI 认知资产运营系统。

**Architecture:** 14 Tasks，7 阶段递进。Stage 1 数据模型先行（Migration），Stage 2 搜索层独立并行，Stage 3-4 GT 采集+审核串行，Stage 5 KPI 升级可并行于 Stage 3-4，Stage 6 Action 执行器，Stage 7 Dashboard+E2E 收尾。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / Celery + Redis / PostgreSQL 16 / Jinja2 + HTMX / duckduckgo-search

---

## File Map

```
新增 (19):
  src/models/gt_candidate.py, gt_evidence.py, gt_review.py
  src/models/content_package.py
  src/search/__init__.py, duckduckgo_backend.py, ai_search_backend.py
  src/collector/gt_collector.py
  src/analyzer/gt_aggregator.py, gt_confidence.py, gt_conflict_detector.py
  src/analyzer/scenario_recall.py, semantic_stability.py, differentiation.py
  src/analyzer/cross_platform_consistency.py, recommendation_quality.py
  src/actions/executor.py, content_package.py, fact_checker.py, schema_generator.py

修改 (15):
  src/models/__init__.py, ground_truth.py, metrics_snapshot.py
  src/config.py
  src/analyzer/pipeline.py, evaluator.py
  src/api/ground_truth.py, actions.py, dashboard.py, brands.py
  src/templates/dashboard/index.html
  src/templates/ground_truth/review.html (new template)
  src/templates/actions/confirm.html (new template)
  tests/conftest.py

测试 (5):
  tests/test_gt_collector.py, test_gt_aggregator.py
  tests/test_kpi_extended.py, test_action_executor.py
  tests/test_phase10_e2e.py
```

---

### Task 1: Migration — GT 三层模型 + Content Package + GT 字段扩展

**Files:**
- Create: `src/models/gt_candidate.py`, `src/models/gt_evidence.py`, `src/models/gt_review.py`
- Create: `src/models/content_package.py`
- Modify: `src/models/__init__.py`
- Modify: `src/models/ground_truth.py` (扩展 GT 字段)
- Modify: `tests/conftest.py` (TRUNCATE_ALL)
- Generate: Migration via autogenerate

- [ ] **Step 1: 创建 GT 三层模型**

```python
# src/models/gt_candidate.py
import uuid
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class GroundTruthCandidate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "gt_candidates"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    candidate_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    overall_confidence: Mapped[str] = mapped_column(String(20), default="low")
    status: Mapped[str] = mapped_column(String(50), default="pending_review")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

```python
# src/models/gt_evidence.py
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Float, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin

class GroundTruthEvidence(Base, UUIDMixin):
    __tablename__ = "gt_evidences"
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gt_candidates.id"), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(Text, default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    source_quality: Mapped[str] = mapped_column(String(20), default="low")
    confidence: Mapped[str] = mapped_column(String(20), default="low")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())
```

```python
# src/models/gt_review.py
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin

class GroundTruthReview(Base, UUIDMixin):
    __tablename__ = "gt_reviews"
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("gt_candidates.id"), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    field_changes_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())
```

```python
# src/models/content_package.py
import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class ContentPackage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "content_packages"
    action_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_plans.id"), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    content_items: Mapped[dict] = mapped_column(JSONB, default=list)
    schema_items: Mapped[dict] = mapped_column(JSONB, default=list)
    publishing_checklist: Mapped[dict] = mapped_column(JSONB, default=list)
    fact_check_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")
```

- [ ] **Step 2: 扩展 GroundTruthVersion 字段**

在 `src/models/ground_truth.py` 的 `ground_truth_json` 后增加 GT 元数据字段:

```python
    required_fields_complete: Mapped[bool] = mapped_column(default=False)
    user_confirmed: Mapped[bool] = mapped_column(default=False)
    high_risk_fields_reviewed: Mapped[bool] = mapped_column(default=False)
    gt_coverage_rate: Mapped[float] = mapped_column(Float, default=0.0)
```

- [ ] **Step 3: 更新 models/__init__.py**

```python
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_evidence import GroundTruthEvidence
from src.models.gt_review import GroundTruthReview
from src.models.content_package import ContentPackage
# 加回 __all__
```

- [ ] **Step 4: 更新 conftest.py TRUNCATE_ALL**

```python
TRUNCATE_ALL = (
    "TRUNCATE TABLE content_packages, gt_reviews, gt_evidences, gt_candidates, "
    "insight_summaries, hallucination_results, api_usage_logs, query_results, "
    "metrics_snapshots, action_plans, content_library, collection_runs, "
    "competitor_sets, ground_truth_versions, prompt_versions, query_templates, "
    "brands, users, organizations CASCADE"
)
```

- [ ] **Step 5: 生成 migration**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m alembic revision --autogenerate -m "add_gt_candidate_evidence_review_content_package"
```

检查 migration 确保:
- `gt_candidates`, `gt_evidences`, `gt_reviews`, `content_packages` 四表创建
- `ground_truth_versions` 新增 `required_fields_complete`, `user_confirmed`, `high_risk_fields_reviewed`, `gt_coverage_rate`

- [ ] **Step 6: 运行 migration 并测试**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m alembic upgrade head
# Reset test DB:
cd "/home/ffh/explore geo" && DATABASE_URL="postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test" .venv/bin/python -c "
import asyncio; from sqlalchemy.ext.asyncio import create_async_engine; from src.models.base import Base
async def reset():
    e = create_async_engine('postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test')
    async with e.begin() as c: await c.run_sync(Base.metadata.drop_all); await c.run_sync(Base.metadata.create_all)
    await e.dispose()
asyncio.run(reset())
"
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_models.py -v
```

预期: 4 tests pass

- [ ] **Step 7: 提交**

```bash
git add alembic/versions/ src/models/ tests/conftest.py && git commit -m "feat: add GT Candidate/Evidence/Review + ContentPackage models"
```

---

### Task 2: Config — 搜索 + KPI 阈值 + Action 阈值

**Files:**
- Modify: `src/config.py`

- [ ] **Step 1: 扩展 config.py**

```python
# src/config.py — 在 platform_retry_config 后追加:

    # --- 搜索配置 ---
    google_search_api_key: str = ""
    google_search_cx: str = ""
    brave_search_api_key: str = ""

    # --- KPI 分析阈值 ---
    min_success_platforms_for_analysis: int = 2
    min_success_queries_for_analysis: int = 10

    # --- Action 触发阈值 ---
    action_thresholds: dict = {
        "citation_rate": 0.05,
        "accuracy_rate": 0.60,
        "completeness_rate": 0.50,
        "first_rec_rate": 0.10,
        "differentiation_rate": 0.30,
        "scenario_recall_rate": 0.20,
    }

    # --- GT 必填字段 ---
    gt_required_fields: list = [
        "official_name", "aliases", "industry", "category",
        "positioning", "core_products", "target_users",
        "core_scenarios", "key_differentiators",
        "official_domains", "source_of_truth_by_field",
    ]

    # --- GT 高风险字段 ---
    gt_high_risk_fields: list = [
        "official_name", "category", "positioning",
        "target_competitors", "forbidden_claims",
        "proof_points", "pricing", "certifications",
        "customers", "awards", "funding", "legal_sensitive_claims",
    ]
```

- [ ] **Step 2: 提交**

```bash
git add src/config.py && git commit -m "feat: add search config, action thresholds, GT field config"
```

---

### Task 3: 搜索层 — DuckDuckGo + AI Search + Google 预留

**Files:**
- Create: `src/search/__init__.py`, `src/search/duckduckgo_backend.py`, `src/search/ai_search_backend.py`
- 安装: `pip install duckduckgo-search`

- [ ] **Step 1: 安装依赖**

```bash
cd "/home/ffh/explore geo" && .venv/bin/pip install duckduckgo-search 2>&1 | tail -3
```

- [ ] **Step 2: 创建搜索接口**

```python
# src/search/__init__.py
from dataclasses import dataclass, field

@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source_quality: str = "low"

class SearchBackend:
    name: str = ""
    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        raise NotImplementedError

@dataclass
class PlatformCapabilities:
    supports_web_search: bool = False
    supports_citations: bool = False
    citation_format: str = ""

def get_available_backends(config) -> list[SearchBackend]:
    backends = [DuckDuckGoBackend()]
    if config.google_search_api_key and config.google_search_cx:
        pass  # Google backend 可用时在此注册
    return backends
```

```python
# src/search/duckduckgo_backend.py
from duckduckgo_search import DDGS
from src.search import SearchBackend, SearchResult

class DuckDuckGoBackend(SearchBackend):
    name = "duckduckgo"

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num):
                    quality = self._classify_quality(r.get("href", ""), r.get("body", ""))
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        url=r.get("href", ""),
                        source_quality=quality,
                    ))
        except Exception:
            pass
        return results

    def _classify_quality(self, url: str, snippet: str) -> str:
        if any(kw in url for kw in [".gov.cn", ".gov", "tianyancha.com", "qichacha.com"]):
            return "medium"
        return "low"
```

```python
# src/search/ai_search_backend.py
from src.search import SearchBackend, SearchResult, PlatformCapabilities

PLATFORM_CAPS = {
    "deepseek": PlatformCapabilities(supports_web_search=True, supports_citations=True),
    "kimi": PlatformCapabilities(supports_web_search=True, supports_citations=True),
    "doubao": PlatformCapabilities(supports_web_search=False, supports_citations=False),
    "wenxin": PlatformCapabilities(supports_web_search=False, supports_citations=False),
}

class AISearchBackend(SearchBackend):
    name = "ai_search"

    def __init__(self, platform_name: str, adapter):
        self.platform_name = platform_name
        self.adapter = adapter
        self.caps = PLATFORM_CAPS.get(platform_name, PlatformCapabilities())

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        if not self.caps.supports_web_search:
            return []
        try:
            response = await self.adapter.query(query, search_enabled=True)
            return [SearchResult(
                title="", snippet=response.answer_text[:500], url="",
                source_quality="medium",
            )] if response.answer_text else []
        except Exception:
            return []
```

- [ ] **Step 3: 提交**

```bash
git add src/search/ && git commit -m "feat: add multi-source search layer (DuckDuckGo + AI search)"
```

---

### Task 4: GT 自动采集 — 编排器 + 聚合引擎

**Files:**
- Create: `src/collector/gt_collector.py`
- Create: `src/analyzer/gt_aggregator.py`, `src/analyzer/gt_confidence.py`, `src/analyzer/gt_conflict_detector.py`
- Create: `tests/test_gt_collector.py`, `tests/test_gt_aggregator.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gt_collector.py
import pytest
from src.collector.gt_collector import collect_gt_candidate
from src.models.organization import Organization
from src.models.brand import Brand
from src.models.gt_candidate import GroundTruthCandidate

@pytest.mark.asyncio
async def test_collect_gt_creates_candidate(db_session, monkeypatch):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="象往科技", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    # Mock adapters + search to avoid real API calls
    from src.collector import gt_collector as gc
    async def mock_collect_from_ai(*a, **kw): return {}
    async def mock_collect_from_search(*a, **kw): return {}
    monkeypatch.setattr(gc, "_collect_from_ai_platforms", mock_collect_from_ai)
    monkeypatch.setattr(gc, "_collect_from_search", mock_collect_from_search)

    candidate = await collect_gt_candidate(str(brand.id), str(org.id), db_session)
    assert candidate is not None
    assert candidate.status == "pending_review"
```

```python
# tests/test_gt_aggregator.py
import pytest
from src.analyzer.gt_aggregator import aggregate_field_evidence
from src.analyzer.gt_confidence import compute_field_confidence

def test_aggregate_field_detects_conflict():
    sources = [
        {"value": "SaaS/旅游科技", "source_type": "ai_platform", "source_quality": "medium", "platform": "deepseek"},
        {"value": "SaaS/旅游科技", "source_type": "ai_platform", "source_quality": "medium", "platform": "kimi"},
        {"value": "旅游服务", "source_type": "search_result", "source_quality": "low", "platform": "duckduckgo"},
    ]
    result = aggregate_field_evidence("industry", sources)
    assert result["conflict_count"] == 0  # AI consensus vs low-quality search = no conflict
    assert result["ai_platform_agreement"] == 2

def test_confidence_high_requires_official_source():
    sources = [
        {"source_type": "ai_platform", "source_quality": "medium"},
        {"source_type": "search_result", "source_quality": "low"},
    ]
    conf = compute_field_confidence(sources)
    assert conf != "high"  # no official source
```

- [ ] **Step 3: 实现 gt_collector.py 编排器**

```python
# src/collector/gt_collector.py
import logging
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

GT_QUESTIONS = [
    ("identity", "{公司} 是一家什么样的公司？请详细描述。", ["official_name", "positioning", "industry"]),
    ("category", "{公司} 属于什么行业和什么具体品类？", ["industry", "category", "subcategory"]),
    ("products", "{公司} 的核心产品/服务有哪些？", ["core_products", "core_features"]),
    ("users", "{公司} 的目标用户是谁？主要服务什么人群？", ["target_users", "best_fit_users"]),
    ("scenarios", "{公司} 主要解决哪些用户问题或业务场景？", ["core_scenarios", "scenario_keywords"]),
    ("differentiation", "{公司} 和主要竞品相比有什么不同？有什么特点？", ["key_differentiators"]),
    ("competitors", "{公司} 的主要竞品或替代方案有哪些？", ["target_competitors", "alternative_solutions"]),
    ("misconceptions", "关于{公司}，有哪些常见误解或不能错误描述的地方？", ["forbidden_claims", "common_misconceptions"]),
    ("sources", "{公司} 有哪些官方来源可以证明它的信息？", ["source_of_truth_by_field", "official_docs", "official_channels"]),
    ("recommendation", "在什么情况下应该选择{公司}？推荐它的正确理由是什么？", ["preferred_recommendation_reasons", "best_fit_users"]),
]


async def collect_gt_candidate(brand_id: str, org_id: str, db: AsyncSession, company_name: str = None):
    from src.models.brand import Brand
    from src.models.gt_candidate import GroundTruthCandidate
    from sqlalchemy import select

    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    if not brand:
        raise ValueError("Brand not found")
    company = company_name or brand.name

    # 1. AI 平台采集
    ai_results = await _collect_from_ai_platforms(company)
    # 2. 搜索源采集
    search_results = await _collect_from_search(company)
    # 3. 字段级聚合
    from src.analyzer.gt_aggregator import aggregate_all_fields
    field_results = aggregate_all_fields(ai_results, search_results)

    candidate = GroundTruthCandidate(
        organization_id=org_id, brand_id=brand_id,
        candidate_json={f: r["value"] for f, r in field_results.items()},
        confidence_summary={
            f: {"confidence": r["confidence"], "evidence_count": r["evidence_count"],
                "has_official_source": r.get("official_source_count", 0) > 0}
            for f, r in field_results.items()
        },
        overall_confidence=_compute_overall(field_results),
        status="pending_review",
    )
    db.add(candidate)
    await db.commit()
    return candidate


async def _collect_from_ai_platforms(company: str) -> list[dict]:
    from src.adapters import get_adapter
    import src.collector.engine as ce
    import asyncio

    results = []
    for platform in ["deepseek", "kimi", "doubao"]:
        try:
            adapter = get_adapter(platform)
            for dim, template, fields in GT_QUESTIONS:
                question = template.replace("{公司}", company)
                response = await adapter.query(question)
                results.append({
                    "platform": platform, "dimension": dim, "question": question,
                    "answer": response.answer_text, "source_type": "ai_platform",
                    "source_quality": "medium", "target_fields": fields,
                })
        except Exception as e:
            logger.warning("GT AI collection failed for %s: %s", platform, e)
    return results


async def _collect_from_search(company: str) -> list[dict]:
    from src.search import get_available_backends
    from src.config import settings
    import asyncio

    results = []
    queries = [f"{company} 公司", f"{company} 产品", f"{company} 官网", f"{company} 怎么样"]
    backends = get_available_backends(settings)
    for backend in backends:
        for q in queries:
            try:
                items = await backend.search(q, num=3)
                for item in items:
                    results.append({
                        "platform": backend.name, "query": q, "title": item.title,
                        "snippet": item.snippet, "url": item.url,
                        "source_type": "search_result", "source_quality": item.source_quality,
                    })
            except Exception as e:
                logger.warning("Search failed for %s/%s: %s", backend.name, q, e)
    return results


def _compute_overall(field_results: dict) -> str:
    if not field_results:
        return "low"
    confs = [r.get("confidence", "low") for r in field_results.values()]
    high = confs.count("high")
    if high >= len(confs) * 0.5:
        return "high"
    if high >= 1 or confs.count("medium") >= len(confs) * 0.5:
        return "medium"
    return "low"
```

- [ ] **Step 4: 实现 gt_aggregator.py + gt_confidence.py**

```python
# src/analyzer/gt_aggregator.py
from collections import defaultdict

def aggregate_all_fields(ai_results: list[dict], search_results: list[dict]) -> dict:
    field_sources = defaultdict(list)

    for r in ai_results:
        for field in r.get("target_fields", []):
            field_sources[field].append({
                "value": r["answer"][:500], "source_type": "ai_platform",
                "source_quality": "medium", "platform": r["platform"],
            })

    for r in search_results:
        for field in _infer_fields_from_search(r.get("snippet", "")):
            field_sources[field].append({
                "value": r["snippet"][:300], "source_type": r["source_type"],
                "source_quality": r.get("source_quality", "low"),
                "url": r.get("url", ""), "platform": r["platform"],
            })

    from src.analyzer.gt_confidence import compute_field_confidence
    from src.analyzer.gt_conflict_detector import detect_conflicts

    result = {}
    for field, sources in field_sources.items():
        confidence = compute_field_confidence(sources)
        conflict = detect_conflicts(sources)
        values = [s["value"] for s in sources if s.get("value")]
        best_value = values[0] if values else ""
        result[field] = {
            "value": best_value, "confidence": confidence,
            "evidence_count": len(sources),
            "official_source_count": sum(1 for s in sources if s.get("source_quality") == "high"),
            "ai_platform_agreement": len(set(s["value"][:100] for s in sources if s["source_type"] == "ai_platform")),
            "conflict_count": conflict["conflict_count"],
        }
    return result


def _infer_fields_from_search(snippet: str) -> list[str]:
    fields = []
    if any(kw in snippet for kw in ["公司", "企业", "品牌", "平台"]):
        fields.extend(["official_name", "positioning"])
    if any(kw in snippet for kw in ["产品", "服务", "功能", "提供"]):
        fields.append("core_products")
    if any(kw in snippet for kw in ["官网", "官方", "http"]):
        fields.append("official_domains")
    return fields or ["positioning"]
```

```python
# src/analyzer/gt_confidence.py
def compute_field_confidence(sources: list[dict]) -> str:
    official_sources = [s for s in sources if s.get("source_quality") == "high"]
    ai_sources = [s for s in sources if s.get("source_type") == "ai_platform"]
    has_conflict = len(set(s.get("value", "")[:100] for s in sources)) > 1

    if official_sources and len(set(s.get("value", "")[:100] for s in ai_sources + official_sources)) <= 1:
        return "high"
    if len(ai_sources) >= 2 and not has_conflict:
        return "medium"
    if len(sources) == 1 and sources[0].get("source_quality") in ("low", "very_low"):
        return "low"
    if has_conflict:
        return "uncertain"
    return "low"


# src/analyzer/gt_conflict_detector.py
def detect_conflicts(sources: list[dict]) -> dict:
    values = [s.get("value", "")[:100] for s in sources if s.get("value")]
    unique = set(values)
    return {"conflict_count": len(unique) - 1 if len(unique) > 1 else 0, "has_conflict": len(unique) > 1}
```

- [ ] **Step 5: 运行测试**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_gt_collector.py tests/test_gt_aggregator.py -v
```

- [ ] **Step 6: 提交**

```bash
git add src/collector/gt_collector.py src/analyzer/gt_aggregator.py src/analyzer/gt_confidence.py src/analyzer/gt_conflict_detector.py tests/ && git commit -m "feat: add GT auto-collector with field-level confidence and conflict detection"
```

---

### Task 5-7 概述（因篇幅限制，后续 Task 的关键代码和步骤以精简形式呈现）

### Task 5: GT 审核层 — API + 确认界面

**Files:** Modify `src/api/ground_truth.py`, Create `src/templates/ground_truth/review.html`

核心逻辑:
- `GET /api/brands/{id}/gt-candidates` — 列出待审核候选
- `POST /api/gt-candidates/{id}/review` — 逐字段接受/编辑/删除/标记 uncertain
- 高风险字段列表从 `settings.gt_high_risk_fields` 读取
- 审核完成后 `promote_candidate_to_active_gt()`: 检查 `required_fields_complete && high_risk_fields_reviewed` → 创建 active GroundTruthVersion → 触发正式采集

测试: `test_user_review_promotes_candidate_to_active_gt`, `test_uncertain_fields_not_used_in_kpi`

### Task 6: 5 个新增 KPI (可并行于 Task 4-5)

**Files:** Create 5 个 analyzer 文件, Modify `src/analyzer/pipeline.py`

```python
# src/analyzer/scenario_recall.py 示例
async def compute_scenario_recall(brand_id, collection_run_id, db, scenario_keywords: list) -> dict:
    # 分子: 非品牌名场景问题中品牌被提及次数
    # 分母: 场景问题总数（排除含品牌名的直接提问）
    # 返回: {value, numerator, denominator, sample_size, confidence}
```

Pipeline 集成: 在 `compute_and_save_metrics()` 中追加 5 个新 KPI 计算，结果写入 `details_json["extended_kpis"]`。

测试: `tests/test_kpi_extended.py` (5 tests)

### Task 7: Action 内容执行准备器

**Files:** Create `src/actions/executor.py`, `fact_checker.py`, `content_package.py`, `schema_generator.py`, Modify `src/api/actions.py`

核心流程: `executor.generate_content_package(action_plan_id, db)` → 读取 active GT → LLM 生成内容 (遵守 prompt 约束) → `fact_checker.check()` → `schema_generator.generate_jsonld()` → 保存 ContentPackage → 用户审核 → 导出 Markdown/JSON-LD/发布清单

内容生成 Prompt:
```
基于以下 Ground Truth 生成内容。只能使用已确认字段。不得虚构客户、融资、奖项。不得使用"领先""第一""最大"。涉及竞品保持客观。事实性段落标注来源字段。不确定信息省略。
GT: {active_gt_json}
生成: {content_type}
```

测试: `tests/test_action_executor.py` (4 tests: confirmation required, only active GT used, forbidden claims blocked, package contains all deliverables)

### Task 8-14: Dashboard 页面 + config 验证 + E2E

- Task 8: Dashboard 新 KPI 卡片 (修改 `dashboard.py` + `index.html`)
- Task 9: GT 审核页面 (修改 `ground_truth.py` + 新模板 `review.html`)
- Task 10: Content Package 页面 (`actions.py` + `confirm.html`)
- Task 11: 消歧检查 (gt_collector 增加同名公司检测)
- Task 12: API 端点收尾 (brands.py GT 触发端点)
- Task 13: E2E 测试 (test_phase10_e2e.py)
- Task 14: 全量回归 + final cleanup

---

## Summary

| Task | 内容 | 测试数 | 依赖 |
|---|---|---|---|
| 1 | Migration: GT 三层 + Content Package + GT 扩展 | 4 (模型) | 无 |
| 2 | Config: 搜索 + Action 阈值 + GT 字段配置 | 0 (纯配置) | 无 |
| 3 | 搜索层: DuckDuckGo + AI search | 0 (集成测试) | 2 |
| 4 | GT 采集: 编排器 + 聚合 + 置信度 + 冲突检测 | 4 | 1,2,3 |
| 5 | GT 审核: API + 确认界面 | 3 | 4 |
| 6 | 5 新 KPI: 计算 + pipeline 集成 | 5 | 1 |
| 7 | Action 内容执行: 生成 + 检查 + 导出 | 4 | 1 |
| 8-14 | Dashboard + E2E + 收尾 | 3 | 5,6,7 |

**总计: 14 Tasks, ~23 new tests. 执行顺序: 1→2→3→4→5, 1→6(并行), 1→7(并行), 5+6+7→8-14**
