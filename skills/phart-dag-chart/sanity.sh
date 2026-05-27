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

echo "1. validate fixture..."
if ./run.sh validate tests/fixtures/memory-fanout.dag.json; then
  echo "   PASS"
else
  echo "   FAIL"
  FAIL=1
fi

echo "2. chart fixture (boxed output)..."
if ./run.sh chart tests/fixtures/memory-fanout.dag.json | grep -q memory_a; then
  echo "   PASS"
else
  echo "   FAIL"
  FAIL=1
fi

echo "3. pytest..."
if uv run --directory "$SCRIPT_DIR" pytest -q; then
  echo "   PASS"
else
  echo "   FAIL"
  FAIL=1
fi

exit "$FAIL"
