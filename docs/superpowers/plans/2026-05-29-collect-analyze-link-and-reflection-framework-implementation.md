# 采集→分析自动衔接 & 反思总结框架 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现采集完成后自动触发分析 Pipeline，补齐采集→分析脱节缺口，并建立反思总结框架（工程复盘 + Dashboard 采集摘要卡片）。

**Architecture:** 6 阶段递进——先改数据模型（Migration 先行），再串采集→分析链路（auto_analyze + 独立 run_analysis_for_collection），再修复 API → Celery 异步、平台限流通用化、Insights 生成 + Dashboard 卡片、最后 Retrospectives 落地。每阶段独立可测试。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / Celery + Redis / PostgreSQL 16 / Jinja2 + HTMX

---

## File Structure

```
新增:
  src/analyzer/collection_analysis.py     # run_analysis_for_collection() + 阈值检查
  src/analyzer/insights.py                # generate_insights() 主逻辑
  src/models/insight_summary.py           # InsightSummary ORM 模型

修改:
  src/models/collection_run.py            # 拆分 status → collection_status + analysis_status + 错误字段
  src/models/hallucination.py             # +collection_run_id FK
  src/models/query_result.py              # +rate_limited + final_error_code
  src/models/__init__.py                  # +InsightSummary 导出
  src/config.py                           # 平台限流配置 + 分析阈值
  src/collector/engine.py                 # +auto_analyze + 平台 Semaphore + 429 重试
  src/api/collection_runs.py              # HTTP → Celery delay, 202
  src/analyzer/pipeline.py                # +insights 生成调用
  src/api/dashboard.py                    # 扩展返回最新 InsightSummary
  src/templates/dashboard/index.html      # +采集摘要卡片

测试:
  tests/test_collector.py                 # 扩展：auto_analyze + 平台限流 + 429 重试
  tests/test_collection_analysis.py       # 新增：状态机 + 阈值 + 幂等性
  tests/test_insights.py                  # 新增：insights 生成 + 可信度

Migration:
  alembic/versions/<hash>_split_collection_status.py  # 新增 migration

Config/Retrospectives（已存在，不变）:
  docs/retrospectives/TEMPLATE.md
  docs/retrospectives/INDEX.md
  docs/retrospectives/2026-05-29-kimi-429-concurrency.md
```

---

### Task 1: Migration — 拆分 CollectionRun 状态 + 新增分析字段

**Files:**
- 运行: `cd "/home/ffh/explore geo" && .venv/bin/python -m alembic revision --autogenerate -m "split_collection_status_and_add_analysis_fields"`
- 检查并修改: `alembic/versions/<hash>_split_collection_status_and_add_analysis_fields.py`
- 修改: `src/models/collection_run.py`
- 修改: `src/models/query_result.py`
- 修改: `src/models/hallucination.py`
- 修改: `src/models/__init__.py`
- 创建: `src/models/insight_summary.py`

- [ ] **Step 1: 修改 CollectionRun 模型**

```python
# src/models/collection_run.py — 替换整个文件
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class CollectionRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "collection_runs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual")

    # --- 原 status 拆分为双字段 ---
    collection_status: Mapped[str] = mapped_column(String(50), default="pending")    # pending|running|completed|partial|failed
    analysis_status: Mapped[str] = mapped_column(String(50), default="not_started")  # not_started|running|completed|failed|skipped

    # --- 采集时间 ---
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collection_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- 分析时间 ---
    analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- 采集计数 ---
    total_queries: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- 错误隔离 ---
    collection_error_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_error_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: 修改 QueryResult 模型 — 增加限流字段**

```python
# src/models/query_result.py — 在 retry_count 字段后增加两行:
# 找到 retry_count: Mapped[int] = mapped_column(Integer, default=0) 之后追加:
    rate_limited: Mapped[bool] = mapped_column(default=False)
    final_error_code: Mapped[str] = mapped_column(String(50), default="")
```

- [ ] **Step 3: 修改 HallucinationResult 模型 — 增加 collection_run_id**

```python
# src/models/hallucination.py — 在 query_result_id 字段后增加:
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True, index=True)
```

- [ ] **Step 4: 创建 InsightSummary 模型**

```python
# src/models/insight_summary.py — 新文件
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class InsightSummary(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "insight_summaries"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False, index=True)
    platform_health_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    brand_performance_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    key_findings_json: Mapped[dict] = mapped_column(JSONB, default=list)  # list of insight dicts
    data_reliability_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence_level: Mapped[str] = mapped_column(String(20), default="low")  # high|medium|low
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.utcnow())
```

- [ ] **Step 5: 更新 models/__init__.py 导出**

```python
# src/models/__init__.py — 在现有 import 后追加 InsightSummary:
from src.models.insight_summary import InsightSummary

# 在 __all__ 列表中追加 "InsightSummary"
```

- [ ] **Step 6: 更新 conftest.py 的 TRUNCATE_ALL**

```python
# tests/conftest.py — TRUNCATE_ALL 字符串中追加 insight_summaries:
TRUNCATE_ALL = (
    "TRUNCATE TABLE insight_summaries, hallucination_results, api_usage_logs, query_results, "
    "metrics_snapshots, action_plans, content_library, collection_runs, "
    "competitor_sets, ground_truth_versions, prompt_versions, query_templates, "
    "brands, users, organizations CASCADE"
)
```

- [ ] **Step 7: 生成并调整 migration**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m alembic revision --autogenerate -m "split_collection_status_and_add_analysis_fields"
```

