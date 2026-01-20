#!/usr/bin/env bash
# Create an ArangoDB dump using the docker container or local instance.
# ROBUST VERSION: Requires explicit CONTAINER env var if using Docker.
set -euo pipefail

# Configuration
ARANGO_URL=${ARANGO_URL:-http://127.0.0.1:8529}
ARANGO_DB=${ARANGO_DB:-_system}
ARANGO_USER=${ARANGO_USER:-}
ARANGO_PASS=${ARANGO_PASS:-}
# CONTAINER must be set to use Docker. No auto-guessing.
CONTAINER=${CONTAINER:-}

OUT_BASE=${OUT_BASE:-"$HOME/.local/state/devops-agent/arangodumps"}
TS=$(date +%Y%m%d-%H%M%S)
OUT_DIR="$OUT_BASE/$TS"
mkdir -p "$OUT_DIR"

# Build auth arguments
AUTH_ARGS=()
if [[ -n "$ARANGO_USER" ]]; then
  AUTH_ARGS+=("--server.username" "$ARANGO_USER")
fi
if [[ -n "$ARANGO_PASS" ]]; then
  AUTH_ARGS+=("--server.password" "$ARANGO_PASS")
fi

echo "[arango-ops] Starting dump for database '$ARANGO_DB'..."

if [[ -n "$CONTAINER" ]]; then
  echo "[arango-ops] Mode: Docker ($CONTAINER)"
  
  # Check container exists first
  if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "ERROR: Container '$CONTAINER' not found." >&2
    exit 1
  fi

  # Execute dump inside container to temporary location
  echo "[arango-ops] Executing arangodump inside container..."
  docker exec "$CONTAINER" sh -lc \
    "mkdir -p /tmp/arangodumps/$TS && arangodump --server.endpoint $ARANGO_URL --output-directory /tmp/arangodumps/$TS --overwrite true --compress-output true --server.database $ARANGO_DB ${AUTH_ARGS[@]+\"${AUTH_ARGS[@]}\"}"
  
  # Copy out
  echo "[arango-ops] Copying dump to host..."
  docker cp "$CONTAINER:/tmp/arangodumps/$TS/." "$OUT_DIR/" >/dev/null
  
  # Cleanup container
  docker exec "$CONTAINER" sh -lc "rm -rf /tmp/arangodumps/$TS" || true
else
  echo "[arango-ops] Mode: Local Binary"
  if ! command -v arangodump >/dev/null 2>&1; then
    echo "ERROR: 'arangodump' binary not found in PATH." >&2
    exit 1
  fi
  
  arangodump --server.endpoint "$ARANGO_URL" --output-directory "$OUT_DIR" --overwrite true --compress-output true --server.database "$ARANGO_DB" ${AUTH_ARGS[@]:+"${AUTH_ARGS[@]}"}
fi

echo "[arango-ops] Dump written to $OUT_DIR"

# Integrity check: checks for manifest.json
if [[ -f "$OUT_DIR/manifest.json" ]]; then
  # Just count any directories (collections)
  COUNT=$(find "$OUT_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
  if [[ "$COUNT" -lt 1 ]]; then
    echo "[warn] manifest.json present but no collection directories found." >&2
  else
    echo "[arango-ops] Integrity: OK ($COUNT collections)"
  fi
else
  echo "[warn] manifest.json NOT found in dump output!" >&2
fi

# Robust Retention Policy
RETENTION_N=${RETENTION_N:-7}
echo "[arango-ops] Applying retention (keep last $RETENTION_N)..."

# List all directories in OUT_BASE, sort by modification time (newest first), skip first N, remove rest
# Uses stat to get mtime for reliability over filenames
find "$OUT_BASE" -mindepth 1 -maxdepth 1 -type d -printf "%T@ %p\n" | \
  sort -nr | \
  tail -n +$((RETENTION_N + 1)) | \
  cut -d' ' -f2- | \
  while read -r dir_to_remove; do
    echo "[arango-ops] Removing old backup: $dir_to_remove"
    rm -rf "$dir_to_remove"
  done

echo "[arango-ops] Done."
