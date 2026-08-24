#!/usr/bin/env bash
# ops-memory LIVE E2E gate (opt-in). Calls the REAL downstream skills
# (ops-arango, ops-qdrant, memory, phart-dag-chart) and fails closed when a
# required downstream receipt is missing or its typed seam does not validate.
# This is NOT a mock: it reads back the merged health/metrics artifacts.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0
note() { printf '  %s\n' "$*"; }

echo "[1/5] LIVE: health --json merges ops-arango + ops-qdrant and stamps a seam receipt"
H="$("$SCRIPT_DIR/run.sh" health --json 2>/dev/null)"
if ! echo "$H" | jq -e '.schema == "ops_memory.health.v1" and .seam_validation.status == "PASS" and has("arango") and has("qdrant")' >/dev/null 2>&1; then
    echo "FAIL: health did not merge both lanes with a PASS seam receipt"; echo "$H" | head -5; fail=1
else
    note "ok — status=$(echo "$H" | jq -r .status) arango_up=$(echo "$H" | jq -r .arango.up) qdrant_up=$(echo "$H" | jq -r .qdrant.up)"
fi

echo "[2/5] LIVE: metrics --json returns a per-collection matrix with flag counts"
M="$("$SCRIPT_DIR/run.sh" metrics --json 2>/dev/null)"
if ! echo "$M" | jq -e '.schema == "ops_memory.metrics.v1" and .seam_validation.status == "PASS" and (.collections|length > 0) and has("flag_counts")' >/dev/null 2>&1; then
    echo "FAIL: metrics did not return a validated per-collection matrix"; echo "$M" | head -5; fail=1
else
    note "ok — $(echo "$M" | jq '.collections|length') collections, flags=$(echo "$M" | jq -c .flag_counts)"
fi

echo "[3/5] LIVE: metrics rows carry the monitoring fields the matrix promises"
if ! echo "$M" | jq -e '.collections[0] | has("count") and has("index_types") and has("vector_pointer_frac") and has("flags")' >/dev/null 2>&1; then
    echo "FAIL: collection rows are missing count/index_types/vector_pointer_frac/flags"; fail=1
else
    note "ok — rows expose counts, indexes, sync fraction, and flags"
fi

echo "[4/5] LIVE: topology --chart renders ASCII via phart-dag-chart"
C="$("$SCRIPT_DIR/run.sh" topology --chart 2>/dev/null)"
if ! echo "$C" | grep -q "memory-stack"; then
    echo "FAIL: phart-dag-chart did not render the stack topology"; echo "$C" | head -5; fail=1
else
    note "ok — phart rendered the stack"
fi

echo "[5/5] LIVE: backups --json reports the 12TB backup directory"
B="$("$SCRIPT_DIR/run.sh" backups --json 2>/dev/null)"
if ! echo "$B" | jq -e '.schema == "ops_memory.backups.v1" and (.backup_dir | test("/mnt/storage12tb"))' >/dev/null 2>&1; then
    echo "FAIL: backups did not report the 12TB retention directory"; echo "$B" | head -5; fail=1
else
    note "ok — backup_dir=$(echo "$B" | jq -r .backup_dir) count=$(echo "$B" | jq -r .count)"
fi

if [ "$fail" -ne 0 ]; then echo "E2E: FAIL"; exit 1; fi
echo "E2E: PASS"
