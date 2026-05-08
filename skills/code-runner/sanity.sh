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

# 2b. Codex defaults to gpt-5.5 high reasoning
grep -q '"codex": "gpt-5.5"' "$SCRIPT_DIR/code_runner.py" || { echo "FAIL: codex model is not gpt-5.5"; exit 1; }
grep -q '\["codex", "high"\]' "$SCRIPT_DIR/code_runner.py" || { echo "FAIL: codex does not start at high reasoning"; exit 1; }
grep -q '"codex": "gpt-5.5"' "$SCRIPT_DIR/diagnose.py" || { echo "FAIL: diagnose codex model is not gpt-5.5"; exit 1; }
echo "PASS: Codex defaults to gpt-5.5 high reasoning"

# 3. SCILLM_API_BASE normalization accepts base URL, /v1 URL, and full endpoint
python3 - "$SCRIPT_DIR" << 'PY' || { echo "FAIL: SCILLM_API_BASE normalization failed"; exit 1; }
import sys

sys.path.insert(0, sys.argv[1])
import code_runner
import diagnose
import logact_recovery
import tool_use

expected = "http://localhost:4001/v1/chat/completions"
for module in (code_runner, diagnose, logact_recovery, tool_use):
    normalize = module.normalize_scillm_chat_url
    assert normalize("http://localhost:4001") == expected
    assert normalize("http://localhost:4001/") == expected
    assert normalize("http://localhost:4001/v1") == expected
    assert normalize(expected) == expected
    custom = "http://localhost:4001/custom"
    assert normalize(custom) == custom
PY
echo "PASS: SCILLM_API_BASE normalization works"

# 4. dry-run works with a test spec
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

# 5. Stress test: multi-round recovery (fail → fix → pass)
python3 "$SCRIPT_DIR/stress_test.py" > /dev/null 2>&1 || { echo "FAIL: stress test (multi-round recovery) failed"; python3 "$SCRIPT_DIR/stress_test.py" 2>&1; exit 1; }
echo "PASS: stress test (multi-round recovery)"

# 6. Full stress tests: 12 scenarios (code gen, compliance, preflight, allowlist, etc.)
python3 "$SCRIPT_DIR/stress_tests.py" > /dev/null 2>&1 || { echo "FAIL: full stress tests failed"; python3 "$SCRIPT_DIR/stress_tests.py" 2>&1; exit 1; }
echo "PASS: full stress tests (12 scenarios)"

echo "=== ALL PASSED ==="
