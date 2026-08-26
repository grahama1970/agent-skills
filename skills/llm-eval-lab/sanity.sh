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

# Deterministic evaluators self-check (no network)
uv run python -c "
from evaluators import eval_json_output, eval_python_code
assert eval_json_output('{\"a\":1}', expected_keys={'a'})[0] == 3
assert eval_json_output('nope')[0] == 0
assert eval_python_code('x=1', 'assert x==1')[0] == 3
assert eval_python_code('x=1', 'assert x==2')[0] == 1
print('OK: deterministic evaluators')
"

# best-practices-react: interactive-element attribute coverage (data-qid CI gate)
if [ -d ui/src ]; then
  python3 ui/verify-data-qid.py
fi

echo "=== sanity passed ==="
