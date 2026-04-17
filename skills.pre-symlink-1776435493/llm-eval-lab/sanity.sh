#!/bin/bash
# Sanity check for llm-eval-lab
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== llm-eval-lab sanity ==="

# Check imports resolve
uv run python -c "
import sys
sys.path.insert(0, '.')
from eval_app import app, console
print('OK: eval_app imports')
"

# Check CLI help works
uv run python llm_eval_lab.py --help | head -5
echo ""

# Check models command
uv run python llm_eval_lab.py models 2>/dev/null | head -3 || echo "WARN: models command failed (may need API keys)"

echo "=== sanity passed ==="
