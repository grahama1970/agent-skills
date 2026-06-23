#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${OUT_DIR:-/tmp/personaplex-p6-p7-p8-sanity}"
MEMORY_URL="${PERSONAPLEX_MEMORY_URL:-${MEMORY_URL:-http://127.0.0.1:8601}}"
REQUIRE_ARGS=()
if [[ "${PERSONAPLEX_REQUIRE_REAL:-0}" == "1" ]]; then
  REQUIRE_ARGS+=(--require-real)
fi
mkdir -p "$OUT_DIR"
PYTHONPATH="$ROOT/skills/personaplex/scripts:${PYTHONPATH:-}" \
python3 "$ROOT/skills/personaplex/scripts/personaplex_p6_real_memory_upsert_probe.py" \
  --out-dir "$OUT_DIR" \
  --memory-url "$MEMORY_URL" \
  "${REQUIRE_ARGS[@]}"
