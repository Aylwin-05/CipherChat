#!/bin/bash
# ============================================================
# Nexara Database Backup Script
# ============================================================
# Creates timestamped pg_dump backups with optional compression.
# Designed to run via cron or manually.
#
# Usage:
#   chmod +x scripts/backup-db.sh
#   ./scripts/backup-db.sh                    # dump to ./backups/
#   ./scripts/backup-db.sh /mnt/s3-mount     # dump to custom path
#
# Restore:
#   gunzip -c backups/nexara_20260903_120000.sql.gz | docker compose exec -T postgres psql -U nexara -d nexara
# ============================================================

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="nexara_${TIMESTAMP}.sql.gz"
CONTAINER="nexara-postgres-1"
DB_USER="nexara"
DB_NAME="nexara"

mkdir -p "${BACKUP_DIR}"

echo "==> Backing up ${DB_NAME} to ${BACKUP_DIR}/${FILENAME}"

docker compose exec -T postgres pg_dump \
  -U "${DB_USER}" \
  -d "${DB_NAME}" \
  --no-owner \
  --no-acl \
  -Fc \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

SIZE=$(du -h "${BACKUP_DIR}/${FILENAME}" | cut -f1)
echo "==> Backup complete: ${FILENAME} (${SIZE})"

# Prune backups older than 30 days
echo "==> Pruning backups older than 30 days..."
find "${BACKUP_DIR}" -name "nexara_*.sql.gz" -mtime +30 -delete 2>/dev/null || true

echo "==> Done."
