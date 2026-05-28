# GEO Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a brand AI visibility monitoring and optimization platform (GEO Explorer) — 4 AI platform adapters, question template engine, 5 KPI computation, hallucination detection, executable action plans, content factory, and a 7-page dashboard.

**Architecture:** Three-layer pipeline (Collector → Analyzer → Action Engine) on FastAPI + Celery + PostgreSQL + Redis. Collector runs 22 question templates across 4 adapters concurrently. Analyzer computes SOV, First-Recommendation Rate, Accuracy, Completeness, Citation Rate plus hallucination detection. Action Engine maps detection failures to executable tasks and content briefs. Dashboard renders via Jinja2 + HTMX.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Celery, Redis, PostgreSQL 16, Jinja2, HTMX, Docker Compose, pytest + pytest-asyncio.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `src/__init__.py`, `src/config.py`, `src/database.py`, `src/main.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.1
celery[redis]==5.4.0
redis==5.2.1
jinja2==3.1.4
python-multipart==0.0.19
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
pydantic==2.10.4
pydantic-settings==2.7.1
openai==1.59.9
volcenginesdkarkruntime==1.0.0
httpx==0.28.1
pytest==8.3.4
pytest-asyncio==0.25.0
pytest-cov==6.0.0
factory-boy==3.3.1
```

- [ ] **Step 2: Create .env.example**

```
# App
APP_ENV=development
SECRET_KEY=change-me-in-production

# Database
DATABASE_URL=postgresql+asyncpg://geo:geo@db:5432/geo_explorer

# Redis
REDIS_URL=redis://redis:6379/0

# AI Platform API Keys
DEEPSEEK_API_KEY=sk-your-key
KIMI_API_KEY=sk-your-key
DOUBAO_API_KEY=your-key
WENXIN_API_KEY=your-key
WENXIN_SECRET_KEY=your-secret
```

- [ ] **Step 3: Create src/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://geo:geo@localhost:5432/geo_explorer"
    redis_url: str = "redis://localhost:6379/0"

    deepseek_api_key: str = ""
    kimi_api_key: str = ""
    doubao_api_key: str = ""
    wenxin_api_key: str = ""
    wenxin_secret_key: str = ""

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Create src/database.py**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings

engine = create_async_engine(settings.database_url, echo=settings.app_env == "development")
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
```

- [ ] **Step 5: Create src/main.py**

```python
from fastapi import FastAPI

