#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "=== Cleanup Skill Sanity ==="
[[ -f "$SCRIPT_DIR/SKILL.md" ]] && echo "  [PASS] SKILL.md exists" || { echo "  [FAIL] SKILL.md missing"; exit 1; }
[[ -f "$SCRIPT_DIR/cleanup.py" ]] && echo "  [PASS] cleanup.py exists" || { echo "  [FAIL] cleanup.py missing"; exit 1; }
# Syntax check
uv run --project "$SCRIPT_DIR" python -m py_compile "$SCRIPT_DIR/cleanup.py" \
  && echo "  [PASS] cleanup.py compiles" || { echo "  [FAIL] cleanup.py syntax error"; exit 1; }
# CLI smoke
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/cleanup.py" --help > /dev/null 2>&1 \
  && echo "  [PASS] --help works" || { echo "  [FAIL] --help failed"; exit 1; }
echo "Result: PASS"
