#!/usr/bin/env bash
# ops-worktrees sanity: prove the refusals hold and that archived work returns.
unset VIRTUAL_ENV
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== [ops-worktrees] sanity ==="
uv run --project "$SCRIPT_DIR" pytest "$SCRIPT_DIR/tests" -q || { echo "FAIL: tests"; exit 1; }

# The reaper must never propose deleting anything it cannot prove is landed.
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/worktree_lease.py" \
  --repo "${OPS_WORKTREES_REPO:-$HOME/workspace/experiments/agent-skills}" --json 2>/dev/null \
  | python3 -c '
import json, sys
r = json.load(sys.stdin)
assert "removed" in r and "archived" in r and "kept" in r, "three dispositions required"
assert r["apply"] is False, "a bare reap must be a preview"
print("preview: remove=%d archive=%d keep=%d of %d"
      % (len(r["removed"]), len(r["archived"]), len(r["kept"]), r["registered_total"]))
' || { echo "FAIL: reap preview"; exit 1; }

echo "ops-worktrees sanity passed"