app = FastAPI(title="GEO Explorer", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Create Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 7: Create docker-compose.yml**

```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [db, redis]
    volumes: ["./src:/app/src"]

  worker:
    build: .
    command: celery -A src.collector.tasks worker --loglevel=info
    env_file: .env
    depends_on: [db, redis]
    volumes: ["./src:/app/src"]

  beat:
    build: .
    command: celery -A src.collector.tasks beat --loglevel=info
    env_file: .env
    depends_on: [db, redis]
    volumes: ["./src:/app/src"]

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: geo
      POSTGRES_PASSWORD: geo
      POSTGRES_DB: geo_explorer
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

volumes:
  pgdata:
```

- [ ] **Step 8: Run health check**

Run: `cd "/home/ffh/explore geo" && pip install fastapi uvicorn && python -c "from src.main import app; print('OK')"`

- [ ] **Step 9: Commit**

```bash
git add requirements.txt Dockerfile docker-compose.yml .env.example src/
git commit -m "feat: project scaffolding with FastAPI, Docker, config"
```

---

### Task 2: Database models — base and organization

**Files:**
- Create: `src/models/__init__.py`, `src/models/base.py`, `src/models/organization.py`, `src/models/user.py`

- [ ] **Step 1: Create src/models/base.py**

```python
import uuid
from datetime import datetime
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
```

- [ ] **Step 2: Create src/models/organization.py**

```python
import uuid
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDMixin

class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    users: Mapped[list["User"]] = relationship(back_populates="organization")
```

- [ ] **Step 3: Create src/models/user.py**

```python
import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDMixin

class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped["Organization"] = relationship(back_populates="users")
```

- [ ] **Step 4: Create src/models/__init__.py**

```python
from src.models.base import Base
from src.models.organization import Organization
from src.models.user import User

__all__ = ["Base", "Organization", "User"]
```

- [ ] **Step 5: Write migration init test**

Create `tests/__init__.py` (empty) and `tests/conftest.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.models.base import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

- [ ] **Step 6: Write model instantiation test**

Create `tests/test_models.py`:

```python
import pytest
from src.models.organization import Organization
from src.models.user import User

@pytest.mark.asyncio
async def test_create_organization(db_session):
    org = Organization(name="Test Corp", plan="pro")
    db_session.add(org)
    await db_session.commit()
    assert org.id is not None
    assert org.name == "Test Corp"

@pytest.mark.asyncio
async def test_create_user(db_session):
    org = Organization(name="Test Corp")
    db_session.add(org)
    await db_session.commit()
    user = User(organization_id=org.id, email="a@b.com", name="Test", role="admin", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    assert user.organization_id == org.id
```

- [ ] **Step 7: Run tests**

Run: `cd "/home/ffh/explore geo" && pip install pytest pytest-asyncio aiosqlite && python -m pytest tests/test_models.py -v`

Expected: 2 PASS

- [ ] **Step 8: Commit**

```bash
git add src/models/ tests/
git commit -m "feat: add base, organization, and user models"
```

---

### Task 3: Brand and Ground Truth models

**Files:**
- Create: `src/models/brand.py`, `src/models/ground_truth.py`

- [ ] **Step 1: Create src/models/brand.py**

```python
import uuid
from sqlalchemy import String, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDMixin

class Brand(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "brands"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list] = mapped_column(ARRAY(String), default=list)
    industry: Mapped[str] = mapped_column(String(255), default="")
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

- [ ] **Step 2: Create src/models/ground_truth.py**

```python
import uuid
from sqlalchemy import String, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class GroundTruthVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ground_truth_versions"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    ground_truth_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_urls: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    reviewer: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
```

- [ ] **Step 3: Write test**

Create `tests/test_brand_models.py`:

```python
import pytest
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

@pytest.mark.asyncio
async def test_create_brand_with_gt(db_session):
    org = Organization(name="Test Corp")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand",
                  aliases=["TB", "Test"], industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    gt = GroundTruthVersion(
        brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"},
        status="active"
    )
    db_session.add(gt)
    await db_session.commit()
    assert gt.id is not None
    assert gt.ground_truth_json["industry"] == "Tech"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_brand_models.py -v`

- [ ] **Step 5: Commit**

---

### Task 4: Query template and Prompt version models

**Files:**
- Create: `src/models/query_template.py`, `src/models/prompt_version.py`

- [ ] **Step 1: Create src/models/query_template.py**

```python
import uuid
from sqlalchemy import String, ForeignKey, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class QueryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "query_templates"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

- [ ] **Step 2: Create src/models/prompt_version.py**

```python
from sqlalchemy import String, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class PromptVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "prompt_versions"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    template_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(50), default="draft")
```

- [ ] **Step 3: Test and commit**

---

### Task 5: Query result and metrics models

**Files:**
- Create: `src/models/query_result.py`, `src/models/metrics_snapshot.py`

- [ ] **Step 1: Create src/models/query_result.py**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin

class QueryResult(Base, UUIDMixin):
    __tablename__ = "query_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_templates.id"), nullable=False)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    question: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    request_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), default="")
    model_version: Mapped[str] = mapped_column(String(100), default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    error_code: Mapped[str] = mapped_column(String(50), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
```

- [ ] **Step 2: Create src/models/metrics_snapshot.py**

```python
import uuid
from datetime import date
from sqlalchemy import String, ForeignKey, Integer, Float, Date
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class MetricsSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "metrics_snapshots"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sov: Mapped[float] = mapped_column(Float, default=0.0)
    first_rec_rate: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy_rate: Mapped[float] = mapped_column(Float, default=0.0)
    completeness_rate: Mapped[float] = mapped_column(Float, default=0.0)
    citation_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
```

- [ ] **Step 3: Test and commit**

---

### Task 6: Hallucination, Action Plan, Content Library, Competitor, API Usage models

**Files:**
- Create: `src/models/hallucination.py`, `src/models/action_plan.py`, `src/models/content_library.py`, `src/models/competitor_set.py`, `src/models/api_usage.py`

- [ ] **Step 1: Create all 5 model files**

`src/models/hallucination.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin

class HallucinationResult(Base, UUIDMixin):
    __tablename__ = "hallucination_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_level: Mapped[str] = mapped_column(String(10), default="P1")
    severity: Mapped[str] = mapped_column(String(10), default="P1")
    verdict: Mapped[str] = mapped_column(String(50), default="not_mentioned")
    ai_claim: Mapped[str] = mapped_column(Text, default="")
    ground_truth_value: Mapped[str] = mapped_column(Text, default="")
    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    human_verdict: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=None)
```

`src/models/action_plan.py`:

```python
import uuid
from datetime import date, datetime
from sqlalchemy import String, ForeignKey, Date, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class ActionPlan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "action_plans"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(100), default="")
    action_type: Mapped[str] = mapped_column(String(100), default="")
    priority: Mapped[str] = mapped_column(String(10), default="P1")
    evidence_query_result_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    evidence_hallucination_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    ai_wrong_claims: Mapped[dict] = mapped_column(JSONB, default=dict)
    correct_ground_truth: Mapped[dict] = mapped_column(JSONB, default=dict)
    suggested_content_type: Mapped[str] = mapped_column(String(100), default="")
    target_page: Mapped[str] = mapped_column(Text, default="")
    platform_target: Mapped[str] = mapped_column(String(100), default="")
    expected_metric_lift: Mapped[dict] = mapped_column(JSONB, default=dict)
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`src/models/content_library.py`:

```python
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class ContentLibrary(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "content_library"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    action_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_plans.id"), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    platform_target: Mapped[str] = mapped_column(String(100), default="")
    quality_check_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    published_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metric_impact: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`src/models/competitor_set.py`:

```python
import uuid
from sqlalchemy import String, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class CompetitorSet(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "competitor_sets"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    competitor_brand_ids: Mapped[list] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list)
    source_type: Mapped[str] = mapped_column(String(50), default="manual")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

`src/models/api_usage.py`:

```python
import uuid
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class ApiUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_usage_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    status: Mapped[str] = mapped_column(String(50), default="success")
```

- [ ] **Step 2: Update src/models/__init__.py** to export all models

- [ ] **Step 3: Write a smoke test that creates one of each model**

- [ ] **Step 4: Run tests and commit**

---

### Task 7: Platform adapter — base and DeepSeek

**Files:**
- Create: `src/adapters/__init__.py`, `src/adapters/base.py`, `src/adapters/deepseek.py`

- [ ] **Step 1: Create src/adapters/base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Citation:
    url: str
    type: str  # official | third_party | wiki
    context: str

@dataclass
class AIResponse:
    platform: str
    question: str
    answer_text: str
    citations: list[Citation] = field(default_factory=list)
    model_name: str = ""
    model_version: str = ""
    raw_response: dict | None = None
    latency_ms: int = 0
    error: str | None = None

class PlatformAdapter(ABC):
    @abstractmethod
    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse: ...

    @abstractmethod
    async def extract_citations(self, response: str) -> list[Citation]: ...
```

- [ ] **Step 2: Create src/adapters/deepseek.py**

```python
import time
from openai import AsyncOpenAI
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings

class DeepSeekAdapter(PlatformAdapter):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com"
        )
        self.default_model = "deepseek-v4-flash"

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        try:
            response = await self.client.chat.completions.create(
                model=kwargs.get("model", self.default_model),
                messages=[
                    {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            latency = int((time.time() - start) * 1000)
            return AIResponse(
                platform="deepseek",
                question=prompt,
                answer_text=response.choices[0].message.content or "",
                citations=await self.extract_citations(response.choices[0].message.content or ""),
                model_name=self.default_model,
                model_version=response.model,
                raw_response=response.model_dump(),
                latency_ms=latency,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return AIResponse(platform="deepseek", question=prompt, answer_text="", latency_ms=latency, error=str(e))

    async def extract_citations(self, response: str) -> list[Citation]:
        import re
        citations = []
        url_pattern = re.compile(r'https?://[^\s\)\]】一-鿿]+')
        for match in url_pattern.finditer(response):
            url = match.group()
            ctx_start = max(0, match.start() - 50)
            ctx_end = min(len(response), match.end() + 50)
            context = response[ctx_start:ctx_end]
            ctype = "official" if any(d in url for d in ["xiangwang", "official"]) else "third_party"
            citations.append(Citation(url=url, type=ctype, context=context))
        return citations
```

- [ ] **Step 3: Write adapter unit test with mock**

Create `tests/test_adapters/test_deepseek.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from src.adapters.deepseek import DeepSeekAdapter

@pytest.mark.asyncio
async def test_deepseek_query_mocked():
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = "TestBrand is a travel tech company."
    mock_response.model = "deepseek-v4-flash"

    with patch.object(DeepSeekAdapter, '__init__', lambda self: None):
        adapter = DeepSeekAdapter()
        adapter.client = AsyncMock()
        adapter.client.chat.completions.create = AsyncMock(return_value=mock_response)
        adapter.default_model = "deepseek-v4-flash"
        adapter.extract_citations = AsyncMock(return_value=[])

        result = await adapter.query("TestBrand是什么？")
        assert result.platform == "deepseek"
        assert "travel tech" in result.answer_text

@pytest.mark.asyncio
async def test_extract_citations():
    adapter = DeepSeekAdapter.__new__(DeepSeekAdapter)
    adapter.client = None
    adapter.default_model = "deepseek-v4-flash"
    result = await adapter.extract_citations("参考 https://example.com/docs 获取更多信息")
    assert len(result) == 1
    assert result[0].url == "https://example.com/docs"
```

- [ ] **Step 4: Run tests and commit**

---

### Task 8: Platform adapters — Kimi, Doubao, Wenxin

**Files:**
- Create: `src/adapters/kimi.py`, `src/adapters/doubao.py`, `src/adapters/wenxin.py`

- [ ] **Step 1: Kimi adapter (same pattern as DeepSeek, different base_url)**

```python
# src/adapters/kimi.py
from openai import AsyncOpenAI
from src.adapters.deepseek import DeepSeekAdapter
from src.config import settings

class KimiAdapter(DeepSeekAdapter):
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.kimi_api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        self.default_model = "kimi-k2.5"
```

- [ ] **Step 2: Doubao adapter**

```python
# src/adapters/doubao.py
import time
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings

class DoubaoAdapter(PlatformAdapter):
    def __init__(self):
        try:
            from volcenginesdkarkruntime import Ark
            self.client = Ark(
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key=settings.doubao_api_key,
            )
        except ImportError:
            self.client = None
        self.default_model = "doubao-seed-2-0-lite-260215"

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        if self.client is None:
            return AIResponse(platform="doubao", question=prompt, answer_text="",
                              error="volcenginesdkarkruntime not installed")
        try:
            response = self.client.chat.completions.create(
                model=kwargs.get("model", self.default_model),
                messages=[
                    {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            latency = int((time.time() - start) * 1000)
            return AIResponse(
                platform="doubao",
                question=prompt,
                answer_text=response.choices[0].message.content or "",
                citations=await self.extract_citations(response.choices[0].message.content or ""),
                model_name=self.default_model,
                raw_response={"choices": [{"message": {"content": response.choices[0].message.content}}]},
                latency_ms=latency,
            )
        except Exception as e:
            return AIResponse(platform="doubao", question=prompt, answer_text="",
                              latency_ms=int((time.time() - start) * 1000), error=str(e))

    async def extract_citations(self, response: str) -> list[Citation]:
        import re
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】一-鿿]+', response):
            url = match.group()
            ctx = response[max(0, match.start()-50):min(len(response), match.end()+50)]
            ctype = "official" if any(d in url for d in ["xiangwang", "official"]) else "third_party"
            citations.append(Citation(url=url, type=ctype, context=ctx))
        return citations
```

- [ ] **Step 3: Wenxin adapter**

```python
# src/adapters/wenxin.py
import time
import httpx
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings

class WenxinAdapter(PlatformAdapter):
    def __init__(self):
        self.api_key = settings.wenxin_api_key
        self.secret_key = settings.wenxin_secret_key
        self.default_model = "ernie-4.0-turbo-128k"
        self._access_token = None
        self._token_expiry = 0

    async def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expiry:
            return self._access_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://aip.baidubce.com/oauth/2.0/token",
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.api_key,
                    "client_secret": self.secret_key,
                }
            )
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = now + data.get("expires_in", 2592000) - 300
            return self._access_token

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro?access_token={token}",
                    json={
                        "messages": [
                            {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": kwargs.get("temperature", 0.3),
                        "max_output_tokens": kwargs.get("max_tokens", 2048),
                    },
                    timeout=30,
                )
                data = resp.json()
                latency = int((time.time() - start) * 1000)
                answer = data.get("result", "")
                return AIResponse(
                    platform="wenxin",
                    question=prompt,
                    answer_text=answer,
                    citations=await self.extract_citations(answer),
                    model_name=self.default_model,
                    raw_response=data,
                    latency_ms=latency,
                )
        except Exception as e:
            return AIResponse(platform="wenxin", question=prompt, answer_text="",
                              latency_ms=int((time.time() - start) * 1000), error=str(e))

    async def extract_citations(self, response: str) -> list[Citation]:
        import re
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】一-鿿]+', response):
            url = match.group()
            ctx = response[max(0, match.start()-50):min(len(response), match.end()+50)]
            ctype = "official" if any(d in url for d in ["xiangwang", "official"]) else "third_party"
            citations.append(Citation(url=url, type=ctype, context=ctx))
        return citations
```

- [ ] **Step 4: Update src/adapters/__init__.py**

```python
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.adapters.deepseek import DeepSeekAdapter
from src.adapters.kimi import KimiAdapter
from src.adapters.doubao import DoubaoAdapter
from src.adapters.wenxin import WenxinAdapter

ADAPTERS = {
    "deepseek": DeepSeekAdapter,
    "kimi": KimiAdapter,
    "doubao": DoubaoAdapter,
    "wenxin": WenxinAdapter,
}

def get_adapter(platform: str) -> PlatformAdapter:
    return ADAPTERS[platform]()
```

- [ ] **Step 5: Write mock tests for all 3 adapters, run, commit**

---

### Task 9: Collector — query engine

**Files:**
- Create: `src/collector/__init__.py`, `src/collector/engine.py`

- [ ] **Step 1: Create collector engine**

```python
# src/collector/engine.py
import asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.adapters import get_adapter
from src.adapters.base import PlatformAdapter
from src.models.brand import Brand
from src.models.query_template import QueryTemplate
from src.models.query_result import QueryResult
from src.models.api_usage import ApiUsage

PLATFORMS = ["deepseek", "kimi", "doubao", "wenxin"]

async def collect_brand(brand_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession):
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    if not brand:
        return {"error": "brand not found"}

    templates = (await db.execute(
        select(QueryTemplate).where(
            (QueryTemplate.organization_id == org_id) | (QueryTemplate.organization_id.is_(None)),
            QueryTemplate.is_active == True
        )
    )).scalars().all()

    results = []
    for platform_name in PLATFORMS:
        adapter = get_adapter(platform_name)
        for tmpl in templates:
            question = tmpl.template_text.replace("{品牌}", brand.name)
            for alias in brand.aliases:
                question = question.replace(f"{{{alias}}}", alias)

            response = await adapter.query(question)

            qr = QueryResult(
                brand_id=brand_id,
                organization_id=org_id,
                platform=platform_name,
                template_id=tmpl.id,
                question=question,
                answer_text=response.answer_text,
                citations=[{"url": c.url, "type": c.type, "context": c.context} for c in response.citations],
                model_name=response.model_name,
                model_version=response.model_version,
                response_raw_json=response.raw_response,
                status="error" if response.error else "success",
                error_message=response.error or "",
                latency_ms=response.latency_ms,
                collected_at=datetime.utcnow(),
            )
            db.add(qr)
            results.append({"platform": platform_name, "template": tmpl.id, "status": qr.status})

            usage = ApiUsage(
                organization_id=org_id, brand_id=brand_id, platform=platform_name,
                query_result_id=qr.id, prompt_tokens=len(question) // 4,
                completion_tokens=len(response.answer_text) // 4 if response.answer_text else 0,
                cost=0, status="failed" if response.error else "success",
            )
            db.add(usage)
            await db.flush()
            qr_ref = qr
            usage.query_result_id = qr_ref.id

    await db.commit()
    return {"brand_id": str(brand_id), "total": len(results),
            "errors": sum(1 for r in results if r["status"] == "error")}

async def collect_all_brands(org_id: uuid.UUID, db: AsyncSession):
    brands = (await db.execute(select(Brand).where(Brand.organization_id == org_id))).scalars().all()
    tasks = [collect_brand(b.id, org_id, db) for b in brands]
    return await asyncio.gather(*tasks)
```

- [ ] **Step 2: Write test with mock adapter**

- [ ] **Step 3: Run tests and commit**

---

### Task 10: Celery tasks for scheduled collection

**Files:**
- Create: `src/collector/tasks.py`, `src/celery_app.py`

- [ ] **Step 1: Create Celery app**

```python
# src/celery_app.py
from celery import Celery
from src.config import settings

app = Celery("geo_explorer", broker=settings.redis_url)
app.conf.update(
    beat_schedule={
        "weekly-collection": {
            "task": "src.collector.tasks.weekly_collect",
            "schedule": 604800.0,  # 7 days in seconds
        },
    },
    timezone="Asia/Shanghai",
)
```

- [ ] **Step 2: Create Celery task**

```python
# src/collector/tasks.py
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.celery_app import app
from src.config import settings
from src.collector.engine import collect_all_brands

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

@app.task
def collect_brand_task(brand_id: str, org_id: str):
    async def _run():
        async with SessionLocal() as db:
            return await __import__('src.collector.engine', fromlist=['collect_brand']).collect_brand(
                uuid.UUID(brand_id), uuid.UUID(org_id), db
            )
    return asyncio.run(_run())

@app.task
def weekly_collect():
    async def _run():
        async with SessionLocal() as db:
            from sqlalchemy import select
            from src.models.brand import Brand
            brands = (await db.execute(select(Brand))).scalars().all()
            result = await collect_all_brands(brands[0].organization_id if brands else uuid.uuid4(), db)
            return str(result)
    return asyncio.run(_run())
```

- [ ] **Step 3: Test celery task loading, commit**

---

### Task 11: Analyzer — SOV and First-Recommendation Rate

**Files:**
- Create: `src/analyzer/__init__.py`, `src/analyzer/sov.py`, `src/analyzer/first_rec.py`

- [ ] **Step 1: SOV calculator**

```python
# src/analyzer/sov.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.models.query_result import QueryResult
from src.models.brand import Brand

async def compute_sov(brand_id: str, org_id: str, db: AsyncSession, platform: str | None = None) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    aliases = [brand.name] + (brand.aliases or [])

    base_query = select(QueryResult).where(
        QueryResult.brand_id == brand_id,
        QueryResult.status == "success",
    )
    if platform:
        base_query = base_query.where(QueryResult.platform == platform)

    results = (await db.execute(base_query)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"sov": 0.0, "mentioned": 0, "total_valid": 0}

    mentioned = 0
    for r in valid:
        if any(alias.lower() in r.answer_text.lower() for alias in aliases):
            mentioned += 1

    return {
        "sov": round(mentioned / len(valid), 4),
        "mentioned": mentioned,
        "total_valid": len(valid),
        "total_attempted": len(results),
        "failure_rate": round(1 - len(valid) / len(results), 4) if results else 0,
    }
```

- [ ] **Step 2: First-Recommendation Rate calculator**

```python
# src/analyzer/first_rec.py
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.query_template import QueryTemplate

FIRST_REC_PATTERNS = [
    r'(?:首选|最推荐|优先考虑|强烈推荐|最值得|第一名)\S{0,20}({brand})',
    r'({brand})\S{0,10}(?:最好|最佳|最合适|首选|推荐)',
]

async def compute_first_rec(brand_id: str, org_id: str, db: AsyncSession, platform: str | None = None) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()

    rec_template_ids = (await db.execute(
        select(QueryTemplate.id).where(QueryTemplate.dimension == "场景推荐")
    )).scalars().all()

    base_query = select(QueryResult).where(
        QueryResult.brand_id == brand_id,
        QueryResult.status == "success",
        QueryResult.template_id.in_(rec_template_ids),
    )
    if platform:
        base_query = base_query.where(QueryResult.platform == platform)

    results = (await db.execute(base_query)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"first_rec_rate": 0.0, "first_count": 0, "total_rec_answers": 0}

    first_count = 0
    for r in valid:
        text = r.answer_text
        # Check ordered list: 1. BrandName
        list_match = re.findall(r'(?:^|\n)\s*(?:\d+[\.\)、]|[-*])\s*([^\n]{0,80})', text)
        if list_match and brand.name in list_match[0]:
            first_count += 1
            continue
        # Check pattern-based
        for pattern in FIRST_REC_PATTERNS:
            if re.search(pattern.replace("{brand}", re.escape(brand.name)), text):
                first_count += 1
                break

    return {
        "first_rec_rate": round(first_count / len(valid), 4),
        "first_count": first_count,
        "total_rec_answers": len(valid),
    }
```

- [ ] **Step 4: Write tests with sample AI responses, run, commit**

---

### Task 12: Analyzer — Accuracy, Completeness, Citation rate

**Files:**
- Create: `src/analyzer/accuracy.py`, `src/analyzer/completeness.py`, `src/analyzer/citation.py`

- [ ] **Step 1: Accuracy calculator (讲对率)**

```python
# src/analyzer/accuracy.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

async def compute_accuracy(brand_id: str, org_id: str, db: AsyncSession, platform: str | None = None) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    gt_version = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active"
        )
    )).scalar_one_or_none()

    if not gt_version:
        return {"accuracy_rate": 0.0, "mentioned_fields": 0, "correct_fields": 0, "error": "no active ground truth"}

    gt = gt_version.ground_truth_json
    check_fields = ["official_name", "industry", "category", "positioning",
                    "target_users", "core_scenarios", "differentiators", "tech_tags", "market_position"]

    results = (await db.execute(
        select(QueryResult).where(
            QueryResult.brand_id == brand_id,
            QueryResult.status == "success",
        )
    )).scalars().all()
    valid = [r for r in results if r.answer_text]

    total_mentioned = 0
    total_correct = 0
    for r in valid:
        text = r.answer_text
        for field in check_fields:
            gt_value = gt.get(field)
            if not gt_value:
                continue
            mentioned = _field_mentioned(field, str(gt_value), text)
            if mentioned:
                total_mentioned += 1
                if _field_correct(field, str(gt_value), text):
                    total_correct += 1

    return {
        "accuracy_rate": round(total_correct / total_mentioned, 4) if total_mentioned else 0.0,
        "mentioned_fields": total_mentioned,
        "correct_fields": total_correct,
    }

def _field_mentioned(field: str, gt_value: str, text: str) -> bool:
    return gt_value.lower()[:20] in text.lower()

def _field_correct(field: str, gt_value: str, text: str) -> bool:
    return gt_value.lower()[:20] in text.lower()
```

- [ ] **Step 2: Completeness calculator (认知完整度)**

```python
# src/analyzer/completeness.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

GT_FIELDS = ["official_name", "industry", "category", "positioning",
             "target_users", "core_scenarios", "differentiators", "tech_tags", "market_position"]

async def compute_completeness(brand_id: str, org_id: str, db: AsyncSession, platform: str | None = None) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    gt_version = (await db.execute(
        select(GroundTruthVersion).where(GroundTruthVersion.brand_id == brand_id, GroundTruthVersion.status == "active")
    )).scalar_one_or_none()
    if not gt_version:
        return {"completeness_rate": 0.0, "covered_fields": 0, "total_fields": len(GT_FIELDS), "error": "no active ground truth"}

    gt = gt_version.ground_truth_json
    total_fields = sum(1 for f in GT_FIELDS if gt.get(f))
    if total_fields == 0:
        return {"completeness_rate": 0.0, "covered_fields": 0, "total_fields": 0}

    results = (await db.execute(select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success"
    ))).scalars().all()
    valid = [r for r in results if r.answer_text]

    all_text = "\n".join(r.answer_text for r in valid)
    covered = 0
    for field in GT_FIELDS:
        gt_value = gt.get(field)
        if not gt_value:
            continue
        if str(gt_value).lower()[:20] in all_text.lower():
            covered += 1

    return {"completeness_rate": round(covered / total_fields, 4), "covered_fields": covered, "total_fields": total_fields}
```

- [ ] **Step 3: Citation rate calculator**

```python
# src/analyzer/citation.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

async def compute_citation_rate(brand_id: str, org_id: str, db: AsyncSession, platform: str | None = None) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    aliases = [brand.name] + (brand.aliases or [])

    gt_version = (await db.execute(
        select(GroundTruthVersion).where(GroundTruthVersion.brand_id == brand_id, GroundTruthVersion.status == "active")
    )).scalar_one_or_none()

    official_domains = []
    if gt_version:
        official_domains = gt_version.ground_truth_json.get("official_domains", [])

    base_q = select(QueryResult).where(QueryResult.brand_id == brand_id, QueryResult.status == "success")
    if platform:
        base_q = base_q.where(QueryResult.platform == platform)

    results = (await db.execute(base_q)).scalars().all()
    valid = [r for r in results if r.answer_text]

    mentioned_count = 0
    cited_count = 0
    for r in valid:
        text = r.answer_text
        if any(a.lower() in text.lower() for a in aliases):
            mentioned_count += 1
            if r.citations:
                for c in r.citations:
                    c_url = c.get("url", "") if isinstance(c, dict) else str(c)
                    if any(d in c_url for d in official_domains):
                        cited_count += 1
                        break
            # Also check for inline URLs
            import re
            found_urls = re.findall(r'https?://[^\s\)\]】]+', text)
            if any(any(d in u for d in official_domains) for u in found_urls):
                cited_count += 1

    return {
        "citation_rate": round(cited_count / mentioned_count, 4) if mentioned_count else 0.0,
        "cited_contexts": cited_count,
        "mentioned_contexts": mentioned_count,
    }
```

- [ ] **Step 4: Unit tests, commit**

---

### Task 13: Analyzer — Hallucination detector

**Files:**
- Create: `src/analyzer/hallucination.py`

- [ ] **Step 1: HallucinationDetector**

```python
# src/analyzer/hallucination.py
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.models.hallucination import HallucinationResult

FIELD_LEVELS = {
    "official_name": "P0", "industry": "P0", "category": "P0", "positioning": "P0",
    "target_users": "P1", "core_scenarios": "P1", "differentiators": "P1",
    "tech_tags": "P2", "market_position": "P2",
}

@dataclass
class Claim:
    field_name: str
    value: str
    context: str  # surrounding text snippet

@dataclass
class HallucinationReport:
    brand_id: str
    query_result_id: str
    detections: list[dict] = field(default_factory=list)

class HallucinationDetector:
    def extract_claims(self, response: str) -> list[Claim]:
        claims = []
        field_keywords = {
            "industry": ["行业", "领域", "属于"],
            "positioning": ["定位", "是", "核心"],
            "target_users": ["用户", "客户", "面向", "适合"],
            "differentiators": ["不同于", "优势", "特色", "区别"],
        }
        for field, keywords in field_keywords.items():
            for kw in keywords:
                idx = response.find(kw)
                if idx >= 0:
                    ctx = response[max(0, idx-30):min(len(response), idx+80)]
                    claims.append(Claim(field_name=field, value=kw, context=ctx))
        return claims

    async def detect(self, query_result: QueryResult, gt: GroundTruthVersion, db: AsyncSession) -> list[HallucinationResult]:
        gt_json = gt.ground_truth_json
        claims = self.extract_claims(query_result.answer_text)
        detections = []
        for claim in claims:
            gt_value = gt_json.get(claim.field_name, "")
            if not gt_value:
                continue
            verdict = "uncertain"  # Simplified V1: flag uncertain by default, human reviews
            if str(gt_value).lower() in query_result.answer_text.lower():
                verdict = "correct"
            elif claim.value.lower() not in str(gt_value).lower():
                verdict = "uncertain"

            h = HallucinationResult(
                brand_id=query_result.brand_id,
                query_result_id=query_result.id,
                ground_truth_version_id=gt.id,
                field_name=claim.field_name,
                field_level=FIELD_LEVELS.get(claim.field_name, "P1"),
                severity=FIELD_LEVELS.get(claim.field_name, "P1"),
                verdict=verdict,
                ai_claim=claim.context,
                ground_truth_value=str(gt_value),
                detected_at=None,
            )
            detections.append(h)
        return detections
```

- [ ] **Step 2: Test, commit**

---

### Task 14: Analyzer — Competitor matrix

**Files:**
- Create: `src/analyzer/competitor.py`

- [ ] **Step 1: Competitor matrix builder**

```python
# src/analyzer/competitor.py
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.competitor_set import CompetitorSet
from src.models.metrics_snapshot import MetricsSnapshot

METRICS = ["sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"]

async def build_competitor_matrix(brand_id: str, org_id: str, db: AsyncSession) -> dict:
    active_set = (await db.execute(
        select(CompetitorSet).where(CompetitorSet.brand_id == brand_id, CompetitorSet.is_active == True)
    )).scalars().first()

    if not active_set:
        return {"matrix": [], "metric_names": METRICS}

    brand_ids = [uuid.UUID(brand_id)] + [uuid.UUID(cid) for cid in active_set.competitor_brand_ids]
    latest_snapshots = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id.in_(brand_ids),
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(MetricsSnapshot.brand_id, MetricsSnapshot.week_start.desc())
    )).scalars().all()

    latest_by_brand = {}
    for snap in latest_snapshots:
        if snap.brand_id not in latest_by_brand:
            latest_by_brand[snap.brand_id] = snap

    rows = []
    for bid in brand_ids:
        snap = latest_by_brand.get(bid)
        if not snap:
            continue
        rows.append({
            "brand_id": str(bid),
            "sov": snap.sov,
            "first_rec_rate": snap.first_rec_rate,
            "accuracy_rate": snap.accuracy_rate,
            "completeness_rate": snap.completeness_rate,
            "citation_rate": snap.citation_rate,
            "sample_size": snap.sample_size,
        })
    return {"matrix": rows, "metric_names": METRICS}

async def build_trend_comparison(brand_id: str, org_id: str, weeks: int, db: AsyncSession) -> dict:
    """Return weekly trend for brand and its competitors over N weeks."""
    active_set = (await db.execute(
        select(CompetitorSet).where(CompetitorSet.brand_id == brand_id, CompetitorSet.is_active == True)
    )).scalars().first()

    brand_ids = [uuid.UUID(brand_id)]
    if active_set:
        brand_ids += [uuid.UUID(cid) for cid in active_set.competitor_brand_ids]

    snapshots = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id.in_(brand_ids),
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(MetricsSnapshot.week_start.desc()).limit(weeks * len(brand_ids))
    )).scalars().all()

    trends = {}
    for snap in snapshots:
        wk = snap.week_start.isoformat()
        if wk not in trends:
            trends[wk] = {}
        trends[wk][str(snap.brand_id)] = {m: getattr(snap, m) for m in METRICS}

    return {"trends": trends, "metric_names": METRICS}
```

- [ ] **Step 2: Test, commit**

---

### Task 15: Action engine — trigger to task mapping

**Files:**
- Create: `src/actions/__init__.py`, `src/actions/engine.py`

- [ ] **Step 1: Action engine that reads hallucination results and metric gaps, auto-generates prioritized ActionPlan records**

```python
# src/actions/engine.py
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.hallucination import HallucinationResult
from src.models.action_plan import ActionPlan

TRIGGER_MAP = {
    "P0": {"action_type": "definition_correction", "content_type": "FAQ"},
    "P1": {"action_type": "authority_building", "content_type": "Q&A"},
    "P2": {"action_type": "content_enrichment", "content_type": "Tutorial"},
}

async def generate_action_plans(brand_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession):
    hallucinations = (await db.execute(
        select(HallucinationResult).where(
            HallucinationResult.brand_id == brand_id,
            HallucinationResult.human_reviewed == False,
        )
    )).scalars().all()

    plans = []
    for h in hallucinations:
        trigger = TRIGGER_MAP.get(h.field_level, TRIGGER_MAP["P2"])
        plan = ActionPlan(
            brand_id=brand_id,
            organization_id=org_id,
            trigger_type=f"field_{h.field_name}_error",
            action_type=trigger["action_type"],
            priority=h.field_level,
            evidence_hallucination_ids=[h.id],
            ai_wrong_claims={"claim": h.ai_claim},
            correct_ground_truth={"value": h.ground_truth_value},
            suggested_content_type=trigger["content_type"],
            acceptance_criteria=f"Hallucination for {h.field_name} resolved in next scan",
            status="pending",
        )
        db.add(plan)
        plans.append(plan)

    await db.commit()
    return plans
```

- [ ] **Step 2: Test, commit**

---

### Task 16: Content factory

**Files:**
- Create: `src/actions/content_factory.py`

- [ ] **Step 1: Content factory generates content briefs based on ActionPlan**

```python
# src/actions/content_factory.py
CONTENT_TEMPLATES = {
    "FAQ": {
        "structure": "## Q: {{question}}\n## A: {{answer}}",
        "prompt": "基于以下品牌事实，生成一个FAQ条目...",
    },
    "Q&A": {
        "structure": "## 场景：{{scenario}}\n## 推荐方案：{{solution}}",
        "prompt": "基于品牌场景，生成Q&A内容...",
    },
    "Comparison": {
        "structure": "| 维度 | {{brand}} | {{competitor}} |\n|---|---|---|",
        "prompt": "基于品牌差异化优势，生成对比表格...",
    },
    "Tutorial": {
        "structure": "## 行业指南：{{topic}}\n\n{{body}}",
        "prompt": "基于品牌所在行业，生成教程内容...",
    },
    "Case": {
        "structure": "## 案例：{{title}}\n## 背景\n## 方案\n## 结果",
        "prompt": "基于品牌场景，生成案例内容...",
    },
    "Schema": {
        "structure": '<script type="application/ld+json">{{json}}</script>',
        "prompt": "生成Organization和FAQ的JSON-LD Schema...",
    },
}

QUALITY_CHECKLIST = [
    "内容是否基于真实产品能力？",
    "对比是否有客观依据？",
    "案例是否可追溯验证？",
    "是否包含虚假或夸大声明？",
    "Schema是否与页面内容一致？",
    "是否为低质量重复内容？",
]

def generate_content_brief(action_plan, brand, ground_truth_json):
    """Generate a content brief from an action plan - returns structured outline for human review."""
    ct = CONTENT_TEMPLATES.get(action_plan.suggested_content_type, CONTENT_TEMPLATES["FAQ"])
    return {
        "title": f"[{action_plan.priority}] {action_plan.trigger_type}",
        "type": action_plan.suggested_content_type,
        "structure": ct["structure"],
        "brand_facts": ground_truth_json,
        "action_context": {
            "trigger": action_plan.trigger_type,
            "wrong_claims": action_plan.ai_wrong_claims,
            "correct_truth": action_plan.correct_ground_truth,
        },
        "quality_checklist": QUALITY_CHECKLIST,
        "acceptance_criteria": action_plan.acceptance_criteria,
    }
```

- [ ] **Step 2: Test, commit**

---

### Task 17: API — auth and deps

**Files:**
- Create: `src/api/__init__.py`, `src/api/deps.py`, `src/api/auth.py`

- [ ] **Step 1: Dependencies (get_db, get_current_user)**

```python
# src/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
from src.database import get_db
from src.config import settings
from src.models.user import User

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    from sqlalchemy import select
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

- [ ] **Step 2: Auth routes (login, register)**

```python
# src/api/auth.py
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.config import settings
from src.models.user import User
from src.models.organization import Organization

router = APIRouter(prefix="/api/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str
    organization_name: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=settings.jwt_algorithm)

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    org = Organization(name=req.organization_name)
    db.add(org)
    await db.flush()
    user = User(organization_id=org.id, email=req.email, name=req.name,
                role="admin", password_hash=pwd_context.hash(req.password))
    db.add(user)
    await db.commit()
    return TokenResponse(access_token=create_token(str(user.id)))

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == req.email))).scalar_one_or_none()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_token(str(user.id)))
```

- [ ] **Step 3: Test, commit**

---

### Task 18: API — brands and queries routes

**Files:**
- Create: `src/api/brands.py`, `src/api/queries.py`

- [ ] **Step 1: Brand CRUD routes**

```python
# src/api/brands.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

