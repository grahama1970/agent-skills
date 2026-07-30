#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/cleanup-skill-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/cleanup-skill-pycache}"
echo "=== Cleanup Skill Sanity ==="
[[ -f "$SCRIPT_DIR/SKILL.md" ]] && echo "  [PASS] SKILL.md exists" || { echo "  [FAIL] SKILL.md missing"; exit 1; }
[[ -f "$SCRIPT_DIR/cleanup.py" ]] && echo "  [PASS] cleanup.py exists" || { echo "  [FAIL] cleanup.py missing"; exit 1; }
# Syntax check
uv run --project "$SCRIPT_DIR" python -m py_compile \
  "$SCRIPT_DIR/cleanup.py" "$SCRIPT_DIR/cleanup_core.py" "$SCRIPT_DIR/cleanup_watchdog.py" \
  "$SCRIPT_DIR/cleanup_worktree.py" "$SCRIPT_DIR/cleanup_evidence.py" \
  "$SCRIPT_DIR/cleanup_docs.py" "$SCRIPT_DIR/cleanup_bp.py" \
  && echo "  [PASS] all cleanup modules compile" || { echo "  [FAIL] cleanup module syntax error"; exit 1; }
# Every module stays under the 800-line rule from /best-practices-python.
OVERSIZE=""
for f in "$SCRIPT_DIR"/cleanup*.py "$SCRIPT_DIR"/test_cleanup*.py; do
  [[ -f "$f" ]] || continue
  n=$(wc -l < "$f")
  if [[ "$n" -gt 800 ]]; then OVERSIZE="$OVERSIZE $(basename "$f"):$n"; fi
done
if [[ -z "$OVERSIZE" ]]; then
  echo "  [PASS] no module exceeds 800 lines"
else
  echo "  [FAIL] files over 800 lines:$OVERSIZE"; exit 1
fi
# CLI smoke
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/cleanup.py" --help > /dev/null 2>&1 \
  && echo "  [PASS] --help works" || { echo "  [FAIL] --help failed"; exit 1; }
# Behavioral safety checks include positive candidate discovery, negative
# runtime-dependency controls, ingest preconditions, and forbidden mutation.
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/test_cleanup.py" \
  && echo "  [PASS] behavioral safety checks" \
  || { echo "  [FAIL] behavioral safety checks"; exit 1; }
echo "Result: PASS"
