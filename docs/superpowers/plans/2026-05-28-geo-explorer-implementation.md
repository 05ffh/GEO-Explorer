# GEO Explorer Implementation Plan V2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build GEO Explorer — brand AI visibility monitoring and optimization platform with 4 AI platform adapters, 22 question templates, 5 KPI computation, hallucination detection, executable action plans, content brief factory, and 7-page dashboard.

**Architecture:** 8-phase pipeline: Foundation → Models → Seed → Adapters → Collector → Analyzer → Actions → API+Dashboard. Each phase builds on the previous. Collector uses bounded concurrency. Analyzer uses 3-tier accuracy verification. Hallucination detector uses 2-stage claim extraction+verification. All data linked via CollectionRun for full lineage.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, Celery, Redis, PostgreSQL 16 (dev + test), Jinja2, HTMX, Docker Compose, pytest + pytest-asyncio.

---

## Phase 1: Foundation & Database Stability

### Task 1.1: Project scaffolding

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
email-validator==2.2.0
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
DATABASE_URL=postgresql+asyncpg://geo:geo@localhost:5432/geo_explorer
TEST_DATABASE_URL=postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test

# Redis
REDIS_URL=redis://localhost:6379/0

# AI Platforms
DEEPSEEK_API_KEY=sk-your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

KIMI_API_KEY=sk-your-key
KIMI_BASE_URL=https://api.moonshot.cn/v1
KIMI_MODEL=kimi-k2.5

DOUBAO_API_KEY=your-key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=doubao-seed-2-0-lite-260215

WENXIN_API_KEY=your-key
WENXIN_SECRET_KEY=your-secret
WENXIN_BASE_URL=https://aip.baidubce.com
WENXIN_MODEL=ernie-4.0-turbo-128k

# Collector
COLLECTOR_CONCURRENCY=4
COLLECTOR_TIMEOUT=30
COLLECTOR_MAX_RETRIES=2
```

- [ ] **Step 3: Create src/config.py**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://geo:geo@localhost:5432/geo_explorer"
    test_database_url: str = "postgresql+asyncpg://geo_test:geo_test@localhost:5433/geo_explorer_test"
    redis_url: str = "redis://localhost:6379/0"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "kimi-k2.5"

    doubao_api_key: str = ""
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_model: str = "doubao-seed-2-0-lite-260215"

    wenxin_api_key: str = ""
    wenxin_secret_key: str = ""
    wenxin_base_url: str = "https://aip.baidubce.com"
    wenxin_model: str = "ernie-4.0-turbo-128k"

    collector_concurrency: int = 4
    collector_timeout: int = 30
    collector_max_retries: int = 2

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
COPY alembic.ini ./
COPY alembic/ ./alembic/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 7: Create docker-compose.yml with test_db service**

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

  test_db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: geo_test
      POSTGRES_PASSWORD: geo_test
      POSTGRES_DB: geo_explorer_test
    ports: ["5433:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

volumes:
  pgdata:
```

- [ ] **Step 8: Verify health check**

Run: `cd "/home/ffh/explore geo" && pip install fastapi uvicorn && python -c "from src.main import app; print('OK')"`

- [ ] **Step 9: Create .gitignore**

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

- [ ] **Step 10: Commit**

---

### Task 1.2: PostgreSQL test database setup

**Files:**
- Modify: `docker-compose.yml` (already includes test_db)
- Create: `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create tests/conftest.py with PostgreSQL test DB**

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.config import settings
from src.models.base import Base

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(settings.test_database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

- [ ] **Step 2: Start test_db and verify connectivity**

Run:
```bash
docker compose up -d test_db
python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('postgresql://geo_test:geo_test@localhost:5433/geo_explorer_test'))"
```

- [ ] **Step 3: Commit**

---

### Task 1.3: Alembic migration setup

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`

- [ ] **Step 1: Initialize Alembic**

Run:
```bash
cd "/home/ffh/explore geo" && pip install alembic && alembic init alembic
```

- [ ] **Step 2: Configure alembic/env.py**

```python
from alembic import context
from sqlalchemy import engine_from_config, pool
from src.config import settings
from src.models.base import Base

target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        {"sqlalchemy.url": settings.database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Verify init works (migration will be empty until models exist)**

Run:
```bash
docker compose up -d db
alembic upgrade head
```
Expected: "INFO [alembic.runtime.migration] Running upgrade -> None"

- [ ] **Step 4: Commit**

---

## Phase 2: Core Data Models

### Task 2.1: Base, Organization, User models

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

- [ ] **Step 4: Write model test**

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

- [ ] **Step 5: Run tests and commit**

Run: `docker compose up -d test_db && python -m pytest tests/test_models.py -v`
Expected: 2 PASS

---

### Task 2.2: Brand and GroundTruthVersion models (no circular FK)

**Files:**
- Create: `src/models/brand.py`, `src/models/ground_truth.py`

- [ ] **Step 1: Create Brand model (without ground_truth_version_id)**

```python
# src/models/brand.py
import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class Brand(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "brands"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list] = mapped_column(ARRAY(String), default=list)
    industry: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
```

> **Design note:** `ground_truth_version_id` is removed. Instead, the active Ground Truth is queried via `GroundTruthVersion.brand_id` + `status == "active"`. This avoids the circular foreign key between brands ↔ ground_truth_versions.

- [ ] **Step 2: Create GroundTruthVersion model**

```python
# src/models/ground_truth.py
import uuid
from sqlalchemy import String, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class GroundTruthVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ground_truth_versions"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    ground_truth_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_urls: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    reviewer: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")

# Ground Truth JSON schema (14 fields):
# {
#   "official_name": str,       # P0
#   "aliases": [str],           # P0
#   "industry": str,            # P0
#   "category": str,            # P0
#   "positioning": str,         # P0
#   "target_users": str,        # P1
#   "core_scenarios": [str],    # P1
#   "differentiators": [str],   # P1
#   "tech_tags": [str],         # P2
#   "market_position": str,     # P2
#   "official_domains": [str],  # P0
#   "trusted_sources": [str],   # P1
#   "forbidden_claims": [str],  # P1
#   "competitors": [str],       # P0
# }
```

- [ ] **Step 3: Test — create Brand then GroundTruthVersion independently**

```python
@pytest.mark.asyncio
async def test_brand_and_gt_no_circular_fk(db_session):
    org = Organization(name="TC")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.commit()
    assert brand.id is not None

    gt = GroundTruthVersion(
        brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech",
                           "positioning": "Test tool", "official_domains": ["test.com"]},
        status="active"
    )
    db_session.add(gt)
    await db_session.commit()
    assert gt.id is not None
```

- [ ] **Step 4: Run tests and commit**

---

### Task 2.3: QueryTemplate, PromptVersion models

**Files:**
- Create: `src/models/query_template.py`, `src/models/prompt_version.py`

- [ ] **Step 1: Create QueryTemplate model**

```python
# src/models/query_template.py
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

- [ ] **Step 2: Create PromptVersion model**

