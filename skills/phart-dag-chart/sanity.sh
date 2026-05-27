#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== /phart-dag-chart sanity ==="
FAIL=0

if ! command -v uv >/dev/null 2>&1; then
  echo "SKIP: uv not installed"
  exit 0
fi

echo "1. validate fixture (positive)..."
if ./run.sh validate tests/fixtures/memory-fanout.dag.json; then
  echo "   PASS"
else
  echo "   FAIL"
  FAIL=1
fi

echo "2. validate duplicate id (negative)..."
neg_out=$(./run.sh validate tests/fixtures/duplicate-id.dag.json 2>&1) || true
if echo "$neg_out" | grep -qi 'duplicated'; then
  echo "   PASS"
else
  echo "   FAIL: expected duplicated error, got: $neg_out"
  FAIL=1
fi

echo "3. chart fixture (boxed output)..."
out=$(./run.sh chart tests/fixtures/memory-fanout.dag.json)
if echo "$out" | grep -q memory_a && echo "$out" | grep -qE '(┌|\[)'; then
  echo "   PASS"
else
  echo "   FAIL"
  FAIL=1
fi

echo "4. pytest..."
if uv run --project "$SCRIPT_DIR" pytest -q; then
  echo "   PASS"
else
  echo "   FAIL"
  FAIL=1
fi

exit "$FAIL"
