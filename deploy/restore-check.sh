#!/usr/bin/env bash
# GEO Explorer — Backup restore verification (P0-5)
# Usage: ./deploy/restore-check.sh [backup_file]
# Spins up a temporary PostgreSQL, imports backup, runs minimal SQL checks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/backups"

# ── Find latest backup ────────────────────────────────────────────────────────
if [ $# -ge 1 ]; then
    BACKUP_FILE="$1"
else
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/geo_*.dump 2>/dev/null | head -1 || echo "")
fi

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
    echo "[ERROR] No backup file found. Run ./deploy/backup.sh first."
    exit 1
fi

echo "[$(date '+%H:%M:%S')] Verifying backup: $BACKUP_FILE"

# ── Start temp PostgreSQL ─────────────────────────────────────────────────────
TEMP_CONTAINER="geo_restore_check_$$"
TEMP_PORT=15432
TEMP_PASSWORD="restore_check_temp"

echo "[$(date '+%H:%M:%S')] Starting temporary PostgreSQL on port ${TEMP_PORT}..."
docker run -d --rm --name "$TEMP_CONTAINER" \
    -e POSTGRES_USER=geo -e POSTGRES_PASSWORD="$TEMP_PASSWORD" \
    -e POSTGRES_DB=geo_restore_test \
    -p "${TEMP_PORT}:5432" \
    postgres:16-alpine > /dev/null

# Wait for PG to be ready
for i in $(seq 1 30); do
    if docker exec "$TEMP_CONTAINER" pg_isready -U geo -d geo_restore_test &>/dev/null; then
        break
    fi
    sleep 1
done

# ── Restore ───────────────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Restoring backup..."
PGPASSWORD="$TEMP_PASSWORD" pg_restore -h localhost -p "$TEMP_PORT" \
    -U geo -d geo_restore_test --no-owner --no-privileges \
    "$BACKUP_FILE" 2>&1 || {
    echo "[FAIL] Restore failed — backup may be corrupted"
    docker stop "$TEMP_CONTAINER" > /dev/null 2>&1
    exit 1
}

# ── Verify ────────────────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Running verification queries..."
TABLE_COUNT=$(PGPASSWORD="$TEMP_PASSWORD" psql -h localhost -p "$TEMP_PORT" \
    -U geo -d geo_restore_test -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>&1 || echo "0")
echo "  Tables restored: ${TABLE_COUNT}"

# ── Cleanup ──────────────────────────────────────────────────────────────────
docker stop "$TEMP_CONTAINER" > /dev/null 2>&1

if [ "$TABLE_COUNT" -gt 5 ]; then
    echo "[$(date '+%H:%M:%S')] [PASS] Backup is valid and restorable (${TABLE_COUNT} tables)"
    exit 0
else
    echo "[$(date '+%H:%M:%S')] [FAIL] Restored database has too few tables (${TABLE_COUNT})"
    exit 1
fi
