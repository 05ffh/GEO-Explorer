#!/usr/bin/env bash
# GEO Explorer — Database backup (P0-5)
# Usage: ./deploy/backup.sh [--quiet]
# Output: deploy/backups/geo_YYYYMMDD_HHMMSS_<sha>.dump (pg_dump custom format)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="${SCRIPT_DIR}/backups"
COMPOSE_FILE="${SCRIPT_DIR}/../docker-compose.prod.yml"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"

mkdir -p "$BACKUP_DIR"

# ── Identify container ────────────────────────────────────────────────────────
PG_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null || echo "")
if [ -z "$PG_CONTAINER" ]; then
    echo "[ERROR] PostgreSQL container not found. Is docker-compose.prod.yml running?"
    exit 1
fi

# ── Get env ───────────────────────────────────────────────────────────────────
POSTGRES_USER="${POSTGRES_USER:-geo}"
POSTGRES_DB="${POSTGRES_DB:-geo_explorer}"
GIT_SHA=$(git -C "${SCRIPT_DIR}/.." rev-parse --short HEAD 2>/dev/null || echo "unknown")

# ── Backup ────────────────────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/geo_${TIMESTAMP}_${GIT_SHA}.dump"

echo "[$(date '+%H:%M:%S')] Backing up ${POSTGRES_DB} → ${BACKUP_FILE}"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc \
    > "$BACKUP_FILE" 2>&1

BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date '+%H:%M:%S')] Backup complete: ${BACKUP_SIZE}"

# ── Retention cleanup ─────────────────────────────────────────────────────────
find "$BACKUP_DIR" -name "geo_*.dump" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
LOCAL_COUNT=$(find "$BACKUP_DIR" -name "geo_*.dump" | wc -l)
echo "[$(date '+%H:%M:%S')] ${LOCAL_COUNT} backups retained (${RETENTION_DAYS}d)"

echo "$BACKUP_FILE"