```python
# src/models/prompt_version.py
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

- [ ] **Step 3: Test, commit**

---

### Task 2.4: CollectionRun model [P0 — New]

**Files:**
- Create: `src/models/collection_run.py`

- [ ] **Step 1: Create CollectionRun model**

```python
# src/models/collection_run.py
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class CollectionRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "collection_runs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    ground_truth_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ground_truth_versions.id"), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual | scheduled
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending | running | completed | partial | failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_queries: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
```

- [ ] **Step 2: Test, commit**

---

### Task 2.5: QueryResult, ApiUsage models

**Files:**
- Create: `src/models/query_result.py`, `src/models/api_usage.py`

- [ ] **Step 1: Create QueryResult with collection_run_id**

```python
# src/models/query_result.py
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, UUIDMixin

class QueryResult(Base, UUIDMixin):
    __tablename__ = "query_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False, index=True)
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

- [ ] **Step 2: Create ApiUsage model**

```python
# src/models/api_usage.py
import uuid
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

class ApiUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_usage_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    status: Mapped[str] = mapped_column(String(50), default="success")
```

- [ ] **Step 3: Test data lineage — CollectionRun → QueryResult → ApiUsage**

- [ ] **Step 4: Commit**

---

### Task 2.6: MetricsSnapshot, Hallucination, ActionPlan, ContentLibrary, CompetitorSet models

**Files:**
- Create: `src/models/metrics_snapshot.py`, `src/models/hallucination.py`, `src/models/action_plan.py`, `src/models/content_library.py`, `src/models/competitor_set.py`

- [ ] **Step 1: MetricsSnapshot with collection_run_id**

```python
# src/models/metrics_snapshot.py
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
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
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

- [ ] **Step 2: Hallucination model**

```python
# src/models/hallucination.py
# Same as V1 spec — includes field_name, field_level, severity, verdict, ai_claim,
# ground_truth_value, human_reviewed, human_verdict, reviewer_id, reviewed_at
```

- [ ] **Step 3: ActionPlan model with state machine fields**

```python
# src/models/action_plan.py
VALID_TRANSITIONS = {
    "pending": ["in_progress", "cancelled"],
    "in_progress": ["completed", "cancelled"],
    "completed": ["verified", "reopened"],
    "verified": [],
    "cancelled": [],
    "reopened": ["in_progress"],
}
# status: pending | in_progress | completed | verified | cancelled | reopened
```

- [ ] **Step 4: ContentLibrary model (content brief, not auto-publish)**

```python
# src/models/content_library.py
# Fields: brand_id, organization_id, action_plan_id, content_type, title,
# brief_json (problem_evidence, correct_facts, required_sections, forbidden_claims,
# acceptance_criteria, quality_checklist), status: draft | review | published
```

- [ ] **Step 5: CompetitorSet model**

```python
# src/models/competitor_set.py
# Fields: brand_id, organization_id, name, competitor_brand_ids, source_type,
# version, is_active. source_type: manual | auto_discovered | system_recommended
```

- [ ] **Step 6: Test, commit**

---

### Task 2.7: Generate initial Alembic migration

- [ ] **Step 1: Generate migration**

```bash
alembic revision --autogenerate -m "init all models"
```

- [ ] **Step 2: Run migration on dev DB**

```bash
docker compose up -d db
alembic upgrade head
```

- [ ] **Step 3: Verify all tables exist**

```bash
docker compose exec db psql -U geo -d geo_explorer -c "\dt"
```
Expected: organizations, users, brands, ground_truth_versions, query_templates, prompt_versions, collection_runs, query_results, api_usage_logs, metrics_snapshots, hallucination_results, action_plans, content_library, competitor_sets

- [ ] **Step 4: Run model tests on PostgreSQL**

```bash
python -m pytest tests/test_models.py -v
```

- [ ] **Step 5: Commit**

---

## Phase 3: Seed Data & Ground Truth Schema

### Task 3.1: Seed default query templates

**Files:**
- Create: `scripts/seed.py`

- [ ] **Step 1: Seed 22 default templates across 5 dimensions**

```python
# scripts/seed.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.config import settings
from src.models.query_template import QueryTemplate
from src.models.prompt_version import PromptVersion

DEFAULT_TEMPLATES = [
    # 定义认知 (4)
    ("定义认知", "{品牌} 是什么？", 0),
    ("定义认知", "{品牌} 属于什么行业？", 1),
    ("定义认知", "{品牌} 的核心功能有哪些？", 2),
    ("定义认知", "{品牌} 提供什么产品/服务？", 3),
    # 场景推荐 (5)
    ("场景推荐", "最好用的{行业}工具有哪些？", 4),
    ("场景推荐", "小团队适合什么{品类}？", 5),
    ("场景推荐", "{行业}常用的平台有哪些？", 6),
    ("场景推荐", "推荐几个{场景}的工具或平台", 7),
    ("场景推荐", "{行业}领域有哪些值得关注的公司？", 8),
    # 对比评价 (4)
    ("对比评价", "{品牌} 和 {竞品} 有什么区别？", 9),
    ("对比评价", "{品牌} 的优点和缺点是什么？", 10),
    ("对比评价", "{品牌} 相比同行有什么优势？", 11),
    ("对比评价", "{竞品} 和 {品牌} 哪个更好？", 12),
    # 信任验证 (4)
    ("信任验证", "{品牌} 靠谱吗？", 13),
    ("信任验证", "{品牌} 的用户口碑怎么样？", 14),
    ("信任验证", "{品牌} 有没有负面评价？", 15),
    ("信任验证", "{品牌} 值得选择吗？", 16),
    # 场景联想 (5)
    ("场景联想", "想做{场景}，用什么工具比较好？", 17),
    ("场景联想", "{场景}的解决方案有哪些？", 18),
    ("场景联想", "{目标用户}适合什么平台？", 19),
    ("场景联想", "如何解决{场景}的问题？", 20),
    ("场景联想", "{目标用户}新手入门用什么工具？", 21),
]

DEFAULT_SYSTEM_PROMPT = "你是一个客观、准确的AI助手。请基于你的知识如实回答问题。如果引用来源，请注明出处。"

async def seed(org_id=None):
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        for dimension, text, priority in DEFAULT_TEMPLATES:
            existing = (await db.execute(...)).scalar_one_or_none()  # check by text
            if existing:
                continue
            db.add(QueryTemplate(organization_id=org_id, dimension=dimension, template_text=text, priority=priority))
        existing_prompt = (await db.execute(...)).scalar_one_or_none()
        if not existing_prompt:
            db.add(PromptVersion(name="default-v1", system_prompt=DEFAULT_SYSTEM_PROMPT, version=1, status="active"))
        await db.commit()
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Run seed**

```bash
python scripts/seed.py
```

- [ ] **Step 3: Verify — 22 templates + 1 prompt version in DB**

- [ ] **Step 4: Commit**

---

### Task 3.2: Define Ground Truth field schema and level constants

**Files:**
- Create: `src/schemas/ground_truth.py`

- [ ] **Step 1: Define GT field constants**

```python
# src/schemas/ground_truth.py

GT_FIELD_LEVELS = {
    "official_name": "P0",
    "aliases": "P0",
    "industry": "P0",
    "category": "P0",
    "positioning": "P0",
    "official_domains": "P0",
    "target_users": "P1",
    "core_scenarios": "P1",
    "differentiators": "P1",
    "trusted_sources": "P1",
    "forbidden_claims": "P1",
    "tech_tags": "P2",
    "market_position": "P2",
}

GT_LIST_FIELDS = {"aliases", "core_scenarios", "differentiators", "tech_tags", "trusted_sources", "forbidden_claims", "official_domains", "competitors"}

GT_REQUIRED_FOR_COMPLETENESS = {k for k in GT_FIELD_LEVELS if k != "forbidden_claims"}
```

