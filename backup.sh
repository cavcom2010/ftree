#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-$ROOT/venv/bin/python}"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
BACKUP_ROOT="${BACKUP_DIR:-$ROOT/.production/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.production}"
export DJANGO_SETTINGS_MODULE

print_usage() {
  cat <<'EOF'
Usage: ./backup.sh

Creates a production backup containing:
  - PostgreSQL custom-format dump: database.dump
  - Uploaded media archive when media files exist: media.tar.gz
  - Metadata and checksums

Environment:
  ENV_FILE=/path/to/.env
  PYTHON_BIN=/path/to/python
  BACKUP_DIR=/path/to/backups
  RETENTION_DAYS=30          Set to 0 to disable pruning.
  BACKUP_AFTER_HOOK=/path/to/script
  DJANGO_SETTINGS_MODULE=config.settings.production
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_usage
  exit 0
fi

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

[[ -x "$PYTHON_BIN" ]] || die "Missing Python interpreter at $PYTHON_BIN"
[[ -f "$ENV_FILE" ]] || die "Missing environment file at $ENV_FILE"
[[ -f "$ROOT/manage.py" ]] || die "Cannot find manage.py in $ROOT"
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || die "RETENTION_DAYS must be a non-negative integer"

require_command pg_dump
require_command pg_restore
require_command tar
require_command sha256sum
require_command find
require_command flock

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

[[ -n "${DATABASE_URL:-}" ]] || die "DATABASE_URL is required for production backups"
case "$DATABASE_URL" in
  postgres://*|postgresql://*) ;;
  *) die "DATABASE_URL must be a PostgreSQL URL" ;;
esac

mkdir -p "$BACKUP_ROOT"

LOCK_FILE="$BACKUP_ROOT/.backup.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  die "Another backup is already running"
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
HOSTNAME_VALUE="$(hostname 2>/dev/null || echo unknown)"
BACKUP_NAME="${TIMESTAMP}-${RELEASE_VERSION}"
FINAL_DIR="$BACKUP_ROOT/$BACKUP_NAME"
TMP_DIR="$BACKUP_ROOT/.tmp-${BACKUP_NAME}-$$"

[[ ! -e "$FINAL_DIR" ]] || die "Backup directory already exists: $FINAL_DIR"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

cleanup() {
  local exit_code=$?
  if [[ "$exit_code" -ne 0 ]]; then
    rm -rf "$TMP_DIR"
  fi
}
trap cleanup EXIT

echo "Creating production backup ${BACKUP_NAME}..."

DATABASE_DUMP="$TMP_DIR/database.dump"
MEDIA_ARCHIVE="$TMP_DIR/media.tar.gz"
METADATA_FILE="$TMP_DIR/metadata.env"
CHECKSUM_FILE="$TMP_DIR/sha256sums.txt"

echo "Dumping PostgreSQL database..."
pg_dump \
  --dbname="$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="$DATABASE_DUMP"

echo "Validating database dump..."
pg_restore --list "$DATABASE_DUMP" >/dev/null

MEDIA_ROOT="$(
  "$PYTHON_BIN" manage.py shell -c "from django.conf import settings; print(settings.MEDIA_ROOT)"
)"
MEDIA_INCLUDED=0
MEDIA_SAMPLE=""
if [[ -d "$MEDIA_ROOT" ]]; then
  MEDIA_SAMPLE="$(find "$MEDIA_ROOT" -type f -print -quit)"
fi
if [[ -n "$MEDIA_SAMPLE" ]]; then
  echo "Archiving uploaded media..."
  tar -czf "$MEDIA_ARCHIVE" -C "$(dirname "$MEDIA_ROOT")" "$(basename "$MEDIA_ROOT")"
  MEDIA_INCLUDED=1
else
  echo "No uploaded media files found; skipping media archive."
fi

cat > "$METADATA_FILE" <<EOF
created_at_utc="$TIMESTAMP"
host="$HOSTNAME_VALUE"
root="$ROOT"
release="$RELEASE_VERSION"
django_settings_module="$DJANGO_SETTINGS_MODULE"
database_dump="database.dump"
media_archive="$([[ "$MEDIA_INCLUDED" == "1" ]] && echo "media.tar.gz" || echo "")"
retention_days="$RETENTION_DAYS"
EOF

echo "Writing checksums..."
(
  cd "$TMP_DIR"
  if [[ "$MEDIA_INCLUDED" == "1" ]]; then
    sha256sum database.dump media.tar.gz metadata.env
  else
    sha256sum database.dump metadata.env
  fi
) > "$CHECKSUM_FILE"

mv "$TMP_DIR" "$FINAL_DIR"

if [[ "$RETENTION_DAYS" -gt 0 ]]; then
  echo "Pruning backups older than ${RETENTION_DAYS} day(s)..."
  find "$BACKUP_ROOT" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -name '20*T*Z-*' \
    -mtime +"$RETENTION_DAYS" \
    -exec rm -rf {} +
else
  echo "Backup pruning disabled."
fi

if [[ -n "${BACKUP_AFTER_HOOK:-}" ]]; then
  [[ -x "$BACKUP_AFTER_HOOK" ]] || die "BACKUP_AFTER_HOOK is not executable: $BACKUP_AFTER_HOOK"
  echo "Running backup hook..."
  "$BACKUP_AFTER_HOOK" "$FINAL_DIR"
fi

echo "Backup complete: $FINAL_DIR"
echo "Verify with: cd '$FINAL_DIR' && sha256sum -c sha256sums.txt && pg_restore --list database.dump >/dev/null"
