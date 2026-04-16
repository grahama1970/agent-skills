#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "pdf-lab sanity check..."

# Check pyproject.toml exists
if [ ! -f "$SCRIPT_DIR/pyproject.toml" ]; then
  echo "FAIL: pyproject.toml not found"
  exit 1
fi

# Check pdf_lab.py exists
if [ ! -f "$SCRIPT_DIR/pdf_lab.py" ]; then
  echo "FAIL: pdf_lab.py not found"
  exit 1
fi

# Test that python can import without errors
if ! uv run --project "$SCRIPT_DIR" python -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import pdf_lab" 2>/dev/null; then
  echo "FAIL: cannot import pdf_lab module"
  exit 1
fi

# Test help command via run.sh
if ! "$SCRIPT_DIR/run.sh" --help 2>&1 | grep -q "pdf-lab"; then
  echo "FAIL: run.sh --help did not show expected output"
  exit 1
fi

echo "PASS: pdf-lab sanity check"
exit 0