- [ ] **Step 2: Commit**

---

## Phase 4: Platform Adapters

### Task 4.1: Base adapter and OpenAICompatibleAdapter

**Files:**
- Create: `src/adapters/__init__.py`, `src/adapters/base.py`

- [ ] **Step 1: Create base adapter types**

```python
# src/adapters/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class Citation:
    url: str
    type: str       # official | third_party | wiki
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

- [ ] **Step 2: Create OpenAICompatibleAdapter**

```python
# src/adapters/base.py (continued)
import time
import re
from openai import AsyncOpenAI

class OpenAICompatibleAdapter(PlatformAdapter):
    platform_name: str = ""
    base_url: str = ""
    default_model: str = ""
    api_key: str = ""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", self.default_model)
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            latency = int((time.time() - start) * 1000)
            answer = response.choices[0].message.content or ""
            return AIResponse(
                platform=self.platform_name,
                question=prompt,
                answer_text=answer,
                citations=await self.extract_citations(answer),
                model_name=model,
                model_version=response.model or "",
                raw_response=response.model_dump(),
                latency_ms=latency,
            )
        except Exception as e:
            return AIResponse(platform=self.platform_name, question=prompt, answer_text="",
                              model_name=model, latency_ms=int((time.time() - start) * 1000), error=str(e))

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】一-鿿]+', response):
            url = match.group()
            ctx_start = max(0, match.start() - 50)
            ctx_end = min(len(response), match.end() + 50)
            ctx = response[ctx_start:ctx_end]
            ctype = "third_party"  # Default; subclasses can override with domain check
            citations.append(Citation(url=url, type=ctype, context=ctx))
        return citations
```

- [ ] **Step 3: Commit**

---

### Task 4.2: DeepSeek, Kimi adapters

**Files:**
- Create: `src/adapters/deepseek.py`, `src/adapters/kimi.py`

- [ ] **Step 1: DeepSeek adapter**

```python
# src/adapters/deepseek.py
from src.adapters.base import OpenAICompatibleAdapter
from src.config import settings

class DeepSeekAdapter(OpenAICompatibleAdapter):
    platform_name = "deepseek"
    base_url = settings.deepseek_base_url
    default_model = settings.deepseek_model
    api_key = settings.deepseek_api_key
```

- [ ] **Step 2: Kimi adapter (NOT inheriting DeepSeek)**

```python
# src/adapters/kimi.py
from src.adapters.base import OpenAICompatibleAdapter
from src.config import settings

class KimiAdapter(OpenAICompatibleAdapter):
    platform_name = "kimi"
    base_url = settings.kimi_base_url
    default_model = settings.kimi_model
    api_key = settings.kimi_api_key
```

- [ ] **Step 3: Write test verifying correct platform names**

```python
@pytest.mark.asyncio
async def test_deepseek_platform_name():
    adapter = DeepSeekAdapter()
    assert adapter.platform_name == "deepseek"

@pytest.mark.asyncio
async def test_kimi_platform_name():
    adapter = KimiAdapter()
    assert adapter.platform_name == "kimi"

@pytest.mark.asyncio
async def test_deepseek_query_returns_correct_platform():
    adapter = DeepSeekAdapter()
    result = AIResponse(platform=adapter.platform_name, question="test", answer_text="ok")
    assert result.platform == "deepseek"
```

- [ ] **Step 4: Run tests and commit**

---

### Task 4.3: Doubao adapter

**Files:**
- Create: `src/adapters/doubao.py`

- [ ] **Step 1: Create Doubao adapter**

```python
# src/adapters/doubao.py
import time
import re
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings

class DoubaoAdapter(PlatformAdapter):
    platform_name = "doubao"

    def __init__(self):
        try:
            from volcenginesdkarkruntime import Ark
            self.client = Ark(base_url=settings.doubao_base_url, api_key=settings.doubao_api_key)
        except ImportError:
            self.client = None

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", settings.doubao_model)
        if self.client is None:
            return AIResponse(platform=self.platform_name, question=prompt, answer_text="",
                              model_name=model, error="volcenginesdkarkruntime not installed")
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=kwargs.get("temperature", 0.3),
                max_tokens=kwargs.get("max_tokens", 2048),
            )
            latency = int((time.time() - start) * 1000)
            answer = response.choices[0].message.content or ""
            return AIResponse(
                platform=self.platform_name, question=prompt, answer_text=answer,
                citations=await self.extract_citations(answer),
                model_name=model, latency_ms=latency,
                raw_response={"model": model, "choices": [{"message": {"content": answer}}]},
            )
        except Exception as e:
            return AIResponse(platform=self.platform_name, question=prompt, answer_text="",
                              model_name=model, latency_ms=int((time.time() - start) * 1000), error=str(e))

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】一-鿿]+', response):
            url = match.group()
            ctx = response[max(0, match.start()-50):min(len(response), match.end()+50)]
            citations.append(Citation(url=url, type="third_party", context=ctx))
        return citations
```

- [ ] **Step 2: Test, commit**

---

### Task 4.4: Wenxin adapter

**Files:**
- Create: `src/adapters/wenxin.py`

- [ ] **Step 1: Create Wenxin adapter with OAuth token caching**

```python
# src/adapters/wenxin.py
import time
import re
import httpx
from src.adapters.base import PlatformAdapter, AIResponse, Citation
from src.config import settings

class WenxinAdapter(PlatformAdapter):
    platform_name = "wenxin"

    def __init__(self):
        self.api_key = settings.wenxin_api_key
        self.secret_key = settings.wenxin_secret_key
        self._access_token = None
        self._token_expiry = 0

    async def _get_access_token(self) -> str:
        now = time.time()
        if self._access_token and now < self._token_expiry:
            return self._access_token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.wenxin_base_url}/oauth/2.0/token",
                params={"grant_type": "client_credentials", "client_id": self.api_key, "client_secret": self.secret_key},
            )
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = now + data.get("expires_in", 2592000) - 300
            return self._access_token

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        start = time.time()
        model = kwargs.get("model", settings.wenxin_model)
        try:
            token = await self._get_access_token()
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.wenxin_base_url}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro?access_token={token}",
                    json={
                        "messages": [
                            {"role": "system", "content": system_prompt or "你是一个诚实的AI助手。"},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": kwargs.get("temperature", 0.3),
                        "max_output_tokens": kwargs.get("max_tokens", 2048),
                    },
                    timeout=settings.collector_timeout,
                )
                data = resp.json()
                latency = int((time.time() - start) * 1000)
                answer = data.get("result", "")
                return AIResponse(
                    platform=self.platform_name, question=prompt, answer_text=answer,
                    citations=await self.extract_citations(answer),
                    model_name=model, raw_response=data, latency_ms=latency,
                )
        except Exception as e:
            return AIResponse(platform=self.platform_name, question=prompt, answer_text="",
                              model_name=model, latency_ms=int((time.time() - start) * 1000), error=str(e))

    async def extract_citations(self, response: str) -> list[Citation]:
        citations = []
        for match in re.finditer(r'https?://[^\s\)\]】一-鿿]+', response):
            url = match.group()
            ctx = response[max(0, match.start()-50):min(len(response), match.end()+50)]
            citations.append(Citation(url=url, type="third_party", context=ctx))
        return citations
