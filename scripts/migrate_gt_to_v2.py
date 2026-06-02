"""P1-1: Migrate GT from v1 flat format to v2 structured format.

Usage:
  python scripts/migrate_gt_to_v2.py --dry-run     # Preview only, no writes
  python scripts/migrate_gt_to_v2.py --apply        # Execute migration
  python scripts/migrate_gt_to_v2.py --verify       # Verify v2 flat output
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text

from src.config import settings

BACKUP_DIR = Path(__file__).parent.parent / "artifacts" / "gt_migrations"


async def backup_gt(session: AsyncSession, backup_id: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"gt_backup_{backup_id}.jsonl"
    rows = (await session.execute(text("SELECT * FROM ground_truth_versions"))).fetchall()
    cols = [c[0] for c in rows[0]._mapping.items()] if rows else []
    with open(path, "w") as f:
        for row in rows:
            d = dict(row._mapping)
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    print(f"Backed up {len(rows)} GT versions to {path}")
    return path


async def scan_gt(session: AsyncSession) -> dict:
    rows = (await session.execute(text(
        "SELECT id, brand_id, version, status, gt_schema_version, ground_truth_json "
        "FROM ground_truth_versions ORDER BY brand_id, version"
    ))).fetchall()

    v1_count = 0
    v2_count = 0
    unknown_fields = set()
    missing_required = {}

    from src.schemas.gt_field_registry import get_required_fields, validate_field_name

    for row in rows:
        gt_json = row.ground_truth_json or {}
        schema_ver = row.gt_schema_version
        if schema_ver == "gt_v2" or gt_json.get("schema_version") == "gt_v2":
            v2_count += 1
            continue
        v1_count += 1
        for field_name in gt_json:
            valid, _ = validate_field_name(field_name)
            if not valid:
                unknown_fields.add(field_name)
        required = get_required_fields()
        missing = [f for f in required if f not in gt_json or not gt_json[f]]
        if missing:
            missing_required[str(row.id)] = missing

    return {
        "total": len(rows), "v1": v1_count, "v2": v2_count,
        "unknown_fields": sorted(unknown_fields),
        "missing_required": missing_required,
    }


def migrate_one(gt_json: dict, source_urls: list | None = None) -> tuple[dict, list[str]]:
    from src.schemas.gt_field_registry import GT_FIELD_REGISTRY, validate_field_name
    from src.schemas.gt_v2 import compute_coverage_score

    warnings = []
    fields = {}
    now = datetime.now(timezone.utc).isoformat()
    legacy_sources = []
    if source_urls:
        legacy_sources = [{
            "tier": "C", "source_type": "other", "url": u, "title": "",
            "evidence_text": "", "retrieved_at": now,
        } for u in source_urls]

    for field_name, value in gt_json.items():
        valid, reason = validate_field_name(field_name)
        if not valid:
            warnings.append(f"unknown_field: {reason}")
        defn = GT_FIELD_REGISTRY.get(field_name)
        if isinstance(value, list):
            field_type = "list"
            values = [{"value": str(v), "primary": True, "sources": legacy_sources}
                       for v in value]
        else:
            field_type = defn.field_type if defn else "string"
            values = [{"value": str(value), "primary": True, "sources": legacy_sources}]
        fields[field_name] = {
            "field_type": field_type, "values": values, "status": "reviewed",
        }

    meta = {
        "schema_version": "gt_meta_v1",
        "last_reviewed_at": now,
        "coverage_score": compute_coverage_score(
            {k: type("F", (), {"values": v["values"]})() for k, v in fields.items()}
        ),
        "total_fields": len(fields),
        "completed_fields": sum(1 for f in fields.values() if f["values"]),
    }
    return {"schema_version": "gt_v2", "fields": fields, "meta": meta}, warnings


async def apply_migration(session: AsyncSession, dry_run: bool = False) -> dict:
    rows = (await session.execute(text(
        "SELECT id, version, ground_truth_json, source_urls FROM ground_truth_versions "
        "WHERE (gt_schema_version IS NULL OR gt_schema_version != 'gt_v2') "
        "AND ground_truth_json IS NOT NULL"
    ))).fetchall()

    migrated = 0
    warnings_all = []
    for row in rows:
        gt_json = row.ground_truth_json or {}
        if gt_json.get("schema_version") == "gt_v2":
            continue
        v2_json, warns = migrate_one(gt_json, list(row.source_urls or []))
        warnings_all.extend(warns)
        if not dry_run:
            await session.execute(text(
                "UPDATE ground_truth_versions "
                "SET ground_truth_json = CAST(:v2 AS jsonb), gt_schema_version = 'gt_v2' "
                "WHERE id = :id"
            ), {"v2": json.dumps(v2_json, ensure_ascii=False), "id": row.id})
        migrated += 1

    if not dry_run:
        await session.commit()
    return {"migrated": migrated, "warnings": warnings_all[:20]}


async def verify_migration(session: AsyncSession) -> bool:
    from src.schemas.gt_v2 import gt_v2_to_flat
    rows = (await session.execute(text(
        "SELECT id, ground_truth_json FROM ground_truth_versions "
        "WHERE gt_schema_version = 'gt_v2'"
    ))).fetchall()
    ok = True
    for row in rows:
        gt = row.ground_truth_json or {}
        try:
            flat = gt_v2_to_flat(gt)
            if not isinstance(flat, dict):
                print(f"  FAIL {row.id}: flat() returned non-dict")
                ok = False
        except Exception as e:
            print(f"  FAIL {row.id}: {e}")
            ok = False
    return ok


async def main():
    parser = argparse.ArgumentParser(description="Migrate GT v1 -> v2")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if not any([args.dry_run, args.apply, args.verify]):
        parser.print_help()
        return

    engine = create_async_engine(settings.database_url)
    async with AsyncSession(engine) as session:
        if args.verify:
            ok = await verify_migration(session)
            print(f"Verification: {'PASS' if ok else 'FAIL'}")
            return

        stats = await scan_gt(session)
        print(f"Found {stats['total']} GT versions: {stats['v1']} v1, {stats['v2']} v2")
        if stats["unknown_fields"]:
            print(f"Unknown fields: {stats['unknown_fields']}")
        if stats["missing_required"]:
            print(f"Missing required fields: {len(stats['missing_required'])} versions")

        if stats["v1"] == 0:
            print("No v1 GTs to migrate.")
            return

        backup_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        await backup_gt(session, backup_id)

        result = await apply_migration(session, dry_run=args.dry_run)
        action = "Would migrate" if args.dry_run else "Migrated"
        print(f"{action} {result['migrated']} GT versions")
        for w in result["warnings"]:
            print(f"  WARNING: {w}")

        if not args.dry_run:
            print(f"Backup ID: {backup_id}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
