#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== monitor-pi sanity ==="

# 1. Python parses cleanly
uv run --project "$SCRIPT_DIR" python -c "import ast; ast.parse(open('$SCRIPT_DIR/monitor.py').read()); print('  parse: OK')"

# 2. Imports resolve
uv run --project "$SCRIPT_DIR" python -c "from monitor import run_health_check, HealthReport; print('  imports: OK')"

# 3. One-shot check runs (may report unhealthy — that's fine)
output=$("$SCRIPT_DIR/run.sh" check --json 2>/dev/null || true)
if echo "$output" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    echo "  check --json: OK (valid JSON)"
else
    echo "  check --json: FAIL (invalid JSON output)"
    exit 1
fi

echo "=== monitor-pi sanity PASSED ==="
