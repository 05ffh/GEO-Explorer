"""DataExport async Celery task — generates export files (P2-5)."""
import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.celery_app import app as celery_app
from src.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

EXPORT_DIR = "exports"


@celery_app.task(bind=True, max_retries=1, soft_time_limit=300, time_limit=420)
def data_export_task(self, export_id: str):
    """Generate a data export file and create a signed download token."""

    async def run():
        async with SessionLocal() as db:
            eid = uuid.UUID(export_id)

            # Update status
            await db.execute(text(
                "UPDATE data_exports SET status = 'generating', task_state_id = :tid WHERE id = :id"
            ), {"tid": self.request.id, "id": eid})

            # Load export request
            exp = (await db.execute(text(
                "SELECT * FROM data_exports WHERE id = :id"
            ), {"id": eid})).fetchone()
            if not exp:
                return {"status": "error", "detail": "Export not found"}

            org_id = exp.organization_id
            scope = exp.scope
            brand_id = exp.brand_id
            fmt = exp.format

            # Gather data
            data = await _gather_export_data(db, org_id, brand_id, scope)

            # Generate file
            os.makedirs(EXPORT_DIR, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
            safe_name = f"export_{org_id}_{date_str}"

            if fmt == "json":
                filepath = os.path.join(EXPORT_DIR, f"{safe_name}.json")
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            else:
                # CSV ZIP
                import zipfile
                filepath = os.path.join(EXPORT_DIR, f"{safe_name}.zip")
                with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
                    for table_name, rows in data.items():
                        if rows:
                            csv_content = _to_csv(rows)
                            zf.writestr(f"{table_name}.csv", csv_content)
                    # Add manifest
                    manifest = {"export_id": export_id, "organization_id": str(org_id),
                                "scope": scope, "generated_at": date_str,
                                "tables": list(data.keys())}
                    zf.writestr("manifest.json", json.dumps(manifest, indent=2))

            # File hash + size
            file_size = os.path.getsize(filepath)
            with open(filepath, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            # Generate download token
            raw_token = uuid.uuid4().hex
            token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            expires = datetime.now(timezone.utc) + timedelta(hours=72)

            # Update export record
            await db.execute(text("""
                UPDATE data_exports SET status = 'completed', file_path = :path,
                file_hash = :hash, file_size_bytes = :size,
                download_token_hash = :th, expires_at = :exp,
                updated_at = :now WHERE id = :id
            """), {
                "path": filepath, "hash": file_hash, "size": file_size,
                "th": token_hash, "exp": expires, "now": datetime.now(timezone.utc),
                "id": eid,
            })
            await db.commit()

            return {
                "status": "completed", "export_id": export_id,
                "file_size": file_size, "download_token": raw_token,
                "expires_at": expires.isoformat(),
            }

    return asyncio.run(run())


async def _gather_export_data(db, org_id, brand_id, scope) -> dict:
    """Gather data for export."""
    data = {}

    # Organization info
    org = (await db.execute(text("SELECT id, name, slug, plan FROM organizations WHERE id = :id"),
                             {"id": org_id})).fetchone()
    if org:
        data["organization"] = [dict(org._mapping)]

    # Brands
    brand_filter = "AND b.id = :bid" if brand_id else ""
    brand_params = {"oid": org_id}
    if brand_id:
        brand_params["bid"] = brand_id
    brands = (await db.execute(text(
        f"SELECT b.* FROM brands b WHERE b.organization_id = :oid {brand_filter}"
    ), brand_params)).fetchall()
    if brands:
        data["brands"] = [_row(r) for r in brands]

    # Collection runs
    runs = (await db.execute(text(
        "SELECT id, brand_id, collection_status, total_queries, success_count, "
        "created_at FROM collection_runs WHERE organization_id = :oid ORDER BY created_at DESC LIMIT 100"
    ), {"oid": org_id})).fetchall()
    if runs:
        data["collection_runs"] = [_row(r) for r in runs]

    # Metrics
    metrics = (await db.execute(text(
        "SELECT * FROM metrics_snapshots WHERE organization_id = :oid ORDER BY created_at DESC LIMIT 50"
    ), {"oid": org_id})).fetchall()
    if metrics:
        data["metrics"] = [_row(r) for r in metrics]

    # Hallucinations
    halls = (await db.execute(text(
        "SELECT * FROM hallucination_results WHERE organization_id = :oid ORDER BY created_at DESC LIMIT 200"
    ), {"oid": org_id})).fetchall()
    if halls:
        data["hallucinations"] = [_row(r) for r in halls]

    # Reports
    reports = (await db.execute(text(
        "SELECT id, brand_id, edition, format, status, generated_at "
        "FROM report_artifacts WHERE organization_id = :oid ORDER BY created_at DESC LIMIT 50"
    ), {"oid": org_id})).fetchall()
    if reports:
        data["reports"] = [_row(r) for r in reports]

    return data


def _row(r) -> dict:
    return {k: str(v) if isinstance(v, uuid.UUID) else
            v.isoformat() if isinstance(v, datetime) else v
            for k, v in dict(r._mapping).items()}


def _to_csv(rows: list) -> str:
    if not rows:
        return ""
    import csv, io
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()
