#!/usr/bin/env bash
# Sanity check for /code-runner
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== /code-runner sanity check ==="

# 1. run.sh exists and is executable
[[ -x "$SCRIPT_DIR/run.sh" ]] || { echo "FAIL: run.sh not executable"; exit 1; }
echo "PASS: run.sh executable"

# 2. code_runner.py imports
python3 "$SCRIPT_DIR/code_runner.py" --help > /dev/null 2>&1 || { echo "FAIL: code_runner.py --help failed"; exit 1; }
echo "PASS: code_runner.py imports OK"

# 3. dry-run works with a test spec
cat > /tmp/code-runner-sanity-spec.json << 'EOF'
{
  "task_id": "sanity",
  "title": "Sanity test",
  "prompt": "echo hello",
  "backend": "text",
  "cwd": "/tmp",
  "definition_of_done": {"command": "echo OK", "assertion": "OK"}
}
EOF
python3 "$SCRIPT_DIR/code_runner.py" dry-run /tmp/code-runner-sanity-spec.json > /dev/null 2>&1 || { echo "FAIL: dry-run failed"; exit 1; }
echo "PASS: dry-run works"

# 4. Stress test: multi-round recovery (fail → fix → pass)
python3 "$SCRIPT_DIR/stress_test.py" > /dev/null 2>&1 || { echo "FAIL: stress test (multi-round recovery) failed"; python3 "$SCRIPT_DIR/stress_test.py" 2>&1; exit 1; }
echo "PASS: stress test (multi-round recovery)"

# 5. Full stress tests: 12 scenarios (code gen, compliance, preflight, allowlist, etc.)
python3 "$SCRIPT_DIR/stress_tests.py" > /dev/null 2>&1 || { echo "FAIL: full stress tests failed"; python3 "$SCRIPT_DIR/stress_tests.py" 2>&1; exit 1; }
echo "PASS: full stress tests (12 scenarios)"

echo "=== ALL PASSED ==="
