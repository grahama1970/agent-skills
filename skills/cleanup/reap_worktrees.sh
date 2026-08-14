#!/usr/bin/env bash
# Scheduled worktree reclamation. The piece that was missing: cleanup_worktree.py
# and audit-worktrees.sh both classify, neither removes, and no cron ran either
# of them -- so the count could only ever go up.
#
# Preview by default. Set WORKTREE_REAP_APPLY=1 to actually remove.
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${1:-$HOME/workspace/experiments/agent-skills}"
LOG="${WORKTREE_REAP_LOG:-$HOME/.cleanup/worktree-reap.jsonl}"
mkdir -p "$(dirname "$LOG")"

APPLY=""
[ "${WORKTREE_REAP_APPLY:-0}" = "1" ] && APPLY="--apply"

RECEIPT="$(uv run --project "$SKILL_DIR" python "$SKILL_DIR/worktree_lease.py" \
  --repo "$REPO" $APPLY --json 2>/dev/null)"
[ -n "$RECEIPT" ] || { echo "reap produced no receipt"; exit 1; }

printf '%s\n' "$RECEIPT" >> "$LOG"
printf '%s' "$RECEIPT" | python3 -c '
import json, sys
r = json.load(sys.stdin)
verb = "removed" if r["apply"] else "would remove"
removed = len(r["removed"])
total = r["registered_total"]
unregistered = len(r["unregistered"])
print(verb + " " + str(removed) + " of " + str(total) + " registered worktrees")
if unregistered:
    print(str(unregistered) + " unregistered (pre-lease) worktrees are never auto-removed;")
    print("run --assess-backlog for the evidence-backed safe list")
'