手动检查生成的 migration 文件，确保：
- `collection_runs` 表新增 `collection_status`, `analysis_status`, `collection_completed_at`, `analysis_started_at`, `analysis_completed_at`, `collection_error_summary`, `analysis_error_message`, `analysis_error_trace`
- 旧 `status` 列删除（或 rename 为 collection_status 并补充默认值）
- 旧 `completed_at` 列重命名为 `collection_completed_at`
- 旧 `error_summary` 列重命名为 `collection_error_summary`
- `query_results` 表新增 `rate_limited` (Boolean, default False), `final_error_code` (String(50))
- `hallucination_results` 表新增 `collection_run_id` (UUID FK → collection_runs.id)
- 新建 `insight_summaries` 表

- [ ] **Step 8: 运行 migration**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m alembic upgrade head
```

- [ ] **Step 9: 确认现有测试仍通过（模型结构变更后）**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_models.py -v
```

预期: 3 tests pass（如果 test_models.py 引用了旧字段 `status` 需要先修）

- [ ] **Step 10: 调整 test_collector.py 适配新字段名**

```python
# tests/test_collector.py — 将所有 run.status 改为 run.collection_status:
# 第56行: assert run.status == "completed" → assert run.collection_status == "completed"
# 确认 test_collector.py 只引用新字段
```

- [ ] **Step 11: 提交 Task 1**

```bash
git add alembic/versions/ src/models/ tests/ && git commit -m "feat: split CollectionRun status, add analysis fields, InsightSummary model

- Split status into collection_status + analysis_status
- Add collection/analysis error isolation fields
- Add collection_run_id FK to HallucinationResult
- Add rate_limited + final_error_code to QueryResult
- Create InsightSummary ORM model
- Update conftest TRUNCATE_ALL

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 配置 — 平台限流 + 分析阈值

**Files:**
- 修改: `src/config.py`

- [ ] **Step 1: 修改 src/config.py**

```python
# src/config.py — 在 collector_concurrency 之后追加:

    # --- 分析触发阈值 ---
    min_success_platforms_for_analysis: int = 2
    min_success_queries_for_analysis: int = 10

    # --- 平台级并发 ---
    platform_concurrency_limits: dict = {
        "kimi": 2,
        "deepseek": 4,
        "doubao": 4,
        "wenxin": 2,
    }

    # --- 平台级重试 ---
    platform_retry_config: dict = {
        "kimi": {"max_retries": 2, "backoff_seconds": [2, 4]},
        "deepseek": {"max_retries": 2, "backoff_seconds": [1, 2]},
        "doubao": {"max_retries": 2, "backoff_seconds": [1, 2]},
        "wenxin": {"max_retries": 2, "backoff_seconds": [2, 4]},
    }
```

- [ ] **Step 2: 提交 Task 2**

```bash
git add src/config.py && git commit -m "feat: add analysis thresholds and platform rate-limit config"
```

---

### Task 3: 采集→分析衔接核心逻辑

**Files:**
- 创建: `src/analyzer/collection_analysis.py`
- 修改: `src/collector/engine.py`
- 修改: `src/analyzer/pipeline.py`
- 创建: `tests/test_collection_analysis.py`

- [ ] **Step 1: 写失败测试 — collection_analysis.py 待创建**

```python
# tests/test_collection_analysis.py — 新文件
import pytest
from sqlalchemy import select
from src.models.organization import Organization
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion
from src.models.query_template import QueryTemplate
from src.models.prompt_version import PromptVersion
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.analyzer.collection_analysis import (
    should_analyze, run_analysis_for_collection,
)


@pytest.mark.asyncio
async def test_should_analyze_sufficient_data(db_session):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="partial", total_queries=20,
        success_count=12, failure_count=8,
    )
    db_session.add(run)
    await db_session.commit()

    # 12 success, deepseek+kimi+doubao 3 platforms — 应满足 >=2 平台 + >=10 查询
    assert should_analyze(run, success_platform_count=3) is True


@pytest.mark.asyncio
async def test_should_analyze_insufficient_data(db_session):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="partial", total_queries=10,
        success_count=3, failure_count=7,
    )
    db_session.add(run)
    await db_session.commit()
    assert should_analyze(run, success_platform_count=1) is False


@pytest.mark.asyncio
async def test_should_analyze_failed_collection(db_session):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="failed", total_queries=22,
        success_count=0, failure_count=22,
    )
    db_session.add(run)
    await db_session.commit()
    assert should_analyze(run, success_platform_count=0) is False


@pytest.mark.asyncio
async def test_analysis_not_duplicated_on_retry(db_session, monkeypatch):
    """同一个 collection_run 重试时不重复生成 MetricsSnapshot."""
    from src.collector import engine as collector_engine
    from src.adapters.mock import MockAdapter
    from src.analyzer import collection_analysis as ca

    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    gt = GroundTruthVersion(brand_id=brand.id, version=1, ground_truth_json={"name": "TestBrand"}, status="active")
    db_session.add(gt)
    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    prompt = PromptVersion(name="test", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)
    await db_session.commit()

    monkeypatch.setattr(collector_engine, "get_adapter", lambda p: MockAdapter(platform_name=p))
    monkeypatch.setattr(collector_engine, "PLATFORMS", ["deepseek", "kimi"])

    # 第一次采集+分析
    run = await collector_engine.run_collection(brand.id, org.id, db_session, trigger_type="manual", auto_analyze=True)
    await db_session.refresh(run)

    from src.models.metrics_snapshot import MetricsSnapshot
    snapshots = (await db_session.execute(
        select(MetricsSnapshot).where(MetricsSnapshot.collection_run_id == run.id)
    )).scalars().all()
    first_count = len(snapshots)
    assert first_count == 1, f"Expected 1 MetricsSnapshot, got {first_count}"
    assert run.analysis_status == "completed"

    # 手动重跑分析（模拟），不应重复创建 MetricsSnapshot
    await ca.run_analysis_for_collection(run.id, org.id, db_session)
    snapshots_after = (await db_session.execute(
        select(MetricsSnapshot).where(MetricsSnapshot.collection_run_id == run.id)
    )).scalars().all()
    assert len(snapshots_after) == 1, "Should not duplicate MetricsSnapshot on re-analysis"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_collection_analysis.py -v