router = APIRouter(prefix="/api/brands", tags=["brands"])

class BrandCreate(BaseModel):
    name: str
    aliases: list[str] = []
    industry: str = ""
    ground_truth: dict = {}

@router.get("")
async def list_brands(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    brands = (await db.execute(
        select(Brand).where(Brand.organization_id == user.organization_id)
    )).scalars().all()
    return [{"id": str(b.id), "name": b.name, "industry": b.industry, "aliases": b.aliases} for b in brands]

@router.post("")
async def create_brand(req: BrandCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    brand = Brand(organization_id=user.organization_id, name=req.name,
                  aliases=req.aliases, industry=req.industry)
    db.add(brand)
    await db.flush()
    if req.ground_truth:
        gt = GroundTruthVersion(brand_id=brand.id, version=1, ground_truth_json=req.ground_truth, status="active")
        db.add(gt)
        brand.ground_truth_version_id = gt.id
    await db.commit()
    return {"id": str(brand.id), "name": brand.name}

@router.get("/{brand_id}")
async def get_brand(brand_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    brand = (await db.execute(
        select(Brand).where(Brand.id == brand_id, Brand.organization_id == user.organization_id)
    )).scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    gt = None
    if brand.ground_truth_version_id:
        gt = (await db.execute(
            select(GroundTruthVersion).where(GroundTruthVersion.id == brand.ground_truth_version_id)
        )).scalar_one_or_none()
    return {"id": str(brand.id), "name": brand.name, "aliases": brand.aliases,
            "industry": brand.industry, "ground_truth": gt.ground_truth_json if gt else {}}

@router.put("/{brand_id}")
async def update_brand(brand_id: uuid.UUID, req: BrandCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    brand = (await db.execute(
        select(Brand).where(Brand.id == brand_id, Brand.organization_id == user.organization_id)
    )).scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404)
    brand.name = req.name
    brand.aliases = req.aliases
    brand.industry = req.industry
    if req.ground_truth:
        gt = GroundTruthVersion(brand_id=brand.id, version=1, ground_truth_json=req.ground_truth, status="active")
        db.add(gt)
        await db.flush()
        brand.ground_truth_version_id = gt.id
    await db.commit()
    return {"id": str(brand.id), "status": "updated"}

@router.post("/{brand_id}/collect")
async def trigger_collection(brand_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from src.collector.tasks import collect_brand_task
    task = collect_brand_task.delay(str(brand_id), str(user.organization_id))
    return {"task_id": task.id, "brand_id": str(brand_id)}
```

- [ ] **Step 2: Query result routes**

```python
# src/api/queries.py
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.query_result import QueryResult

router = APIRouter(prefix="/api", tags=["queries"])

@router.get("/brands/{brand_id}/queries")
async def list_queries(brand_id: uuid.UUID, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db), page: int = Query(1, ge=1),
                        platform: str | None = None, status: str | None = None):
    base_q = select(QueryResult).where(QueryResult.brand_id == brand_id)
    if platform:
        base_q = base_q.where(QueryResult.platform == platform)
    if status:
        base_q = base_q.where(QueryResult.status == status)
    total = (await db.execute(select(func.count()).select_from(base_q.subquery()))).scalar()
    results = (await db.execute(base_q.order_by(QueryResult.collected_at.desc()).offset((page-1)*20).limit(20))).scalars().all()
    return {"total": total, "page": page, "items": [
        {"id": str(r.id), "platform": r.platform, "question": r.question[:100],
         "status": r.status, "latency_ms": r.latency_ms, "collected_at": r.collected_at.isoformat()} for r in results
    ]}

@router.get("/queries/{query_id}")
async def get_query(query_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    qr = (await db.execute(select(QueryResult).where(QueryResult.id == query_id))).scalar_one_or_none()
    if not qr:
        raise HTTPException(status_code=404)
    return {"id": str(qr.id), "platform": qr.platform, "question": qr.question,
            "answer_text": qr.answer_text, "citations": qr.citations, "model_name": qr.model_name,
            "status": qr.status, "error_message": qr.error_message, "latency_ms": qr.latency_ms,
            "collected_at": qr.collected_at.isoformat()}
```

- [ ] **Step 3: Test, commit**

---

### Task 19: API — metrics, hallucinations, actions, content, dashboard routes

**Files:**
- Create: `src/api/metrics.py`, `src/api/hallucinations.py`, `src/api/actions.py`, `src/api/content.py`, `src/api/dashboard.py`

- [ ] **Step 1: Metrics routes**

```python
# src/api/metrics.py
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.analyzer.sov import compute_sov
from src.analyzer.first_rec import compute_first_rec
from src.analyzer.accuracy import compute_accuracy
from src.analyzer.completeness import compute_completeness
from src.analyzer.citation import compute_citation_rate

router = APIRouter(prefix="/api/brands/{brand_id}/metrics", tags=["metrics"])

@router.get("")
async def get_metrics(brand_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    org_id = str(user.organization_id)
    bid = str(brand_id)
    sov, frr, acc, comp, cit = await asyncio.gather(
        compute_sov(bid, org_id, db), compute_first_rec(bid, org_id, db),
        compute_accuracy(bid, org_id, db), compute_completeness(bid, org_id, db),
        compute_citation_rate(bid, org_id, db),
    )
    return {"brand_id": bid, "sov": sov, "first_rec_rate": frr, "accuracy_rate": acc,
            "completeness_rate": comp, "citation_rate": cit}
```

- [ ] **Step 2: Hallucination routes**

```python
# src/api/hallucinations.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.hallucination import HallucinationResult

router = APIRouter(prefix="/api", tags=["hallucinations"])

class ReviewRequest(BaseModel):
    verdict: str  # correct | wrong | uncertain
    notes: str = ""

@router.get("/brands/{brand_id}/hallucinations")
async def list_hallucinations(brand_id, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                                severity: str | None = None, human_reviewed: bool | None = None):
    q = select(HallucinationResult).where(HallucinationResult.brand_id == brand_id)
    if severity: q = q.where(HallucinationResult.severity == severity)
    if human_reviewed is not None: q = q.where(HallucinationResult.human_reviewed == human_reviewed)
    results = (await db.execute(q.order_by(HallucinationResult.detected_at.desc()).limit(50))).scalars().all()
    return [{"id": str(r.id), "field_name": r.field_name, "severity": r.severity,
             "verdict": r.verdict, "ai_claim": r.ai_claim, "ground_truth": r.ground_truth_value,
             "human_reviewed": r.human_reviewed} for r in results]

@router.post("/hallucinations/{id}/review")
async def review_hallucination(id, req: ReviewRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = (await db.execute(select(HallucinationResult).where(HallucinationResult.id == id))).scalar_one_or_none()
    if not result: raise HTTPException(status_code=404)
    result.human_verdict = req.verdict
    result.human_reviewed = True
    result.reviewer_id = user.id
    await db.commit()
    return {"status": "reviewed"}
```

- [ ] **Step 3: Action Plan routes**

```python
# src/api/actions.py
@router.get("/brands/{brand_id}/actions")
# List with filters: status, priority. Returns action_plans with owner name.
@router.put("/actions/{id}")
# Update: status, owner_id, due_date, notes
@router.post("/brands/{brand_id}/actions/generate")
# Calls src.actions.engine.generate_action_plans() and returns count
```

- [ ] **Step 4: Content Library routes**

```python
# src/api/content.py
@router.get("/brands/{brand_id}/content")
# List content items by type/status
@router.post("/actions/{id}/brief")
# Calls src.actions.content_factory.generate_content_brief() for an action plan
@router.post("/content")
# Create new content item
@router.put("/content/{id}")
# Update status, body, quality_check
```

- [ ] **Step 5: Dashboard route**

```python
# src/api/dashboard.py
@router.get("/api/dashboard")
# Aggregated org-level stats: total brands, latest metrics avg, pending actions, recent errors
```

- [ ] **Step 6: Register all routers in src/main.py**

```python
from src.api import auth, brands, queries, metrics, hallucinations, actions, content, dashboard
app.include_router(auth.router)
app.include_router(brands.router)
app.include_router(queries.router)
app.include_router(metrics.router)
app.include_router(hallucinations.router)
app.include_router(actions.router)
app.include_router(content.router)
app.include_router(dashboard.router)
```

- [ ] **Step 7: Test all endpoints with pytest + httpx AsyncClient, commit**

---

### Task 20: Frontend — base template and dashboard pages

**Files:**
- Create: `src/templates/base.html`, `src/templates/dashboard/index.html`

- [ ] **Step 1: Base template with Jinja2 + HTMX**

```html
<!-- src/templates/base.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEO Explorer - 品牌AI可见度</title>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link href="/static/css/app.css" rel="stylesheet">
</head>
<body>
    <nav><!-- sidebar navigation --></nav>
    <main id="main-content">{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 2: Dashboard index page with 5 metric cards, recent hallucinations, pending actions**

- [ ] **Step 3: Wire up FastAPI to serve templates**

```python
# Add to src/main.py:
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")
```

- [ ] **Step 4: Test page renders, commit**

---

### Task 21: Frontend — brand detail and query detail pages

**Files:**
- Create: `src/templates/brands/detail.html`, `src/templates/queries/detail.html`, `src/templates/queries/list.html`

- [ ] **Step 1: Brand detail page — GT display, metrics trend chart, platform radar**

- [ ] **Step 2: Query list — sortable table, platform filter, status badges**

- [ ] **Step 3: Query detail — full AI response, citation list, hallucination highlights**

- [ ] **Step 4: Commit**

---

### Task 22: Frontend — hallucinations, competitors, actions, content pages

**Files:**
- Create: `src/templates/hallucinations/`, `src/templates/competitors/`, `src/templates/actions/`, `src/templates/content/`

- [ ] **Step 1: Hallucination report page — severity distribution, AI claim vs GT comparison, review button**

- [ ] **Step 2: Competitor matrix page — table with per-metric comparison**

- [ ] **Step 3: Action Plan page — task board (Kanban columns: pending/in_progress/completed)**

- [ ] **Step 4: Content Library page — content by type, quality check status, metric impact**

- [ ] **Step 5: Commit**

---

### Task 23: Seed data — default question templates and prompt

**Files:**
- Create: `src/seed.py`

- [ ] **Step 1: Seed 22 default question templates across 5 dimensions**

- [ ] **Step 2: Seed default prompt version (system prompt)**

- [ ] **Step 3: Seed default organization for internal use**

- [ ] **Step 4: Run seed, commit**

---

### Task 24: Integration test — end-to-end collection and analysis pipeline

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Create brand with GT → run collection with mock adapters → compute all 5 metrics → generate hallucinations → create action plans → generate content briefs → verify full pipeline**

- [ ] **Step 2: Fix any integration issues**

- [ ] **Step 3: Commit**

---

### Task 25: Final assembly — register routers, polish, verify

- [ ] **Step 1: Verify all routers registered in main.py**

- [ ] **Step 2: `docker compose build && docker compose up -d`**

- [ ] **Step 3: Hit /health, verify 200**

- [ ] **Step 4: Manual smoke test: create brand, seed templates, trigger collection (mock), view dashboard**

- [ ] **Step 5: Run full test suite: `python -m pytest tests/ -v`**

- [ ] **Step 6: Commit**

---

### Task 26: .gitignore and final cleanup

- [ ] **Step 1: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
*.egg-info/
.pytest_cache/
.codegraph/
pgdata/
```

- [ ] **Step 2: Commit all remaining files**