```

- [ ] **Step 2: Test, commit**

---

### Task 4.5: MockAdapter for testing without API keys

**Files:**
- Create: `src/adapters/mock.py`

- [ ] **Step 1: Create MockAdapter**

```python
# src/adapters/mock.py
from src.adapters.base import PlatformAdapter, AIResponse, Citation

# Sample mock responses keyed by platform
MOCK_RESPONSES = {
    "deepseek": "TestBrand 是一家专注于旅游行业的科技公司，主要提供飞猪业务自动化解决方案。",
    "kimi": "TestBrand（象往科技）是国内旅游SaaS领域的新兴工具，核心功能包括订单管理和数据采集。",
    "doubao": "TestBrand 面向飞猪商家，提供一站式数据整合服务。",
    "wenxin": "根据我的了解，TestBrand 是一个旅游科技平台，目前主要服务于中国市场的飞猪生态。",
}

class MockAdapter(PlatformAdapter):
    def __init__(self, platform_name: str = "mock"):
        self.platform_name = platform_name

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        answer = MOCK_RESPONSES.get(self.platform_name, f"Mock response about TestBrand for prompt: {prompt[:50]}")
        return AIResponse(
            platform=self.platform_name,
            question=prompt,
            answer_text=answer,
            citations=await self.extract_citations(answer),
            model_name=f"mock-{self.platform_name}-v1",
            model_version="mock-v1.0",
            raw_response={"mock": True, "content": answer},
            latency_ms=50,
        )

    async def extract_citations(self, response: str) -> list[Citation]:
        return []
```

- [ ] **Step 2: Test MockAdapter returns correct platform name for each platform**

- [ ] **Step 3: Update src/adapters/__init__.py to export all adapters including mock**

```python
from src.adapters.base import PlatformAdapter, OpenAICompatibleAdapter, AIResponse, Citation
from src.adapters.deepseek import DeepSeekAdapter
from src.adapters.kimi import KimiAdapter
from src.adapters.doubao import DoubaoAdapter
from src.adapters.wenxin import WenxinAdapter
from src.adapters.mock import MockAdapter, MOCK_RESPONSES

ADAPTERS = {"deepseek": DeepSeekAdapter, "kimi": KimiAdapter, "doubao": DoubaoAdapter, "wenxin": WenxinAdapter}

def get_adapter(platform: str) -> PlatformAdapter:
    return ADAPTERS[platform]()
```

- [ ] **Step 4: Commit**

---

## Phase 5: Collector

### Task 5.1: Collector engine with CollectionRun and bounded concurrency

**Files:**
- Create: `src/collector/__init__.py`, `src/collector/engine.py`

- [ ] **Step 1: Create collector engine**

```python
# src/collector/engine.py
import asyncio
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from src.adapters import get_adapter
from src.config import settings
from src.models.brand import Brand
from src.models.query_template import QueryTemplate
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.api_usage import ApiUsage
from src.models.prompt_version import PromptVersion
from src.models.ground_truth import GroundTruthVersion

PLATFORMS = ["deepseek", "kimi", "doubao", "wenxin"]

async def run_collection(brand_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession,
                         trigger_type: str = "manual") -> CollectionRun:
    brand = (await db.execute(select(Brand).where(
        Brand.id == brand_id, Brand.organization_id == org_id
    ))).scalar_one_or_none()
    if not brand:
        raise ValueError("Brand not found")

    templates = (await db.execute(
        select(QueryTemplate).where(
            (QueryTemplate.organization_id == org_id) | (QueryTemplate.organization_id.is_(None)),
            QueryTemplate.is_active == True,
        )
    )).scalars().all()

    active_prompt = (await db.execute(
        select(PromptVersion).where(PromptVersion.status == "active")
    )).scalars().first()

    active_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id, GroundTruthVersion.status == "active"
        )
    )).scalars().first()

    run = CollectionRun(
        organization_id=org_id, brand_id=brand_id,
        prompt_version_id=active_prompt.id if active_prompt else None,
        ground_truth_version_id=active_gt.id if active_gt else None,
        trigger_type=trigger_type, status="running", started_at=datetime.utcnow(),
        total_queries=len(PLATFORMS) * len(templates),
    )
    db.add(run)
    await db.flush()

    sem = asyncio.Semaphore(settings.collector_concurrency)

    async def query_one(platform_name, tmpl):
        async with sem:
            adapter = get_adapter(platform_name)
            question = tmpl.template_text
            for alias in brand.aliases or []:
                question = question.replace(f"{{{alias}}}", alias)
            question = question.replace("{品牌}", brand.name)
            question = question.replace("{行业}", brand.industry)

            system = active_prompt.system_prompt if active_prompt else "你是一个诚实的AI助手。"
            return await adapter.query(question, system_prompt=system), platform_name, tmpl

    jobs = [query_one(p, t) for p in PLATFORMS for t in templates]
    responses = await asyncio.gather(*jobs, return_exceptions=True)

    for result in responses:
        if isinstance(result, Exception):
            continue
        response, platform_name, tmpl = result
        qr = QueryResult(
            brand_id=brand_id, organization_id=org_id,
            collection_run_id=run.id, platform=platform_name,
            template_id=tmpl.id, prompt_version_id=active_prompt.id if active_prompt else None,
            question=response.question, answer_text=response.answer_text,
            citations=[{"url": c.url, "type": c.type, "context": c.context} for c in response.citations],
            model_name=response.model_name, model_version=response.model_version,
            response_raw_json=response.raw_response,
            status="error" if response.error else "success",
            error_message=response.error or "", latency_ms=response.latency_ms,
            collected_at=datetime.utcnow(),
        )
        db.add(qr)
        await db.flush()

        usage = ApiUsage(
            organization_id=org_id, brand_id=brand_id, collection_run_id=run.id,
            platform=platform_name, query_result_id=qr.id,
            prompt_tokens=len(response.question) // 4,
            completion_tokens=len(response.answer_text) // 4 if response.answer_text else 0,
            cost=0, status="failed" if response.error else "success",
        )
        db.add(usage)

    success_count = sum(1 for r in responses if not isinstance(r, Exception) and not r[0].error)
    failure_count = run.total_queries - success_count
    run.success_count = success_count
    run.failure_count = failure_count
    run.status = "completed" if failure_count == 0 else ("failed" if failure_count == run.total_queries else "partial")
    run.completed_at = datetime.utcnow()
    await db.commit()
    return run
```

- [ ] **Step 2: Write test — mock collection with MockAdapter**

```python
@pytest.mark.asyncio
async def test_collection_creates_full_lineage(db_session):
    # Create org, user, brand, GT, templates, prompt
    # Run collection with mock adapters (monkeypatch ADAPTERS with MockAdapter)
    # Verify: 1 CollectionRun, 88 QueryResult (all with collection_run_id), 88 ApiUsage
    # Verify run.success_count + run.failure_count == run.total_queries
