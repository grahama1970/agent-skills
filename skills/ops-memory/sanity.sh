#!/usr/bin/env bash
# ops-memory sanity gate: behavioral + SAFETY (boundary) acceptance checks.
# Offline-safe: does not require live Arango/Qdrant. The live E2E path is
# sanity-e2e.sh (opt-in), which calls the real downstream skills.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/scripts/ops_memory.py"
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

echo "[2/6] SAFETY: no direct ArangoDB/Qdrant access (must compose owning skills)"
if grep -nE 'from arango import|ArangoClient|import qdrant|QdrantClient' "$SRC"; then
    echo "FAIL: ops-memory must never open Arango/Qdrant directly — compose ops-arango/ops-qdrant"; fail=1
fi
if grep -nE 'sys\.path\.(insert|append)' "$SRC"; then
    echo "FAIL: sys.path surgery is forbidden (packaging-no-sys-path-surgery)"; fail=1
fi
if grep -nE '\b(exec|eval)\(' "$SRC"; then
    echo "FAIL: dynamic exec/eval is forbidden"; fail=1
fi
[ "$fail" -eq 0 ] && note "ok — no direct DB clients, no path surgery, no dynamic exec"

echo "[3/6] SAFETY: subprocess composition never uses shell=True"
if grep -nE 'shell\s*=\s*True' "$SRC"; then
    echo "FAIL: subprocess shell=True is forbidden (security-subprocess-no-shell-true)"; fail=1
else
    note "ok — children invoked with argument lists only"
fi

echo "[4/6] POSITIVE-CONTROL: topology --json emits a valid ask.dag.v1 graph (offline)"
DAG="$("$SCRIPT_DIR/run.sh" topology --json 2>/dev/null)"
if ! echo "$DAG" | jq -e '.schema_version == "ask.dag.v1" and (.nodes|length > 0)' >/dev/null 2>&1; then
    echo "FAIL: topology --json did not emit ask.dag.v1 nodes"; echo "$DAG" | head -3; fail=1
else
    note "ok — $(echo "$DAG" | jq '.nodes|length') stack nodes"
fi

echo "[5/6] POSITIVE-CONTROL: config doctor --json emits readiness + child map (offline)"
DOC="$("$SCRIPT_DIR/run.sh" config doctor --json 2>/dev/null)"
if ! echo "$DOC" | jq -e '.schema == "ops_memory.config_doctor.v1" and has("readiness") and has("children") and has("needs_attention")' >/dev/null 2>&1; then
    echo "FAIL: config doctor did not emit the readiness contract"; echo "$DOC" | head -3; fail=1
else
    note "ok — readiness=$(echo "$DOC" | jq -r .readiness)"
fi

echo "[6/6] NEGATIVE-CONTROL: bogus SKILLS_ROOT -> missing children, fails to USABLE_WITH_GAPS"
NEG="$(SKILLS_ROOT=/nonexistent-skills-root "$SCRIPT_DIR/run.sh" config doctor --json 2>/dev/null)"
if ! echo "$NEG" | jq -e '.readiness == "USABLE_WITH_GAPS" and ([.needs_attention[].reason] | map(startswith("missing_child")) | any)' >/dev/null 2>&1; then
    echo "FAIL: missing children were not reported as needs_attention"; echo "$NEG" | head -5; fail=1
else
    note "ok — degrades and reports missing children instead of claiming READY"
fi

if [ "$fail" -ne 0 ]; then echo "SANITY: FAIL"; exit 1; fi
echo "SANITY: PASS"
