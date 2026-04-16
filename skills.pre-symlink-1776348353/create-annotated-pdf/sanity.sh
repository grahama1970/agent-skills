#!/usr/bin/env bash
# Sanity check for create-annotated-pdf
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-annotated-pdf sanity check ==="

# 1. Check run.sh exists and is executable
echo "1/4 Checking run.sh..."
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not found or not executable"
    exit 1
fi

# 2. Check Python script exists
echo "2/4 Checking annotate_from_stem.py..."
if [[ ! -f "$SCRIPT_DIR/annotate_from_stem.py" ]]; then
    echo "FAIL: annotate_from_stem.py not found"
    exit 1
fi

# 3. Check Python imports (try global first, then script)
echo "3/4 Checking Python dependencies..."
python3 -c "import fitz; print('pymupdf OK')" 2>/dev/null || {
    echo "WARNING: pymupdf not available globally (script may install on first run)"
}

# 4. Check help/usage output
echo "4/4 Testing help output..."
"$SCRIPT_DIR/run.sh" --help > /dev/null 2>&1 || {
    echo "WARNING: --help flag not supported (script uses uv run --script)"
}

echo "create-annotated-pdf sanity check PASSED"