```

- [ ] **Step 3: Run tests and commit**

---

### Task 5.2: Celery tasks and scheduler

**Files:**
- Create: `src/celery_app.py`, `src/collector/tasks.py`

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
            "schedule": 604800.0,
        },
    },
    timezone="Asia/Shanghai",
)
```

- [ ] **Step 2: Create Celery tasks**

```python
# src/collector/tasks.py
import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from src.celery_app import app
from src.config import settings
from src.collector.engine import run_collection
from src.models.brand import Brand

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

@app.task
def collect_brand_task(brand_id: str, org_id: str):
    async def _run():
        async with SessionLocal() as db:
            return await run_collection(uuid.UUID(brand_id), uuid.UUID(org_id), db, trigger_type="manual")
    return asyncio.run(_run())

@app.task
def weekly_collect():
    async def _run():
        async with SessionLocal() as db:
            brands = (await db.execute(select(Brand))).scalars().all()
            if not brands:
                return "no brands found"
            org_id = str(brands[0].organization_id)
            for brand in brands:
                await run_collection(brand.id, brand.organization_id, db, trigger_type="scheduled")
            return f"collected {len(brands)} brands"
    return asyncio.run(_run())
```

- [ ] **Step 3: Test Celery task loading**

```bash
celery -A src.collector.tasks inspect registered
```

- [ ] **Step 4: Commit**

---

## Phase 6: Analyzer

### Task 6.1: SOV and First-Recommendation Rate

**Files:**
- Create: `src/analyzer/__init__.py`, `src/analyzer/sov.py`, `src/analyzer/first_rec.py`

- [ ] **Step 1: SOV calculator**

```python
# src/analyzer/sov.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand

async def compute_sov(brand_id: str, collection_run_id: str | None, db: AsyncSession) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    aliases = [brand.name] + (brand.aliases or [])

    q = select(QueryResult).where(QueryResult.brand_id == brand_id, QueryResult.status == "success")
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    failed = len(results) - len(valid)

    mentioned = sum(1 for r in valid if any(a.lower() in r.answer_text.lower() for a in aliases))
    return {
        "sov": round(mentioned / len(valid), 4) if valid else 0.0,
        "mentioned": mentioned,
        "total_valid": len(valid),
        "total_attempted": len(results),
        "sample_size": len(valid),
        "failure_rate": round(failed / len(results), 4) if results else 0.0,
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
    r'(?:首选|最推荐|优先考虑|强烈推荐|最值得|第一名)[^。\n]{0,20}({brand})',
    r'({brand})[^。\n]{0,10}(?:最好|最佳|最合适|首选|推荐)',
]

async def compute_first_rec(brand_id: str, collection_run_id: str | None, db: AsyncSession) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()

    rec_template_ids = (await db.execute(
        select(QueryTemplate.id).where(QueryTemplate.dimension == "场景推荐")
    )).scalars().all()

    q = select(QueryResult).where(
        QueryResult.brand_id == brand_id, QueryResult.status == "success",
        QueryResult.template_id.in_(rec_template_ids),
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]

    first_count = 0
    for r in valid:
        text = r.answer_text
        list_match = re.findall(r'(?:^|\n)\s*(?:\d+[\.\)、]|[-*])\s*([^\n]{0,80})', text)
        if list_match and brand.name in list_match[0]:
            first_count += 1
            continue
        for pattern in FIRST_REC_PATTERNS:
            if re.search(pattern.replace("{brand}", re.escape(brand.name)), text):
                first_count += 1
                break

    return {
        "first_rec_rate": round(first_count / len(valid), 4) if valid else 0.0,
        "first_count": first_count,
        "total_rec_answers": len(valid),
        "sample_size": len(valid),
    }
```

- [ ] **Step 3: Test with mock data, commit**

---

### Task 6.2: Accuracy and Completeness — 3-tier evaluation

**Files:**
- Create: `src/analyzer/accuracy.py`, `src/analyzer/completeness.py`, `src/analyzer/evaluator.py`

- [ ] **Step 1: Create field evaluator with 5 verdicts**

```python
# src/analyzer/evaluator.py
from enum import Enum
from dataclasses import dataclass

class Verdict(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    NOT_MENTIONED = "not_mentioned"

@dataclass
class FieldEvaluation:
    field: str
    verdict: Verdict
    evidence: str          # Quote from AI response
    reason: str            # Why this verdict
    ai_claim: str = ""
    ground_truth_value: str = ""
    coverage_rate: float = 1.0  # For list-type fields

def evaluate_field(field: str, gt_value, ai_text: str) -> FieldEvaluation:
    if gt_value is None or gt_value == "":
        return FieldEvaluation(field=field, verdict=Verdict.NOT_MENTIONED, evidence="", reason="GT field is empty", ground_truth_value="")

    gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)

    # Tier 1: Exact match for scalar fields
    if not isinstance(gt_value, list):
        if gt_str.lower() in ai_text.lower():
            return FieldEvaluation(field=field, verdict=Verdict.CORRECT, evidence=ai_text[:200], reason="Exact match in response", ai_claim=gt_str, ground_truth_value=gt_str)

    # Tier 2: Coverage rate for list fields
    if isinstance(gt_value, list):
        covered = [item for item in gt_value if str(item).lower() in ai_text.lower()]
        rate = len(covered) / len(gt_value) if gt_value else 1.0
        if rate >= 0.8:
            v = Verdict.CORRECT
        elif rate >= 0.4:
            v = Verdict.PARTIAL
        elif rate > 0:
            v = Verdict.PARTIAL
        else:
            v = Verdict.NOT_MENTIONED
        return FieldEvaluation(field=field, verdict=v, evidence=ai_text[:200],
                               reason=f"{len(covered)}/{len(gt_value)} items covered",
                               ai_claim=", ".join(covered), ground_truth_value=", ".join(gt_value),
                               coverage_rate=rate)

    # Tier 3: Fall back to uncertain — human review required
    return FieldEvaluation(field=field, verdict=Verdict.UNCERTAIN, evidence=ai_text[:200],
                           reason="Unable to determine — needs human review",
                           ground_truth_value=gt_str)
```

- [ ] **Step 2: Accuracy calculator using evaluator**

```python
# src/analyzer/accuracy.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.analyzer.evaluator import evaluate_field, Verdict
from src.schemas.ground_truth import GT_FIELD_LEVELS

SCALAR_CHECK_FIELDS = ["industry", "category", "positioning", "target_users", "market_position"]
LIST_CHECK_FIELDS = ["core_scenarios", "differentiators", "tech_tags"]

async def compute_accuracy(brand_id: str, collection_run_id: str | None, db: AsyncSession) -> dict:
    gt = (await db.execute(
        select(GroundTruthVersion).where(GroundTruthVersion.brand_id == brand_id, GroundTruthVersion.status == "active")
    )).scalar_one_or_none()
    if not gt:
        return {"accuracy_rate": 0.0, "mentioned_fields": 0, "correct_fields": 0, "error": "no active ground truth"}

    q = select(QueryResult).where(QueryResult.brand_id == brand_id, QueryResult.status == "success")
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]
    if not valid:
        return {"accuracy_rate": 0.0, "mentioned_fields": 0, "correct_fields": 0, "sample_size": 0}

    all_text = "\n".join(r.answer_text for r in valid)
    gt_json = gt.ground_truth_json

    evaluations = {}
    for field in SCALAR_CHECK_FIELDS + LIST_CHECK_FIELDS:
        if field not in gt_json:
            continue
        ev = evaluate_field(field, gt_json[field], all_text)
        evaluations[field] = ev

    mentioned = [e for e in evaluations.values() if e.verdict != Verdict.NOT_MENTIONED]
    correct = [e for e in mentioned if e.verdict == Verdict.CORRECT]

    return {
        "accuracy_rate": round(len(correct) / len(mentioned), 4) if mentioned else 0.0,
        "mentioned_fields": len(mentioned),
        "correct_fields": len(correct),
        "sample_size": len(valid),
        "details": {k: {"verdict": v.verdict.value, "reason": v.reason, "coverage_rate": v.coverage_rate}
                     for k, v in evaluations.items()},
    }
```

