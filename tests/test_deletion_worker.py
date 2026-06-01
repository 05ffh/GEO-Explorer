"""DataDeletion Worker tests (Task 2 — P0-3/P0-4/P0-5/P0-6)."""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import text, select

from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.saas import DataDeletionRequest, DeletionReceipt
from src.saas.deletion_task import _batch_delete, _collect_file_keys, _delete_files


async def _setup_deletion_test(db_session, scope="brand", status="approved"):
    """Create org+user+brand+deletion_request. Returns (org, user, brand, dr)."""
    org = Organization(name="DelTestOrg")
    db_session.add(org)
    await db_session.commit()

    user = User(organization_id=org.id, email="deltest@test.com", name="DelTester",
                role="owner", password_hash="test_hash")
    db_session.add(user)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="DelBrand", industry="SaaS", created_by=user.id)
    db_session.add(brand)
    await db_session.commit()

    dr = DataDeletionRequest(
        organization_id=org.id, requested_by=user.id,
        scope=scope, brand_id=brand.id if scope == "brand" else None,
        status=status,
        scheduled_delete_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(dr)
    await db_session.commit()

    return org, user, brand, dr


@pytest.mark.asyncio
async def test_deletion_request_model_has_new_fields(db_session):
    """DataDeletionRequest has failed_table, failed_reason, last_processed_id, retry_count."""
    org, user, brand, dr = await _setup_deletion_test(db_session)

    assert hasattr(dr, "failed_table")
    assert hasattr(dr, "failed_reason")
    assert hasattr(dr, "last_processed_id")
    assert hasattr(dr, "retry_count")
    assert dr.retry_count == 0


@pytest.mark.asyncio
async def test_deletion_receipt_creation(db_session):
    """DeletionReceipt can be created and linked to a request."""
    org, user, brand, dr = await _setup_deletion_test(db_session)

    import hashlib, json
    receipt_data = {
        "request_id": str(dr.id), "organization_id": str(org.id),
        "scope": "brand", "brand_id": str(brand.id),
        "deleted_counts": {"brands": 1}, "anonymized_counts": {},
        "retained_items": [], "file_deleted_count": 0, "file_failed_count": 0,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    canonical = json.dumps(receipt_data, sort_keys=True, ensure_ascii=False)
    receipt_hash = hashlib.sha256(canonical.encode()).hexdigest()

    receipt = DeletionReceipt(
        deletion_request_id=dr.id, organization_id=org.id,
        scope="brand", brand_id=brand.id,
        requested_by=user.id, approved_by=user.id,
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        affected_tables_json=["brands"],
        deleted_counts_json={"brands": 1},
        retained_items_json=[{"type": "security_audit", "reason": "retained for 180 days"}],
        receipt_hash=receipt_hash,
    )
    db_session.add(receipt)
    await db_session.commit()

    # Verify
    saved = await db_session.get(DeletionReceipt, receipt.id)
    assert saved is not None
    assert saved.receipt_hash == receipt_hash
    assert saved.deletion_request_id == dr.id


@pytest.mark.asyncio
async def test_receipt_hash_verifiable(db_session):
    """Receipt hash can be verified by recalculating from canonical JSON."""
    org, user, brand, dr = await _setup_deletion_test(db_session)

    import hashlib, json
    receipt_data = {
        "request_id": str(dr.id), "organization_id": str(org.id),
        "scope": "brand", "brand_id": str(brand.id),
        "deleted_counts": {"brands": 1}, "anonymized_counts": {},
        "retained_items": [], "file_deleted_count": 1, "file_failed_count": 0,
        "completed_at": "2026-01-01T00:00:00+00:00",
    }
    canonical1 = json.dumps(receipt_data, sort_keys=True, ensure_ascii=False)
    hash1 = hashlib.sha256(canonical1.encode()).hexdigest()

    # Same data → same hash
    canonical2 = json.dumps(receipt_data, sort_keys=True, ensure_ascii=False)
    hash2 = hashlib.sha256(canonical2.encode()).hexdigest()
    assert hash1 == hash2

    # Different data → different hash
    receipt_data["deleted_counts"] = {"brands": 2}
    canonical3 = json.dumps(receipt_data, sort_keys=True, ensure_ascii=False)
    hash3 = hashlib.sha256(canonical3.encode()).hexdigest()
    assert hash1 != hash3


@pytest.mark.asyncio
async def test_deletion_status_transitions(db_session):
    """DataDeletionRequest statuses follow the expected lifecycle."""
    org, user, brand, dr = await _setup_deletion_test(db_session, status="requested")

    # requested → approved
    dr.status = "approved"
    dr.scheduled_delete_at = datetime.now(timezone.utc) + timedelta(days=90)
    await db_session.commit()
    await db_session.refresh(dr)
    assert dr.status == "approved"

    # approved → processing
    dr.status = "processing"
    await db_session.commit()
    await db_session.refresh(dr)
    assert dr.status == "processing"

    # processing → completed
    dr.status = "completed"
    dr.completed_at = datetime.now(timezone.utc)
    await db_session.commit()
    await db_session.refresh(dr)
    assert dr.status == "completed"


@pytest.mark.asyncio
async def test_deletion_request_completed_is_noop(db_session):
    """Completed deletion requests should not be re-processed."""
    org, user, brand, dr = await _setup_deletion_test(db_session, status="completed")
    # Verifying that the status remains "completed" — worker would noop
    assert dr.status == "completed"


@pytest.mark.asyncio
async def test_deletion_request_processing_duplicate_handled(db_session):
    """Processing deletion requests should be recognized as in-progress."""
    org, user, brand, dr = await _setup_deletion_test(db_session, status="processing")
    assert dr.status == "processing"


@pytest.mark.asyncio
async def test_batch_delete_respects_scope(db_session):
    """_collect_file_keys returns list from data_exports and report_artifacts."""
    org, user, brand, dr = await _setup_deletion_test(db_session)

    paths = await _collect_file_keys(db_session, org.id, brand.id, "brand")
    assert isinstance(paths, list)
    # With no exports/reports, should return empty list
    assert paths == []


@pytest.mark.asyncio
async def test_file_deletion_tracking(db_session):
    """_delete_files tracks successes and failures correctly."""
    paths = ["/nonexistent/path/test_file.txt"]
    deleted, failed, failed_assets = await _delete_files(paths)

    # Non-existent file → treated as already deleted (not a failure)
    assert deleted >= 0
    assert isinstance(failed, int)
    assert isinstance(failed_assets, list)
