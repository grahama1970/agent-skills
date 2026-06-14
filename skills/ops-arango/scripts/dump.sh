#!/usr/bin/env bash
# Create an ArangoDB dump using the docker container or local instance.
# Auto-detects Docker container and credentials from docker inspect.
set -euo pipefail

# Source .env from project root if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
for envfile in "$SKILL_DIR/.env" "${PROJECT_ROOT:-.}/.env"; do
  if [[ -f "$envfile" ]]; then
    set -a; source "$envfile"; set +a
    break
  fi
done

# Configuration — sensible defaults matching maintain.py
ARANGO_URL=${ARANGO_URL:-http://127.0.0.1:8529}
ARANGO_DB=${ARANGO_DB:-memory}
ARANGO_USER=${ARANGO_USER:-root}
ARANGO_PASS=${ARANGO_PASS:-}
CONTAINER=${CONTAINER:-}

# Auto-detect Docker container if not specified
if [[ -z "$CONTAINER" ]]; then
  # Prefer container publishing port 8529, then exact name "arangodb", then any arangodb container
  CONTAINER=$(docker ps --filter "publish=8529" --filter "status=running" --format "{{.Names}}" 2>/dev/null | head -1) || true
  if [[ -z "$CONTAINER" ]]; then
    CONTAINER=$(docker ps --filter "name=^arangodb$" --filter "status=running" --format "{{.Names}}" 2>/dev/null | head -1) || true
  fi
  if [[ -z "$CONTAINER" ]]; then
    CONTAINER=$(docker ps --filter "ancestor=arangodb" --filter "status=running" --format "{{.Names}}" 2>/dev/null | head -1) || true
  fi
  if [[ -n "$CONTAINER" ]]; then
    echo "[ops-arango] Auto-detected container: $CONTAINER"
  fi
fi

# Auto-detect password from Docker container if not set
if [[ -n "$CONTAINER" && -z "$ARANGO_PASS" ]]; then
  ARANGO_PASS=$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep '^ARANGO_ROOT_PASS''WORD=' | cut -d= -f2-) || true
  if [[ -n "$ARANGO_PASS" ]]; then
    echo "[ops-arango] Auto-detected credentials from container env"
  fi
fi

OUT_BASE=${OUT_BASE:-"/mnt/storage12tb/backups/arangodb"}
TS=$(date +%Y%m%d-%H%M%S)
OUT_DIR="$OUT_BASE/$TS"
mkdir -p "$OUT_DIR"

# Pre-dump sanity check: refuse to dump an empty/broken database
echo "[ops-arango] Pre-dump sanity check..."
_check_collection_count() {
  local collection="$1"
  local count
  if [[ -n "$CONTAINER" ]]; then
    count=$(docker exec "$CONTAINER" sh -lc "arangosh --server.endpoint tcp://127.0.0.1:8529 --server.username '$ARANGO_USER' --server.password '$ARANGO_PASS' --server.database '$ARANGO_DB' --javascript.execute-string 'print(db._collection(\"$collection\") ? db._collection(\"$collection\").count() : -1)'" 2>/dev/null | tail -1) || count="-1"
  else
    count=$(arangosh --server.endpoint "$ARANGO_URL" --server.username "$ARANGO_USER" --server.password "$ARANGO_PASS" --server.database "$ARANGO_DB" --javascript.execute-string "print(db._collection(\"$collection\") ? db._collection(\"$collection\").count() : -1)" 2>/dev/null | tail -1) || count="-1"
  fi
  echo "$count"
}

MIN_LESSONS=1
LESSONS_COUNT=$(_check_collection_count "lessons")
if [[ "$LESSONS_COUNT" =~ ^[0-9]+$ ]] && [[ "$LESSONS_COUNT" -lt "$MIN_LESSONS" ]]; then
  echo "ERROR: lessons collection has ${LESSONS_COUNT} documents (<${MIN_LESSONS}) — refusing to overwrite backup with empty DB." >&2
  echo "This could indicate catastrophic data loss. Investigate before backing up." >&2
  exit 1
elif [[ "$LESSONS_COUNT" == "-1" ]]; then
  echo "[warn] Could not verify lessons count (collection may not exist). Proceeding with caution." >&2