- [ ] **Step 3: Completeness calculator**

```python
# src/analyzer/completeness.py
# Similar pattern but denominator = all GT_REQUIRED_FOR_COMPLETENESS fields
# numerator = fields with verdict CORRECT (not just mentioned)
```

- [ ] **Step 4: Write test with 5 mock AI responses covering correct/incorrect/partial/uncertain/not_mentioned**

- [ ] **Step 5: Commit**

---

### Task 6.3: Citation Rate

**Files:**
- Create: `src/analyzer/citation.py`

```python
# src/analyzer/citation.py
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

async def compute_citation_rate(brand_id: str, collection_run_id: str | None, db: AsyncSession) -> dict:
    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one()
    aliases = [brand.name] + (brand.aliases or [])

    gt = (await db.execute(
        select(GroundTruthVersion).where(GroundTruthVersion.brand_id == brand_id, GroundTruthVersion.status == "active")
    )).scalar_one_or_none()
    domains = gt.ground_truth_json.get("official_domains", []) if gt else []

    q = select(QueryResult).where(QueryResult.brand_id == brand_id, QueryResult.status == "success")
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)

    results = (await db.execute(q)).scalars().all()
    valid = [r for r in results if r.answer_text]

    mentioned = 0
    cited = 0
    for r in valid:
        if not any(a.lower() in r.answer_text.lower() for a in aliases):
            continue
        mentioned += 1
        found_urls = re.findall(r'https?://[^\s\)\]】]+', r.answer_text)
        if any(any(d in u for d in domains) for u in found_urls):
            cited += 1

    return {
        "citation_rate": round(cited / mentioned, 4) if mentioned else 0.0,
        "cited_contexts": cited,
        "mentioned_contexts": mentioned,
        "sample_size": len(valid),
    }
```

---

### Task 6.4: Hallucination Detector — 2-stage (Claim Extraction + Verification)

**Files:**
- Create: `src/analyzer/hallucination.py`

- [ ] **Step 1: Stage 1 — Claim Extraction**

```python
# src/analyzer/hallucination.py
import re
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.models.hallucination import HallucinationResult
from src.schemas.ground_truth import GT_FIELD_LEVELS

@dataclass
class Claim:
    field: str
    claim_text: str
    context: str
    confidence: float  # 0.0 - 1.0

class HallucinationDetector:
    FIELD_EXTRACTORS = {
        "industry": [r'(?:属于|是[一]?[个家]?)([^，。\n]{4,40})(?:行业|领域|公司|企业|平台|工具)'],
        "positioning": [r'(?:定位[是为]|核心[是为]|主要[是为]|是[一]?[个家]?)([^，。\n]{4,60})(?:平台|工具|公司|产品|服务|方案)'],
        "category": [r'(?:提供|做|专注[于]?)([^，。\n]{4,40})(?:服务|产品|业务|功能|方案)'],
        "target_users": [r'(?:面向|服务[于]?|适合|针对|用户[是为])([^，。\n]{4,40})'],
        "differentiators": [r'(?:不同于|优势[是在于]|特色[是在于]|区别于)([^，。\n]{4,60})'],
    }

    def extract_claims(self, response: str) -> list[Claim]:
        claims = []
        for field, patterns in self.FIELD_EXTRACTORS.items():
            for pat in patterns:
                for match in re.finditer(pat, response):
                    ctx = response[max(0, match.start()-30):min(len(response), match.end()+50)]
                    claims.append(Claim(field=field, claim_text=match.group(0), context=ctx, confidence=0.7))
        return claims

    def verify_claim(self, claim: Claim, gt_json: dict) -> dict:
        gt_value = gt_json.get(claim.field)
        field_level = GT_FIELD_LEVELS.get(claim.field, "P1")

        if not gt_value:
            return {"verdict": "not_mentioned", "severity": field_level, "reason": "GT field not defined"}

        gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)

        if gt_str.lower()[:30] in claim.claim_text.lower():
            return {"verdict": "correct", "severity": field_level,
                    "reason": f"Claim matches GT: {gt_str[:50]}",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str}

        # Check if claim contradicts GT via keyword mismatch
        if any(kw in claim.claim_text.lower() for kw in ["营销", "CRM", "ERP"]) and \
           not any(kw in gt_str.lower() for kw in ["营销", "CRM", "ERP"]):
            return {"verdict": "incorrect", "severity": field_level,
                    "reason": f"Claim contradicts GT. Claim says: '{claim.claim_text[:80]}', GT: '{gt_str[:80]}'",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str}

        return {"verdict": "uncertain", "severity": field_level,
                "reason": "Cannot determine match — needs human review",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str}

    async def detect(self, query_result: QueryResult, gt: GroundTruthVersion, db: AsyncSession) -> list[HallucinationResult]:
        claims = self.extract_claims(query_result.answer_text)
        gt_json = gt.ground_truth_json
        results = []

        for claim in claims:
            verification = self.verify_claim(claim, gt_json)
            h = HallucinationResult(
                brand_id=query_result.brand_id,
                query_result_id=query_result.id,
                ground_truth_version_id=gt.id,
                field_name=claim.field,
                field_level=GT_FIELD_LEVELS.get(claim.field, "P1"),
                severity=verification["severity"],
                verdict=verification["verdict"],
                ai_claim=claim.claim_text,
                ground_truth_value=verification.get("ground_truth_value", ""),
                detected_at=None,
            )
            results.append(h)
        return results
```

- [ ] **Step 2: Write test with 5 mock AI responses — verify detector identifies industry error, positioning error, missing target_users, partial differentiator, not_mentioned field**

- [ ] **Step 3: Commit**

---

### Task 6.5: Competitor matrix

**Files:**
- Create: `src/analyzer/competitor.py`

```python
# src/analyzer/competitor.py
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.competitor_set import CompetitorSet
from src.models.metrics_snapshot import MetricsSnapshot

METRICS = ["sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"]

async def build_competitor_matrix(brand_id: str, db: AsyncSession) -> dict:
    active_set = (await db.execute(
        select(CompetitorSet).where(CompetitorSet.brand_id == brand_id, CompetitorSet.is_active == True)
    )).scalars().first()
    if not active_set:
        return {"matrix": [], "metric_names": METRICS}

    brand_ids = [uuid.UUID(brand_id)] + [uuid.UUID(cid) for cid in active_set.competitor_brand_ids]
    latest = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.brand_id.in_(brand_ids),
            MetricsSnapshot.platform.is_(None), MetricsSnapshot.dimension.is_(None),
        ).order_by(MetricsSnapshot.brand_id, MetricsSnapshot.week_start.desc())
    )).scalars().all()

    seen = {}
    for s in latest:
        if s.brand_id not in seen:
            seen[s.brand_id] = s

    return {"matrix": [{"brand_id": str(bid), **{m: getattr(s, m) for m in METRICS}, "sample_size": s.sample_size}
                        for bid, s in seen.items()], "metric_names": METRICS}
```

