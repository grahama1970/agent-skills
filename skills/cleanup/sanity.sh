#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/cleanup-skill-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/cleanup-skill-pycache}"
echo "=== Cleanup Skill Sanity ==="
[[ -f "$SCRIPT_DIR/SKILL.md" ]] && echo "  [PASS] SKILL.md exists" || { echo "  [FAIL] SKILL.md missing"; exit 1; }
[[ -f "$SCRIPT_DIR/cleanup.py" ]] && echo "  [PASS] cleanup.py exists" || { echo "  [FAIL] cleanup.py missing"; exit 1; }
# Syntax check
uv run --project "$SCRIPT_DIR" python -m py_compile "$SCRIPT_DIR/cleanup.py" \
  && echo "  [PASS] cleanup.py compiles" || { echo "  [FAIL] cleanup.py syntax error"; exit 1; }
# CLI smoke
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/cleanup.py" --help > /dev/null 2>&1 \
  && echo "  [PASS] --help works" || { echo "  [FAIL] --help failed"; exit 1; }
# Behavioral safety checks include positive candidate discovery, negative
# runtime-dependency controls, ingest preconditions, and forbidden mutation.
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/test_cleanup.py" \
  && echo "  [PASS] behavioral safety checks" \
  || { echo "  [FAIL] behavioral safety checks"; exit 1; }
echo "Result: PASS"