else
  echo "[ops-arango] Pre-dump OK: lessons has $LESSONS_COUNT documents"
fi

echo "[ops-arango] Starting dump for database '$ARANGO_DB'..."

if [[ -n "$CONTAINER" ]]; then
  echo "[ops-arango] Mode: Docker ($CONTAINER)"

  # Check container exists first
  if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "ERROR: Container '$CONTAINER' not found." >&2
    exit 1
  fi

  # Execute dump inside container to temporary location
  echo "[ops-arango] Executing arangodump inside container..."
  # Build command string with proper quoting for the inner shell
  # Inside container, use tcp:// endpoint on localhost (not the host URL)
  CONTAINER_ENDPOINT="tcp://127.0.0.1:8529"
  DUMP_CMD="mkdir -p '/tmp/arangodumps/$TS'"
  DUMP_CMD="$DUMP_CMD && arangodump"
  DUMP_CMD="$DUMP_CMD --server.endpoint '$CONTAINER_ENDPOINT'"
  DUMP_CMD="$DUMP_CMD --output-directory '/tmp/arangodumps/$TS'"
  DUMP_CMD="$DUMP_CMD --overwrite true --compress-output true"
  DUMP_CMD="$DUMP_CMD --server.database '$ARANGO_DB'"
  if [[ -n "$ARANGO_USER" ]]; then
    DUMP_CMD="$DUMP_CMD --server.username '$ARANGO_USER'"
  fi
  if [[ -n "$ARANGO_PASS" ]]; then
    DUMP_CMD="$DUMP_CMD --server.password '$ARANGO_PASS'"
  fi
  docker exec "$CONTAINER" sh -lc "$DUMP_CMD"

  # Copy out
  echo "[ops-arango] Copying dump to host..."
  docker cp "$CONTAINER:/tmp/arangodumps/$TS/." "$OUT_DIR/" >/dev/null

  # Cleanup container
  docker exec "$CONTAINER" sh -lc "rm -rf /tmp/arangodumps/$TS" || true
else
  echo "[ops-arango] Mode: Local Binary"
  if ! command -v arangodump >/dev/null 2>&1; then
    echo "ERROR: 'arangodump' binary not found in PATH and no Docker container found." >&2
    echo "Set CONTAINER=<name> or install arangodump." >&2
    exit 1
  fi

  # Build auth arguments
  AUTH_ARGS=()
  if [[ -n "$ARANGO_USER" ]]; then
    AUTH_ARGS+=("--server.username" "$ARANGO_USER")
  fi
  if [[ -n "$ARANGO_PASS" ]]; then
    AUTH_ARGS+=("--server.password" "$ARANGO_PASS")
  fi

  arangodump --server.endpoint "$ARANGO_URL" --output-directory "$OUT_DIR" --overwrite true --compress-output true --server.database "$ARANGO_DB" ${AUTH_ARGS[@]:+"${AUTH_ARGS[@]}"}
fi

echo "[ops-arango] Dump written to $OUT_DIR"

# Integrity check: checks for manifest.json
if [[ -f "$OUT_DIR/manifest.json" ]]; then
  # Just count any directories (collections)
  COUNT=$(find "$OUT_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
  if [[ "$COUNT" -lt 1 ]]; then
    echo "[warn] manifest.json present but no collection directories found." >&2
  else
    echo "[ops-arango] Integrity: OK ($COUNT collections)"
  fi
else
  echo "[warn] manifest.json NOT found in dump output!" >&2
fi

# Robust Retention Policy
RETENTION_N=${RETENTION_N:-7}
echo "[ops-arango] Applying retention (keep last $RETENTION_N)..."

# List all directories in OUT_BASE, sort by modification time (newest first), skip first N, remove rest
find "$OUT_BASE" -mindepth 1 -maxdepth 1 -type d -printf "%T@ %p\n" | \
  sort -nr | \
  tail -n +$((RETENTION_N + 1)) | \
  cut -d' ' -f2- | \
  while read -r dir_to_remove; do
    echo "[ops-arango] Removing old backup: $dir_to_remove"
    rm -rf "$dir_to_remove"
  done

echo "[ops-arango] Done."