---

### Task 6.6: Metrics snapshot pipeline

**Files:**
- Create: `src/analyzer/pipeline.py`

- [ ] **Step 1: Pipeline — run all analyzers for a CollectionRun and save MetricsSnapshot**

```python
# src/analyzer/pipeline.py
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.metrics_snapshot import MetricsSnapshot
from src.analyzer.sov import compute_sov
from src.analyzer.first_rec import compute_first_rec
from src.analyzer.accuracy import compute_accuracy
from src.analyzer.completeness import compute_completeness
from src.analyzer.citation import compute_citation_rate

async def compute_and_save_metrics(brand_id: str, org_id: str, collection_run_id: str, db: AsyncSession):
    brand_id_str = str(brand_id)
    sov = await compute_sov(brand_id_str, collection_run_id, db)
    frr = await compute_first_rec(brand_id_str, collection_run_id, db)
    acc = await compute_accuracy(brand_id_str, collection_run_id, db)
    comp = await compute_completeness(brand_id_str, collection_run_id, db)
    cit = await compute_citation_rate(brand_id_str, collection_run_id, db)

    snapshot = MetricsSnapshot(
        brand_id=brand_id, organization_id=org_id,
        collection_run_id=collection_run_id,
        week_start=date.today(),
        sov=sov["sov"], first_rec_rate=frr["first_rec_rate"],
        accuracy_rate=acc["accuracy_rate"], completeness_rate=comp["completeness_rate"],
        citation_rate=cit["citation_rate"],
        sample_size=sov["sample_size"], failure_rate=sov["failure_rate"],
        details={"sov": sov, "frr": frr, "accuracy": acc, "completeness": comp, "citation": cit},
    )
    db.add(snapshot)
    await db.commit()
    return snapshot
```

- [ ] **Step 2: Test pipeline end-to-end with mock collection data, commit**

---

## Phase 7: Action Engine & Content Factory

### Task 7.1: Action engine — trigger to task mapping with state machine

**Files:**
- Create: `src/actions/__init__.py`, `src/actions/engine.py`

- [ ] **Step 1: Action engine with state validation**

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

VALID_TRANSITIONS = {
    "pending": ["in_progress", "cancelled"],
    "in_progress": ["completed", "cancelled"],
    "completed": ["verified", "reopened"],
    "verified": [],
    "cancelled": [],
    "reopened": ["in_progress"],
}

def validate_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])

async def generate_action_plans(brand_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> list[ActionPlan]:
    hallucinations = (await db.execute(
        select(HallucinationResult).where(
            HallucinationResult.brand_id == brand_id,
            HallucinationResult.human_reviewed == True,  # Only from reviewed hallucinations
            HallucinationResult.verdict == "incorrect",
        )
    )).scalars().all()

    plans = []
    for h in hallucinations:
        trigger = TRIGGER_MAP.get(h.field_level, TRIGGER_MAP["P2"])
        plan = ActionPlan(
            brand_id=brand_id, organization_id=org_id,
            trigger_type=f"field_{h.field_name}_error",
            action_type=trigger["action_type"],
            priority=h.field_level,
            evidence_hallucination_ids=[h.id],
            ai_wrong_claims={"claim": h.ai_claim},
            correct_ground_truth={"field": h.field_name, "value": h.ground_truth_value},
            suggested_content_type=trigger["content_type"],
            acceptance_criteria=f"Field '{h.field_name}' hallucination resolved: AI should state '{h.ground_truth_value[:100]}'",
            status="pending",
        )
        db.add(plan)
        plans.append(plan)

    await db.commit()
    return plans

async def update_action_status(action_id: uuid.UUID, new_status: str, db: AsyncSession) -> ActionPlan:
    action = (await db.execute(select(ActionPlan).where(ActionPlan.id == action_id))).scalar_one()
    if not validate_transition(action.status, new_status):
        raise ValueError(f"Invalid transition: {action.status} -> {new_status}")
    action.status = new_status
    await db.commit()
    return action
```

- [ ] **Step 2: Test state machine — verify pending→in_progress OK, pending→verified rejected**

- [ ] **Step 3: Commit**

---

### Task 7.2: Content Factory — brief generation (not auto-publish)

**Files:**
- Create: `src/actions/content_factory.py`

- [ ] **Step 1: Content brief templates**

```python
# src/actions/content_factory.py

QUALITY_CHECKLIST = [
    "内容是否基于真实产品能力？",
    "对比是否有客观依据和数据来源？",
    "案例是否可追溯验证？",
    "是否包含虚假或夸大声明？",
    "Schema结构是否与页面正文内容一致？",
    "是否为低质量重复性内容？",
]

def generate_content_brief(action_plan, ground_truth_json) -> dict:
    """Generate content brief for human review — NOT auto-published content."""
    gt = ground_truth_json
    return {
        "action_plan_id": str(action_plan.id),
        "content_type": action_plan.suggested_content_type,
        "priority": action_plan.priority,
        "problem_evidence": {
            "trigger": action_plan.trigger_type,
            "ai_wrong_claims": action_plan.ai_wrong_claims,
        },
        "correct_facts": {
            "field": action_plan.correct_ground_truth.get("field", ""),
            "value": action_plan.correct_ground_truth.get("value", ""),
        },
        "brand_context": {
            "official_name": gt.get("official_name", ""),
            "industry": gt.get("industry", ""),
            "positioning": gt.get("positioning", ""),
            "differentiators": gt.get("differentiators", []),
        },
        "required_sections": _get_required_sections(action_plan.suggested_content_type),
        "forbidden_claims": gt.get("forbidden_claims", []),
        "target_page_suggestion": action_plan.target_page or "官网 About / 产品页",
        "acceptance_criteria": action_plan.acceptance_criteria,
        "quality_checklist": QUALITY_CHECKLIST,
    }

def _get_required_sections(content_type: str) -> list[str]:
    return {
        "FAQ": ["问题", "简短答案", "详细说明", "来源或依据"],
        "Q&A": ["场景描述", "你的品牌如何解决", "与竞品的区别", "推荐理由"],
        "Comparison": ["对比维度", "你的品牌", "竞品A", "竞品B", "数据来源"],
        "Tutorial": ["行业背景", "核心概念", "实操步骤", "常见误区", "推荐工具"],
        "Case": ["客户背景", "面临的挑战", "解决方案", "量化结果", "客户引言"],
        "Schema": ["Organization Schema", "FAQ Schema", "验证通过的JSON-LD代码"],
    }.get(content_type, ["目标", "内容概要", "详细说明"])
```

- [ ] **Step 2: Test — verify brief output has all required fields, is in draft/review status, not published**

- [ ] **Step 3: Commit**

---

## Phase 8: API + Dashboard + E2E

### Task 8.1: Auth API with org isolation

**Files:**
- Create: `src/api/__init__.py`, `src/api/deps.py`, `src/api/auth.py`

- [ ] **Step 1: Dependencies with org-aware query helper**

```python
# src/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
            raise HTTPException(status_code=401)
    except JWTError:
        raise HTTPException(status_code=401)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401)
    return user