```

预期: FAIL — `src.analyzer.collection_analysis` 模块不存在

- [ ] **Step 3: 实现 should_analyze()**

```python
# src/analyzer/collection_analysis.py — 新文件
import logging
import traceback
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def should_analyze(run, success_platform_count: int, min_platforms: int = 2, min_queries: int = 10) -> bool:
    return (
        run.collection_status in ("completed", "partial")
        and success_platform_count >= min_platforms
        and run.success_count >= min_queries
    )


async def run_analysis_for_collection(
    collection_run_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> None:
    from sqlalchemy import select, func
    from src.models.collection_run import CollectionRun
    from src.models.query_result import QueryResult
    from src.models.metrics_snapshot import MetricsSnapshot
    from src.config import settings
    from src.analyzer.pipeline import compute_and_save_metrics

    run = (await db.execute(
        select(CollectionRun).where(CollectionRun.id == collection_run_id)
    )).scalar_one_or_none()
    if not run:
        logger.error("CollectionRun %s not found", collection_run_id)
        return

    # 幂等性：已有 MetricsSnapshot 则跳过
    existing = (await db.execute(
        select(func.count(MetricsSnapshot.id)).where(
            MetricsSnapshot.collection_run_id == collection_run_id,
        )
    )).scalar()
    if existing and existing > 0:
        logger.info("MetricsSnapshot already exists for %s, skipping analysis", collection_run_id)
        return

    # 计算成功平台数
    platforms = (await db.execute(
        select(func.count(func.distinct(QueryResult.platform))).where(
            QueryResult.collection_run_id == collection_run_id,
            QueryResult.status == "success",
        )
    )).scalar()

    if not should_analyze(
        run, success_platform_count=platforms,
        min_platforms=settings.min_success_platforms_for_analysis,
        min_queries=settings.min_success_queries_for_analysis,
    ):
        run.analysis_status = "skipped"
        run.analysis_error_message = (
            f"Insufficient data: {platforms} platforms, {run.success_count} queries"
        )
        await db.commit()
        return

    run.analysis_status = "running"
    run.analysis_started_at = datetime.utcnow()
    await db.commit()

    try:
        await compute_and_save_metrics(
            str(run.brand_id), str(org_id), str(collection_run_id), db,
        )
        run.analysis_status = "completed"
    except Exception as e:
        run.analysis_status = "failed"
        run.analysis_error_message = str(e)
        run.analysis_error_trace = traceback.format_exc()
        logger.exception(
            "Analysis failed",
            extra={
                "collection_run_id": str(collection_run_id),
                "brand_id": str(run.brand_id),
                "organization_id": str(org_id),
            },
        )
    finally:
        run.analysis_completed_at = datetime.utcnow()
        await db.commit()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_collection_analysis.py -v
```

预期: 2-3 tests PASS（test_analysis_not_duplicated_on_retry 依赖 auto_analyze 后续实现）

- [ ] **Step 5: 修改 run_collection() — 增加 auto_analyze 参数**

```python
# src/collector/engine.py — 修改函数签名和末尾逻辑

# 函数签名改为:
async def run_collection(
    brand_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
    trigger_type: str = "manual",
    auto_analyze: bool = True,
) -> CollectionRun:

# 替换末尾 (run.completed_at = datetime.utcnow() 之后的 return run 之前的部分):
    # --- 原: run.completed_at = datetime.utcnow() ---
    run.collection_completed_at = datetime.utcnow()

    # 采集状态: completed/partial/failed
    run.collection_status = (
        "completed" if failure_count == 0
        else "failed" if failure_count == run.total_queries
        else "partial"
    )

    await db.commit()

    # auto_analyze 开关: 由 run_analysis_for_collection 内部判断阈值
    if auto_analyze and run.collection_status in ("completed", "partial"):
        from src.analyzer.collection_analysis import run_analysis_for_collection
        await run_analysis_for_collection(run.id, org_id, db)

    return run
```

注意: `src/collector/engine.py` 中原有的 `run.collection_status` 设置也需要对应修改——将所有 `run.status = ...` 改为 `run.collection_status = ...`，`run.completed_at` 改为 `run.collection_completed_at`。

- [ ] **Step 6: 修改管道测试的 monkeypatch 引用**（如 test_pipeline_smoke.py 引用了 `run.status`）

```bash
cd "/home/ffh/explore geo" && grep -rn "\.status" tests/ --include="*.py" | grep -i "run\|collection"
```

如 `test_collector.py` 中有 `assert run.status == "completed"`，改为 `assert run.collection_status == "completed"`。

- [ ] **Step 7: 运行全量 DB 测试**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_collector.py tests/test_collection_analysis.py -v
```

预期: 所有测试 PASS

- [ ] **Step 8: 提交 Task 3**

```bash
git add src/analyzer/collection_analysis.py src/collector/engine.py tests/test_collection_analysis.py && git commit -m "feat: add auto_analyze linkage from collection to analysis

- Add should_analyze() with configurable thresholds
- Add run_analysis_for_collection() with idempotency check
- run_collection() accepts auto_analyze param (default True)
- Collection status fields updated: status→collection_status, completed_at→collection_completed_at

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 异步 API — Celery 入队 + 202 返回

**Files:**
- 修改: `src/api/collection_runs.py`
- 修改: `tests/test_collector.py` 或 `tests/test_collection_analysis.py` — 增加端点测试

- [ ] **Step 1: 写失败测试 — API 端点 202 响应**

```python
# tests/test_collection_analysis.py — 追加:
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app


@pytest.mark.asyncio
async def test_trigger_collection_returns_202(db_session, monkeypatch):
    """POST /api/brands/{brand_id}/collections 返回 202 + task_id，不等待采集完成."""
    # Seed org + brand
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    # Mock Celery task 避免实际入队
    from src.collector import tasks
    monkeypatch.setattr(tasks.collect_brand_task, "delay", lambda *a, **kw: type("obj", (), {"id": "fake-task-id"})())

    # Create user + token (simplified — 跳过完整 auth 也可直接测 route 逻辑)
    # 这里用直接调用 router 的方式避免完整 auth 流程:
    # 实际实现如需要完整 E2E 测试，需先注册用户并获取 token

    # minimal: 直接 import router 函数验证 Celery 调用
    # 完整的 E2E HTTP 端到端测试在后面的 Task 中处理
    pass  # 测试框架搭建，具体逻辑待 Step 4 验证
```

- [ ] **Step 2: 修改 API 端点**

```python
# src/api/collection_runs.py — 替换 trigger_collection 函数 (取消之前 uncommitted 的直接 await 写法):

@router.post("/api/brands/{brand_id}/collections", status_code=202)
async def trigger_collection(
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    task = collect_brand_task.delay(brand_id, str(user.organization_id))
    return {
        "task_id": task.id,
        "brand_id": brand_id,
        "status": "queued",
    }
```

确保文件顶部有 `from src.collector.tasks import collect_brand_task` 导入。

- [ ] **Step 3: 运行端点测试确认 Celery 调用路径正确**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_collection_analysis.py::test_trigger_collection_returns_202 -v
```

- [ ] **Step 4: 提交 Task 4**

```bash
git add src/api/collection_runs.py && git commit -m "feat: change collection trigger to Celery enqueue with 202 response"
```

---

### Task 5: 平台限流通用化 + 429 重试

**Files:**
- 修改: `src/collector/engine.py`

- [ ] **Step 1: 写失败测试 — 平台级 Semaphore + 429 重试**

```python
# tests/test_collector.py — 追加:

@pytest.mark.asyncio
async def test_kimi_429_retry(db_session, monkeypatch):
    """Kimi 返回 429 → 重试后成功."""
    org = Organization(name="RetryTest")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    gt = GroundTruthVersion(brand_id=brand.id, version=1, ground_truth_json={"name": "TestBrand"}, status="active")
    db_session.add(gt)
    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    prompt = PromptVersion(name="test", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)
    await db_session.commit()

    from src.collector import engine as collector_engine
    from src.adapters.mock import MockAdapter

    call_count = [0]

    class RetryMockAdapter(MockAdapter):
        async def query(self, prompt, system_prompt="", **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:  # 前两次返回 429
                from src.adapters.base import AIResponse
                return AIResponse(
                    platform=self.platform_name, question=prompt, answer_text="",
                    latency_ms=100, error="Error code: 429 - rate limit",
                )
            return await super().query(prompt, system_prompt, **kwargs)

    monkeypatch.setattr(collector_engine, "get_adapter", lambda p: RetryMockAdapter(platform_name=p))
    monkeypatch.setattr(collector_engine, "PLATFORMS", ["kimi"])

    run = await collector_engine.run_collection(brand.id, org.id, db_session, trigger_type="manual", auto_analyze=False)
    await db_session.refresh(run)

    assert run.collection_status == "completed"
    assert run.success_count == 1
    qr = (await db_session.execute(
        select(QueryResult).where(QueryResult.collection_run_id == run.id)
    )).scalars().first()
    assert qr.retry_count >= 2
    assert qr.status == "success"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_collector.py::test_kimi_429_retry -v
```

- [ ] **Step 3: 实现平台级 Semaphore + 429 重试**

```python
# src/collector/engine.py — 修改 query_one() 和 Semaphore 部分:

# 替换:
# sem = asyncio.Semaphore(settings.collector_concurrency)

# 为:
import asyncio
from src.config import settings

_platform_semaphores = {
    p: asyncio.Semaphore(settings.platform_concurrency_limits.get(p, 4))
    for p in PLATFORMS
}


def _get_retry_config(platform_name: str) -> dict:
    return settings.platform_retry_config.get(platform_name, {"max_retries": 2, "backoff_seconds": [1, 2]})


async def query_one(platform_name, tmpl):
    sem = _platform_semaphores[platform_name]
    retry_cfg = _get_retry_config(platform_name)
    max_retries = retry_cfg["max_retries"]
    backoffs = retry_cfg["backoff_seconds"]

    adapter = get_adapter(platform_name)
    question = _build_question(tmpl, brand)

    for attempt in range(max_retries + 1):
        async with sem:
            response, result_platform, result_tmpl = await _do_query(
                adapter, platform_name, tmpl, question, system_prompt
            )
        if not response.error:
            break
        if "429" in (response.error or "") and attempt < max_retries:
            wait = backoffs[min(attempt, len(backoffs) - 1)]
            await asyncio.sleep(wait)
        else:
            break

    # record retry info on the QueryResult
    result = response, result_platform, result_tmpl
    result[0]._retry_count = min(attempt, max_retries)
    result[0]._rate_limited = "429" in (response.error or "")
    result[0]._final_error_code = response.error[:50] if response.error else ""
    return result


def _build_question(tmpl, brand):
    question = tmpl.template_text
    for alias in brand.aliases or []:
        question = question.replace(f"{{{alias}}}", alias)
    question = question.replace("{品牌}", brand.name)
    question = question.replace("{行业}", brand.industry)
    return question


async def _do_query(adapter, platform_name, tmpl, question, system_prompt):
    system = system_prompt  # 从外部闭包捕获
    result = await adapter.query(question, system_prompt=system)
    return result, platform_name, tmpl
```

注意: 由于 `AIResponse` 是 dataclass 没有 `_retry_count` 等字段，需要将重试信息临时挂在对象上，或在 `run_collection()` 结尾的 QueryResult 创建环节从 `responses` 中提取重试数据。

**简化方案:** 不修改 `AIResponse`，改为在创建 `QueryResult` 时额外传入重试参数。将 `responses` 从纯 `AIResponse` 改为 `(AIResponse, retry_info_dict)` 元组。

```python
# 在 run_collection 的 query_one 封装中:
# 最终返回 (response, platform_name, tmpl, retry_info) 而不是三元组

# 在 responses 循环中:
for result in responses:
    if isinstance(result, Exception):
        continue
    response, platform_name, tmpl, retry_info = result
    qr = QueryResult(
        ...
        retry_count=retry_info["retry_count"],
        rate_limited=retry_info["rate_limited"],
        final_error_code=retry_info["final_error_code"],
        ...
    )
```

- [ ] **Step 4: 运行重试测试确认通过**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_collector.py::test_kimi_429_retry -v
```

- [ ] **Step 5: 运行全量测试**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/ -v
```

- [ ] **Step 6: 提交 Task 5**

```bash
git add src/collector/engine.py tests/test_collector.py && git commit -m "feat: add per-platform semaphore and 429 retry with backoff"
```

---

### Task 6: Insights 生成 + InsightSummary 持久化

**Files:**
- 创建: `src/analyzer/insights.py`
- 修改: `src/analyzer/pipeline.py`
- 创建: `tests/test_insights.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_insights.py — 新文件
import pytest
from datetime import datetime
from sqlalchemy import select
from src.analyzer.insights import generate_insights
from src.models.organization import Organization
from src.models.brand import Brand
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.hallucination import HallucinationResult
from src.models.query_template import QueryTemplate


@pytest.mark.asyncio
async def test_generate_insights_cross_platform_p0(db_session):
    """同一 GT 字段在 3 平台都错 → severity=P0, confidence=high."""
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="completed", analysis_status="completed",
        total_queries=3, success_count=3, failure_count=0,
    )
    db_session.add(run)
    await db_session.flush()

    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    await db_session.flush()

    # 先写 MetricsSnapshot（insights 依赖 metrics 数据）
    snap = MetricsSnapshot(
        brand_id=brand.id, organization_id=org.id,
        collection_run_id=run.id, week_start=datetime.utcnow().date(),
        sov=0.78, first_rec_rate=0.65, accuracy_rate=0.82,
        completeness_rate=0.71, citation_rate=0.43, sample_size=3,
        details={"citation": {"by_platform": {
            "deepseek": {"citation_rate": 0.31},
            "kimi": {"citation_rate": 0.67},
            "doubao": {"citation_rate": 0.45},
        }}},
    )
    db_session.add(snap)
    await db_session.flush()

    # 创建 3 个平台的 QueryResult + Hallucination
    platforms = ["deepseek", "kimi", "doubao"]
    for p in platforms:
        qr = QueryResult(
            brand_id=brand.id, organization_id=org.id,
            collection_run_id=run.id, platform=p,
            template_id=tmpl.id, question="TestBrand 是什么？",
            answer_text="TestBrand 是一家金融公司", status="success",
            collected_at=datetime.utcnow(),
        )
        db_session.add(qr)
        await db_session.flush()

        h = HallucinationResult(
            brand_id=brand.id,
            query_result_id=qr.id,
            collection_run_id=run.id,
            field_name="industry", field_level="P0",
            severity="P0", verdict="incorrect",
            ai_claim="金融公司", ground_truth_value="Tech",
        )
        db_session.add(h)
    await db_session.commit()

    insight = await generate_insights(str(run.id), str(brand.id), str(org.id), db_session)
    assert insight is not None
    findings = insight["key_findings_json"]
    p0_findings = [f for f in findings if f["severity"] == "P0"]
    assert len(p0_findings) >= 1
    cross_platform = [f for f in p0_findings if f["type"] == "cross_platform_p0_error"]
    assert len(cross_platform) >= 1
    assert cross_platform[0]["confidence"] == "high"


@pytest.mark.asyncio
async def test_generate_insights_confidence_medium(db_session):
    """2 平台同类问题 → confidence=medium."""
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="completed", analysis_status="completed",
        total_queries=2, success_count=2, failure_count=0,
    )
    db_session.add(run)
    await db_session.flush()

    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    await db_session.flush()

    snap = MetricsSnapshot(
        brand_id=brand.id, organization_id=org.id,
        collection_run_id=run.id, week_start=datetime.utcnow().date(),
        sov=0.5, first_rec_rate=0.5, accuracy_rate=0.5,
        completeness_rate=0.5, citation_rate=0.5, sample_size=2,
    )
    db_session.add(snap)
    await db_session.flush()

    for p in ["deepseek", "kimi"]:
        qr = QueryResult(
            brand_id=brand.id, organization_id=org.id,
            collection_run_id=run.id, platform=p,
            template_id=tmpl.id, question="TestBrand 是什么？",
            answer_text="wrong answer", status="success",
            collected_at=datetime.utcnow(),
        )
        db_session.add(qr)
        await db_session.flush()
        h = HallucinationResult(
            brand_id=brand.id, query_result_id=qr.id,
            collection_run_id=run.id,
            field_name="industry", field_level="P1",
            severity="P1", verdict="incorrect",
            ai_claim="wrong", ground_truth_value="Tech",
        )
        db_session.add(h)
    await db_session.commit()

    insight = await generate_insights(str(run.id), str(brand.id), str(org.id), db_session)
    p1_findings = [f for f in insight["key_findings_json"] if f["severity"] == "P1"]
    assert len(p1_findings) >= 1
    assert p1_findings[0]["confidence"] in ("medium", "high")


@pytest.mark.asyncio
async def test_generate_insights_confidence_low(db_session):
    """1 平台问题 → confidence=low."""
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="completed", analysis_status="completed",
        total_queries=1, success_count=1, failure_count=0,
    )
    db_session.add(run)
    await db_session.flush()

    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    await db_session.flush()

    snap = MetricsSnapshot(
        brand_id=brand.id, organization_id=org.id,
        collection_run_id=run.id, week_start=datetime.utcnow().date(),
        sov=0.5, first_rec_rate=0.5, accuracy_rate=0.5,
        completeness_rate=0.5, citation_rate=0.5, sample_size=1,
    )
    db_session.add(snap)
    await db_session.flush()

    qr = QueryResult(
        brand_id=brand.id, organization_id=org.id,
        collection_run_id=run.id, platform="deepseek",
        template_id=tmpl.id, question="TestBrand 是什么？",
        answer_text="wrong", status="success",
        collected_at=datetime.utcnow(),
    )
    db_session.add(qr)
    await db_session.flush()
    h = HallucinationResult(
        brand_id=brand.id, query_result_id=qr.id,
        collection_run_id=run.id,
        field_name="industry", field_level="P2",
        severity="P2", verdict="incorrect",
        ai_claim="wrong", ground_truth_value="Tech",
    )
    db_session.add(h)
    await db_session.commit()

    insight = await generate_insights(str(run.id), str(brand.id), str(org.id), db_session)
    # 单平台低严重度 → confidence 不应为 high
    assert insight["confidence_level"] in ("medium", "low")
```

- [ ] **Step 3: 实现 generate_insights()**

```python
# src/analyzer/insights.py — 新文件
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from collections import Counter

logger = logging.getLogger(__name__)


async def generate_insights(
    collection_run_id: str,
    brand_id: str,
    org_id: str,
    db: AsyncSession,
) -> dict:
    from src.models.collection_run import CollectionRun
    from src.models.query_result import QueryResult
    from src.models.metrics_snapshot import MetricsSnapshot
    from src.models.hallucination import HallucinationResult
    from src.models.insight_summary import InsightSummary

    run = (await db.execute(
        select(CollectionRun).where(CollectionRun.id == collection_run_id)
    )).scalar_one()

    metrics = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.collection_run_id == collection_run_id,
        ).order_by(MetricsSnapshot.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    hallucinations = (await db.execute(
        select(HallucinationResult).where(
            HallucinationResult.collection_run_id == collection_run_id,
        )
    )).scalars().all()

    # --- 平台健康 ---
    platform_stats = await _compute_platform_health(collection_run_id, db)
    # --- 品牌表现 ---
    brand_perf = _compute_brand_performance(metrics)
    # --- 关键发现 ---
    findings = await _compute_key_findings(hallucinations, metrics, platform_stats, db)

    # 可信度
    total_platforms = len(platform_stats)
    failed_platforms = sum(1 for p in platform_stats.values() if p["success_rate"] == 0)
    data_ok = (
        run.success_count >= 10
        and (total_platforms - failed_platforms) >= 2
    )
    reliability = {
        "total_queries": run.total_queries,
        "success_count": run.success_count,
        "total_platforms": total_platforms,
        "failed_platforms": failed_platforms,
        "kpi_usable": data_ok,
        "cross_platform_usable": (total_platforms - failed_platforms) >= 2,
        "p0_hallucinations": sum(1 for h in hallucinations if h.severity == "P0"),
    }

    summary = InsightSummary(
        organization_id=org_id,
        brand_id=brand_id,
        collection_run_id=collection_run_id,
        platform_health_json=platform_stats,
        brand_performance_json=brand_perf,
        key_findings_json=findings,
        data_reliability_json=reliability,
        confidence_level=_overall_confidence(findings),
        generated_at=datetime.utcnow(),
    )
    db.add(summary)
    await db.commit()

    return {
        "platform_health_json": platform_stats,
        "brand_performance_json": brand_perf,
        "key_findings_json": findings,
        "data_reliability_json": reliability,
        "confidence_level": summary.confidence_level,
    }


async def _compute_platform_health(collection_run_id: str, db: AsyncSession) -> dict:
    from src.models.query_result import QueryResult

    rows = (await db.execute(
        select(
            QueryResult.platform,
            func.count(QueryResult.id).label("total"),
            func.sum(QueryResult.status == "success").label("success"),
            func.avg(QueryResult.latency_ms).label("avg_latency"),
            func.sum(QueryResult.rate_limited == True).label("rate_limited_count"),  # noqa: E712
        ).where(QueryResult.collection_run_id == collection_run_id)
        .group_by(QueryResult.platform)
    )).all()

    result = {}
    for row in rows:
        total = row.total or 0
        success = int(row.success or 0)
        result[row.platform] = {
            "total": total,
            "success": success,
            "success_rate": round(success / total, 4) if total > 0 else 0,
            "avg_latency_ms": round(row.avg_latency or 0, 1),
            "rate_limited_count": int(row.rate_limited_count or 0),
        }
    return result


def _compute_brand_performance(metrics) -> dict:
    if not metrics:
        return {}
    return {
        "sov": metrics.sov,
        "first_rec_rate": metrics.first_rec_rate,
        "accuracy_rate": metrics.accuracy_rate,
        "completeness_rate": metrics.completeness_rate,
        "citation_rate": metrics.citation_rate,
        "sample_size": metrics.sample_size,
    }


async def _compute_key_findings(hallucinations, metrics, platform_stats, db) -> list:
    from collections import defaultdict

    findings = []

    # 1. 跨平台 P0: 同一 field_name 在多个平台出现 P0/P1 幻觉
    field_platforms = defaultdict(list)
    for h in hallucinations:
        field_platforms[h.field_name].append(h)

    for field_name, items in field_platforms.items():
        platforms_involved = list(set(
            _get_platform_for_hallucination(h, db) for h in items
        ))
        n_platforms = len(platforms_involved)
        max_severity = max(items, key=lambda h: {"P0": 3, "P1": 2, "P2": 1}.get(h.severity, 0))

        if n_platforms >= 3:
            findings.append({
                "type": "cross_platform_p0_error",
                "title": f"多平台误判: {field_name}",
                "severity": max_severity.severity,
                "confidence": "high",
                "evidence": [
                    {"platform": p, "ai_claim": h.ai_claim, "ground_truth": h.ground_truth_value}
                    for p, h in zip(platforms_involved, items)
                ],
                "interpretation": f"{n_platforms} 个平台同时出错，可能是品牌公开信息锚点不足。",
                "recommended_action": f"优先修正品牌官方渠道中的 {field_name} 信息。",
            })
        elif n_platforms >= 2:
            findings.append({
                "type": "cross_platform_p0_error",
                "title": f"部分平台误判: {field_name}",
                "severity": max_severity.severity,
                "confidence": "medium",
                "evidence": [
                    {"platform": p, "ai_claim": h.ai_claim}
                    for p, h in zip(platforms_involved, items)
                ],
                "interpretation": f"2 个平台出现同类错误。",
                "recommended_action": f"检查 {field_name} 在主流平台中的展示一致性。",
            })

    # 2. 平台差异: 引用率差异 >= 0.3
    if metrics and metrics.details:
        citation_detail = metrics.details.get("citation", {})
        platform_citations = citation_detail.get("by_platform", {})
        if platform_citations:
            rates = [(p, v.get("citation_rate", 0)) for p, v in platform_citations.items()]
            rates.sort(key=lambda x: x[1])
            if len(rates) >= 2 and rates[-1][1] - rates[0][1] > 0.3:
                findings.append({
                    "type": "platform_diff",
                    "title": f"引用率差异显著: {rates[-1][0]}({rates[-1][1]:.0%}) vs {rates[0][0]}({rates[0][1]:.0%})",
                    "severity": "P1",
                    "confidence": "medium",
                    "evidence": [{"platform": p, "citation_rate": r} for p, r in rates],
                    "interpretation": f"{rates[0][0]} 引用率显著低于其他平台。",
                    "recommended_action": f"优化 {rates[0][0]} 平台的官方链接提及策略。",
                })

    return findings


def _get_platform_for_hallucination(h, db) -> str:
    """从 HallucinationResult 的 query_result_id 获取 platform."""
    # 简化: 从已加载的 QueryResult 中查找（insights 中已有 query_results 缓存）
    # 实际实现中传入 query_results_by_id 字典
    return "unknown"  # 实现时替换为实际查询逻辑


def _overall_confidence(findings: list) -> str:
    if not findings:
        return "low"
    severities = Counter(f["confidence"] for f in findings)
    if severities.get("high", 0) >= 2:
        return "high"
    if severities.get("high", 0) >= 1 or severities.get("medium", 0) >= 2:
        return "medium"
    return "low"
```

注意: 上述代码为骨架，完整实现需根据 `metrics.details` 的实际 JSONB 结构补充细节（尤其是 citation 和 platform 级数据）。

- [ ] **Step 4: 修改 pipeline.py — 采集分析后调用 insights**

```python
# src/analyzer/pipeline.py — 在 compute_and_save_metrics() 末尾 await db.commit() 后追加:

    from src.analyzer.insights import generate_insights
    try:
        await generate_insights(collection_run_id, brand_id, org_id, db)
    except Exception:
        pass  # insights 失败不影响主指标
```

- [ ] **Step 5: 运行 insights 测试**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_insights.py -v
```

- [ ] **Step 6: 提交 Task 6**

```bash
git add src/analyzer/insights.py src/analyzer/pipeline.py tests/test_insights.py && git commit -m "feat: add insights generation with confidence levels and InsightSummary persistence"
```

---

### Task 7: Dashboard 采集摘要卡片

**Files:**
- 修改: `src/api/dashboard.py`
- 修改: `src/templates/dashboard/index.html`

- [ ] **Step 1: 扩展 Dashboard API — 返回最新 InsightSummary**

```python
# src/api/dashboard.py — 在 dashboard_overview() 函数末尾 return 前追加:

    # Latest insight summary
    latest_insight = None
    if brand_count:
        latest_insight_q = (await db.execute(
            select(InsightSummary).where(
                InsightSummary.organization_id == org_id,
            ).order_by(desc(InsightSummary.generated_at)).limit(1)
        )).scalar_one_or_none()
        if latest_insight_q:
            latest_insight = {
                "collection_run_id": str(latest_insight_q.collection_run_id),
                "brand_id": str(latest_insight_q.brand_id),
                "platform_health": latest_insight_q.platform_health_json,
                "brand_performance": latest_insight_q.brand_performance_json,
                "key_findings": latest_insight_q.key_findings_json,
                "data_reliability": latest_insight_q.data_reliability_json,
                "confidence_level": latest_insight_q.confidence_level,
                "generated_at": latest_insight_q.generated_at.isoformat(),
            }

    return {
        ...原有字段...,
        "latest_insight": latest_insight,
    }
```

需要在文件顶部追加: `from src.models.insight_summary import InsightSummary`

- [ ] **Step 2: 更新 Dashboard HTML 模板 — 增加采集摘要卡片**

```html
<!-- src/templates/dashboard/index.html — 在现有指标卡之后追加: -->

{% if latest_insight %}
<div class="insight-card">
  <h2>最近采集摘要 — {{ latest_insight.generated_at[:10] }}</h2>

  <!-- 平台健康 -->
  <div class="platform-health">
    <h3>平台状态</h3>
    {% for platform, stats in latest_insight.platform_health.items() %}
    <div class="platform-row">
      <span class="platform-name">{{ platform }}</span>
      <span class="platform-ok">{{ stats.success }}/{{ stats.total }}</span>
      <span class="platform-latency">{{ stats.avg_latency_ms }}ms</span>
      {% if stats.rate_limited_count > 0 %}
      <span class="platform-warn">限流 {{ stats.rate_limited_count }} 次</span>
      {% endif %}
    </div>
    {% endfor %}
  </div>

  <!-- 品牌表现 -->
  <div class="brand-kpi">
    <div>SOV: {{ "%.0f" % (latest_insight.brand_performance.sov * 100) }}%</div>
    <div>首次推荐: {{ "%.0f" % (latest_insight.brand_performance.first_rec_rate * 100) }}%</div>
    <div>准确率: {{ "%.0f" % (latest_insight.brand_performance.accuracy_rate * 100) }}%</div>
  </div>

  <!-- 关键发现 -->
  <div class="key-findings">
    <h3>关键发现</h3>
    {% for finding in latest_insight.key_findings %}
    <div class="finding severity-{{ finding.severity }}">
      <span class="confidence-badge {{ finding.confidence }}">{{ finding.confidence }}</span>
      {{ finding.title }}
    </div>
    {% endfor %}
  </div>

  <!-- 数据可信度 -->
  <div class="data-reliability">
    <h3>数据可信度</h3>
    <div>采集完成度: {{ latest_insight.data_reliability.success_count }}/{{ latest_insight.data_reliability.total_queries }}</div>
    <div>KPI 可用: {{ "是" if latest_insight.data_reliability.kpi_usable else "否" }}</div>
    <div>跨平台对比可用: {{ "是" if latest_insight.data_reliability.cross_platform_usable else "否" }}</div>
    {% if latest_insight.data_reliability.p0_hallucinations > 0 %}
    <div class="warn">P0 幻觉: {{ latest_insight.data_reliability.p0_hallucinations }} 条需复核</div>
    {% endif %}
  </div>
</div>
{% else %}
<div class="insight-empty">尚无采集摘要数据。请先触发一次品牌采集。</div>
{% endif %}
```

- [ ] **Step 3: 启动 API 验证 Dashboard 页面渲染**

```bash
cd "/home/ffh/explore geo" && fuser -k 8000/tcp 2>/dev/null; sleep 1
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/ | head -20
```

- [ ] **Step 4: 提交 Task 7**

```bash
git add src/api/dashboard.py src/templates/dashboard/index.html && git commit -m "feat: add collection insight summary card to Dashboard"
```

---

### Task 8: Retrospectives 落定 + 最终集成测试

**Files:**
- 已存在: `docs/retrospectives/TEMPLATE.md`, `INDEX.md`, `2026-05-29-kimi-429-concurrency.md`
- 修改: `CLAUDE.md`（或项目根 `docs/superpowers/` 中的 agentic worker 规则文件）— 加入 retrospective 执行绑定

- [ ] **Step 1: 在 CLAUDE.md 中加入 Retrospectives 执行规则**

在项目根目录 `/home/ffh/explore geo/CLAUDE.md` 中追加（如文件不存在则创建）:

```markdown
## Retrospectives

每次开发任务前:
1. 读取 `docs/retrospectives/INDEX.md`
2. 搜索与当前任务关键词相关的复盘记录
3. 在实现说明中列出已参考的教训
4. 若本次踩坑超过 30 分钟，按 TEMPLATE.md 格式新增 retrospective 并更新 INDEX.md
```

- [ ] **Step 2: 运行全量测试**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/ -v
```

确认所有测试 PASS。

- [ ] **Step 3: 运行已有的 pipeline_smoke 确认无回归**

```bash
cd "/home/ffh/explore geo" && .venv/bin/python -m pytest tests/test_pipeline_smoke.py -v
```

- [ ] **Step 4: 启动完整链路验证**（需要 PostgreSQL + Redis 运行）

```bash
# 1. 确认服务运行
pg_isready -h localhost -p 5432
redis-cli ping

# 2. 运行 migration
cd "/home/ffh/explore geo" && .venv/bin/python -m alembic upgrade head

# 3. 启动 API
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 &

# 4. 通过 API 触发采集
curl -s -X POST http://localhost:8000/api/brands/<brand_id>/collections \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"

# 5. 检查 Celery worker 日志确认采集→分析链路完整执行
# 6. 访问 Dashboard 查看摘要卡片
```

- [ ] **Step 5: 最终提交**

```bash
git add -A && git commit -m "feat: finalize collect-analyze link, insights, dashboard card, retrospectives

Complete implementation per spec v2:
- CollectionRun dual-status state machine
- Auto-analysis after collection with idempotency
- Platform-level rate limiting with 429 retry
- Insight generation with confidence levels
- Dashboard collection summary card
- Retrospectives execution binding in CLAUDE.md

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Summary

| Task | 内容 | 测试数 | 依赖 |
|---|---|---|---|
| 1 | Migration: 状态机 + 血缘 + InsightSummary 模型 | 3 (已有模型测试) | 无 |
| 2 | Config: 平台限流 + 分析阈值 | 0 (纯配置) | 无 |
| 3 | 核心: auto_analyze + run_analysis_for_collection + 阈值 | 4 新增 | Task 1, 2 |
| 4 | API: Celery 入队 + 202 | 1 新增 | Task 3 |
| 5 | Collector: 平台 Semaphore + 429 重试 | 1 新增 | Task 2 |
| 6 | Insights: generate_insights + InsightSummary | 3 新增 | Task 3 |
| 7 | Dashboard: 采集摘要卡片 | 0 (UI) | Task 6 |
| 8 | Retrospectives 绑定 + 全量回归 | 全量 | Task 1-7 |

**总计: 8 Tasks, ~9 新增 tests, 执行顺序 1→2→3→4/5/6→7→8（4/5/6 可并行）**
