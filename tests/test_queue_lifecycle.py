"""Tests for TaskLifecycle state transitions (P1-5)."""
import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from src.models.task_state import TaskState, TASK_STATUS_TRANSITIONS, TERMINAL_STATUSES
from src.queue.lifecycle import TaskLifecycle


@pytest.fixture
async def db():
    from src.config import settings
    engine = create_async_engine(settings.test_database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def test_org_id(db):
    """Create a test org and return its ID."""
    from src.models.organization import Organization
    org = Organization(name=f"test-org-{uuid.uuid4().hex[:6]}")
    db.add(org)
    await db.flush()
    return org.id


@pytest.fixture
async def ts(db, test_org_id):
    """Create a test TaskState using a valid org."""
    now = datetime.now(timezone.utc)
    ts = TaskState(
        celery_task_id=f"test-{uuid.uuid4().hex[:8]}",
        root_task_id=f"test-{uuid.uuid4().hex[:8]}",
        task_name="test_task",
        organization_id=test_org_id,
        brand_id=None,
        operation_type="test",
        trigger_type="manual",
        status="queued",
        queued_at=now,
        max_retries=3,
    )
    db.add(ts)
    await db.flush()
    return ts


class TestStateTransitions:
    async def _set_status(self, db, ts, status):
        """Helper to update status in DB before testing transitions."""
        from sqlalchemy import update as sql_update
        await db.execute(
            sql_update(TaskState).where(TaskState.id == ts.id).values(status=status)
        )
        ts.status = status

    @pytest.mark.asyncio
    async def test_valid_transition_queued_to_running(self, db, ts):
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "running", "start")
        assert ok is True
        assert ts.status == "running"
        assert ts.version > 0

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_completed(self, db, ts):
        await self._set_status(db, ts, "running")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "completed", "done")
        assert ok is True
        assert ts.status == "completed"
        assert ts.progress == 1.0

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_failed(self, db, ts):
        await self._set_status(db, ts, "running")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "failed", "error")
        assert ok is True
        assert ts.status == "failed"

    @pytest.mark.asyncio
    async def test_valid_transition_failed_to_dead_lettered(self, db, ts):
        await self._set_status(db, ts, "failed")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "dead_lettered", "dlq")
        assert ok is True
        assert ts.status == "dead_lettered"

    @pytest.mark.asyncio
    async def test_valid_transition_dead_lettered_to_requeued(self, db, ts):
        await self._set_status(db, ts, "dead_lettered")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "requeued", "requeued")
        assert ok is True
        assert ts.status == "requeued"

    @pytest.mark.asyncio
    async def test_valid_transition_requeued_to_queued(self, db, ts):
        await self._set_status(db, ts, "requeued")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "queued", "back to queue")
        assert ok is True

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_cancelled(self, db, ts):
        await self._set_status(db, ts, "running")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "cancelled", "cancelled")
        assert ok is True

    @pytest.mark.asyncio
    async def test_valid_transition_running_to_retrying(self, db, ts):
        await self._set_status(db, ts, "running")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "retrying", "retrying")
        assert ok is True

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_running(self, db, ts):
        await self._set_status(db, ts, "completed")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "running", "cannot restart")
        assert ok is False
        assert ts.status == "completed"

    @pytest.mark.asyncio
    async def test_invalid_transition_cancelled_to_running(self, db, ts):
        await self._set_status(db, ts, "cancelled")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "running", "cannot restart")
        assert ok is False

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_failed(self, db, ts):
        await self._set_status(db, ts, "completed")
        lc = TaskLifecycle(db)
        ok = await lc.transition(ts, "failed", "too late")
        assert ok is False


class TestStateMachine:
    def test_transition_map_completeness(self):
        """All non-terminal states must have at least one outgoing transition."""
        for status in TASK_STATUS_TRANSITIONS:
            if status not in TERMINAL_STATUSES:
                assert len(TASK_STATUS_TRANSITIONS[status]) > 0, f"{status} has no outgoing transitions"

    def test_terminal_states_no_outgoing(self):
        for status in TERMINAL_STATUSES:
            transitions = TASK_STATUS_TRANSITIONS.get(status, set())
            assert len(transitions) == 0, f"Terminal {status} should have no transitions"

    def test_enqueue_failed_transitions(self):
        """enqueue_failed can be manually retried to queued."""
        assert "queued" in TASK_STATUS_TRANSITIONS.get("enqueue_failed", set())


class TestCreateTaskState:
    @pytest.mark.asyncio
    async def test_create_sets_defaults(self, db, test_org_id):
        lc = TaskLifecycle(db)
        ts = await lc.create(
            celery_task_id="test-create-1",
            task_name="test.task",
            organization_id=test_org_id,
            operation_type="test_create",
        )
        assert ts.status == "queued"
        assert ts.max_retries == 3
        assert ts.queued_at is not None
        assert ts.root_task_id == "test-create-1"
        assert ts.organization_id == test_org_id


class TestProgressThrottling:
    @pytest.mark.asyncio
    async def test_first_progress_update_writes(self, db, ts):
        from sqlalchemy import update as sql_update
        await db.execute(sql_update(TaskState).where(TaskState.id == ts.id).values(status="running"))
        ts.status = "running"
        lc = TaskLifecycle(db)
        await lc.update_progress(ts, 0.5, "half done")
        assert ts.progress == 0.5

    @pytest.mark.asyncio
    async def test_small_delta_skipped(self, db, ts):
        from sqlalchemy import update as sql_update
        await db.execute(sql_update(TaskState).where(TaskState.id == ts.id).values(
            status="running", progress=0.50,
            last_progress_update_at=datetime.now(timezone.utc),
        ))
        ts.progress = 0.50
        ts.last_progress_update_at = datetime.now(timezone.utc)
        lc = TaskLifecycle(db)
        await lc.update_progress(ts, 0.51, "tiny change")  # delta < 5%
        assert ts.progress == 0.50  # unchanged

    @pytest.mark.asyncio
    async def test_large_delta_writes(self, db, ts):
        from sqlalchemy import update as sql_update
        await db.execute(sql_update(TaskState).where(TaskState.id == ts.id).values(
            status="running", progress=0.50,
            last_progress_update_at=datetime.now(timezone.utc),
        ))
        ts.progress = 0.50
        ts.last_progress_update_at = datetime.now(timezone.utc)
        lc = TaskLifecycle(db)
        await lc.update_progress(ts, 0.60, "big change")  # delta >= 5%
        assert ts.progress == 0.60
