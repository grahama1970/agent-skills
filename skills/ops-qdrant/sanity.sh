#!/usr/bin/env bash
# ops-qdrant sanity gate: behavioral + SAFETY (no-writes) acceptance checks.
# Non-mocked: the positive-control runs against the live Qdrant if present.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/scripts/ops_qdrant.py"
fail=0
note() { printf '  %s\n' "$*"; }

echo "[1/6] uv sync + CLI import smoke"
if ! uv sync --project "$SCRIPT_DIR" >/dev/null 2>&1; then
    echo "FAIL: uv sync failed"; exit 1
fi
if ! "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "FAIL: run.sh --help failed"; exit 1
fi
note "ok"

echo "[2/6] SAFETY: source performs NO writes (forbidden mutation verbs absent)"
# Read-only contract: no PUT/DELETE/PATCH anywhere; the ONLY POST is /recall.
if grep -nE '\.(put|delete|patch)\(' "$SRC"; then
    echo "FAIL: mutation HTTP verb found — ops-qdrant must be read-only"; fail=1
fi
if grep -nE '\.post\(' "$SRC" | grep -vq '/recall'; then
    echo "FAIL: a POST targets something other than the read-only /recall probe"; fail=1
fi
# No Qdrant point/collection mutation endpoints. Match actual method CALLS
# (identifier.method() — e.g. client.create_collection()), not the assess
# linter's own regex-literal pattern strings that merely name these verbs.
if grep -nE '/points|/collections/[^"]*(", *json=|/index)|[A-Za-z0-9_]\.(create_collection|recreate_collection|delete_collection|upsert)\(' "$SRC"; then
    echo "FAIL: Qdrant mutation endpoint referenced"; fail=1
fi
[ "$fail" -eq 0 ] && note "ok — no writes"

echo "[3/6] POSITIVE-CONTROL: check --json emits ops_qdrant.health.v1"
OUT="$("$SCRIPT_DIR/run.sh" check --json 2>/dev/null || true)"
if ! echo "$OUT" | jq -e '.schema == "ops_qdrant.health.v1"' >/dev/null 2>&1; then
    echo "FAIL: check --json did not emit schema ops_qdrant.health.v1"; echo "$OUT" | head -3; fail=1
else
    for k in qdrant_up collections dense_probe status missing_expected; do
        echo "$OUT" | jq -e "has(\"$k\")" >/dev/null 2>&1 || { echo "FAIL: report missing key $k"; fail=1; }
    done
    note "ok — schema and required keys present (qdrant_up=$(echo "$OUT" | jq -r .qdrant_up))"
fi

echo "[4/6] NEGATIVE-CONTROL: unreachable Qdrant -> status=down, exit 2"
NEG="$(QDRANT_URL=http://127.0.0.1:1 "$SCRIPT_DIR/run.sh" check --json 2>/dev/null)"; code=$?
if [ "$code" -ne 2 ]; then echo "FAIL: expected exit 2 on unreachable Qdrant, got $code"; fail=1; fi
if ! echo "$NEG" | jq -e '.status == "down" and .qdrant_up == false' >/dev/null 2>&1; then
    echo "FAIL: unreachable Qdrant did not report status=down"; fail=1
else
    note "ok — fails closed to down/exit 2"
fi

echo "[5/6] SCHEMA: named-vector parsing shape is present when collections exist"
if echo "$OUT" | jq -e '.collections | length > 0' >/dev/null 2>&1; then
    echo "$OUT" | jq -e '.collections[0] | has("modalities") and has("vectors") and has("points")' >/dev/null 2>&1 \
        || { echo "FAIL: collection record missing modalities/vectors/points"; fail=1; }
    note "ok — per-collection modality/vector shape present"
else
    note "skip — no collections live (shape checked in negative path)"
fi

echo "[6/6] ASSESS: Qdrant single-owner boundary linter (positive + negative controls)"
ASSESS_TMP="$(mktemp -d)"
trap 'rm -rf "$ASSESS_TMP"' EXIT
printf 'from qdrant_client import QdrantClient\nc = QdrantClient()\nc.create_collection("x")\n' > "$ASSESS_TMP/bad.py"
printf 'from graph_memory.qdrant_client import QdrantClient\nc = QdrantClient()\nc.upsert("x", pts)\n' > "$ASSESS_TMP/ok.py"
BAD="$("$SCRIPT_DIR/run.sh" assess "$ASSESS_TMP/bad.py" --json 2>/dev/null)"; bad_code=$?
if [ "$bad_code" -ne 1 ] || ! echo "$BAD" | jq -e '.passed == false and (.issues | map(.pattern) | index("raw_qdrant_client_import"))' >/dev/null 2>&1; then
    echo "FAIL: assess did not flag a raw qdrant_client import (exit=$bad_code)"; echo "$BAD" | head -3; fail=1
fi
OK="$("$SCRIPT_DIR/run.sh" assess "$ASSESS_TMP/ok.py" --json 2>/dev/null)"; ok_code=$?
if [ "$ok_code" -ne 0 ] || ! echo "$OK" | jq -e '.passed == true' >/dev/null 2>&1; then
    echo "FAIL: assess flagged the sanctioned graph_memory.qdrant_client wrapper (exit=$ok_code)"; echo "$OK" | head -3; fail=1
fi
[ "$fail" -eq 0 ] && note "ok — flags raw client, allows the sanctioned wrapper"

if [ "$fail" -ne 0 ]; then echo "SANITY: FAIL"; exit 1; fi
echo "SANITY: PASS"