async def get_org_brand_or_404(brand_id, user: User, db: AsyncSession):
    from src.models.brand import Brand
    brand = (await db.execute(
        select(Brand).where(Brand.id == brand_id, Brand.organization_id == user.organization_id)
    )).scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand
```

- [ ] **Step 2: Auth routes**

```python
# src/api/auth.py — login/register with JWT, passlib bcrypt
# POST /api/auth/register — creates org + user, returns JWT
# POST /api/auth/login — verifies credentials, returns JWT
```

- [ ] **Step 3: Test — register, login, access protected endpoint, verify 401 without token**

- [ ] **Step 4: Commit**

---

### Task 8.2: Brand API

**Files:**
- Create: `src/api/brands.py`

```python
# GET /api/brands — list (paginated, page/page_size, org filter)
# POST /api/brands — create with initial GT
# GET /api/brands/{id} — detail with active GT
# PUT /api/brands/{id} — update, creates new GT version if GT changed
# POST /api/brands/{id}/collect — trigger collection
```
All endpoints filter by `organization_id == user.organization_id`.

---

### Task 8.3: CollectionRun and QueryResult API

**Files:**
- Create: `src/api/collection_runs.py`, `src/api/queries.py`

```python
# GET /api/brands/{id}/collections — list CollectionRuns, paginated
# GET /api/collections/{id} — single run with stats
# GET /api/brands/{id}/queries — list QueryResults, filter by collection_run_id/platform/status
# GET /api/queries/{id} — single result with full answer + citations
```
All endpoints filter by `organization_id`.

---

### Task 8.4: Metrics API

**Files:**
- Create: `src/api/metrics.py`

```python
# GET /api/brands/{id}/metrics — latest snapshot (or compute on-demand from latest collection_run)
# GET /api/brands/{id}/metrics/history — weekly snapshots
# GET /api/brands/{id}/metrics/by-platform — per-platform breakdown
```
Each response includes `sample_size`, `failure_rate`, `collection_run_id`.

---

### Task 8.5: Hallucination Review API

**Files:**
- Create: `src/api/hallucinations.py`

```python
# GET /api/brands/{id}/hallucinations — list, filter by severity/verdict/human_reviewed
# POST /api/hallucinations/{id}/review — submit review (verdict + notes), saves reviewer_id
# POST /api/brands/{id}/hallucinations/generate-actions — from reviewed P0 errors, generate ActionPlans
```

---

### Task 8.6: ActionPlan and Content Brief API

**Files:**
- Create: `src/api/actions.py`, `src/api/content.py`

```python
# src/api/actions.py
# GET /api/brands/{id}/actions — list, filter by status/priority, paginated
# PUT /api/actions/{id} — update status (validated against state machine), owner, notes
# POST /api/brands/{id}/actions/generate — trigger generation from reviewed hallucinations

# src/api/content.py
# GET /api/brands/{id}/content — list content briefs
# POST /api/actions/{id}/brief — generate content brief
# PUT /api/content/{id} — update brief status (draft→review→published)
```

---

### Task 8.7: Dashboard API

**Files:**
- Create: `src/api/dashboard.py`

```python
# GET /api/dashboard — org-level overview:
#   - total brands
#   - avg SOV / first_rec_rate / accuracy / completeness / citation across all brands
#   - total pending action plans by priority
#   - recent P0 hallucinations count
#   - last collection run status for each brand
```

---

### Task 8.8: Register all routers

**Files:**
- Modify: `src/main.py`

```python
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from src.api import auth, brands, collection_runs, queries, metrics, hallucinations, actions, content, dashboard

app = FastAPI(title="GEO Explorer", version="0.1.0")
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

for router in [auth.router, brands.router, collection_runs.router, queries.router,
                metrics.router, hallucinations.router, actions.router, content.router, dashboard.router]:
    app.include_router(router)
```

---

### Task 8.9: Frontend — base template and dashboard pages

**Files:**
- Create: `src/templates/base.html`, `src/static/css/app.css`
- Create: `src/templates/dashboard/index.html`, `src/templates/brands/detail.html`

- [ ] **Step 1: Base template with Jinja2 + HTMX + Chart.js**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEO Explorer — 品牌AI可见度</title>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link href="/static/css/app.css" rel="stylesheet">
</head>
<body>
    <nav><!-- sidebar --></nav>
    <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

- [ ] **Step 2: Dashboard — 5 metric cards with tooltip explanations, sample_size, failure_rate, weekly trend sparklines**

- [ ] **Step 3: Brand detail — GT display, metrics chart, platform comparison, recent collections**

- [ ] **Step 4: Commit**

---

### Task 8.10: Frontend — query, hallucination, action, content pages

**Files:**
- Create: `src/templates/queries/list.html`, `src/templates/queries/detail.html`
- Create: `src/templates/hallucinations/list.html`, `src/templates/hallucinations/review.html`
- Create: `src/templates/actions/board.html`
- Create: `src/templates/content/library.html`

- [ ] **Step 1: Query list — filterable table (platform, status, collection_run), pagination**

- [ ] **Step 2: Query detail — full AI response, citation list, hallucination annotations**

- [ ] **Step 3: Hallucination review page — AI claim vs GT side-by-side, review form with correct/incorrect/uncertain/ignored**

- [ ] **Step 4: Action kanban — columns for pending/in_progress/completed, drag to update status (respects state machine)**

- [ ] **Step 5: Content library — list by type/status, brief detail view with quality checklist**

- [ ] **Step 6: Commit**

---

### Task 8.11: E2E Integration Test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Full pipeline test**

```python
@pytest.mark.asyncio
async def test_full_pipeline(db_session):
    """Complete E2E: register → add brand → fill GT → mock collect → view metrics → detect hallucinations → review → generate action → create brief"""
    # 1. Create org + user
    # 2. Add brand with GT
    # 3. Seed templates
    # 4. Trigger mock collection (use MockAdapter)
    # 5. Verify CollectionRun created with correct counts
    # 6. Verify QueryResults linked to CollectionRun
    # 7. Run metrics pipeline → verify MetricsSnapshot with all 5 KPIs
    # 8. Run hallucination detection → verify HallucinationResults
    # 9. Review P0 hallucination → update human_reviewed
    # 10. Generate ActionPlan → verify P0 action with evidence
    # 11. Generate content brief → verify brief has all required fields
    # 12. Verify API org isolation → user A cannot access user B's brand
```

- [ ] **Step 2: Run E2E test — all steps must pass**

```bash
python -m pytest tests/test_e2e.py -v -s
```

- [ ] **Step 3: Fix any issues, commit**

---

### Task 8.12: Final verification

- [ ] **Step 1: Full test suite**

```bash
python -m pytest tests/ -v
```

- [ ] **Step 2: Docker Compose integration test**

```bash
docker compose up -d db test_db redis
alembic upgrade head
python scripts/seed.py
python -m pytest tests/ -v
```

- [ ] **Step 3: .gitignore update and final commit**
