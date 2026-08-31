#!/usr/bin/env bash
# Scheduled worktree reclamation. The piece that was missing: cleanup_worktree.py
# and audit-worktrees.sh both classify, neither removes, and no cron ran either
# of them -- so the count could only ever go up.
#
# Preview by default. Set WORKTREE_REAP_APPLY=1 to actually remove.
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPTS_DIR")"
REPO="${1:-$HOME/workspace/experiments/agent-skills}"
LOG="${WORKTREE_REAP_LOG:-$HOME/.cleanup/worktree-reap.jsonl}"
mkdir -p "$(dirname "$LOG")"

APPLY=""
[ "${WORKTREE_REAP_APPLY:-0}" = "1" ] && APPLY="--apply"

RECEIPT="$(uv run --project "$SKILL_DIR" python "$SCRIPTS_DIR/worktree_lease.py" \
  --repo "$REPO" $APPLY --json \
  --unregistered-grace-days "${WORKTREE_GRACE_DAYS:-14}" 2>/dev/null)"
[ -n "$RECEIPT" ] || { echo "reap produced no receipt"; exit 1; }

printf '%s\n' "$RECEIPT" >> "$LOG"
printf '%s' "$RECEIPT" | python3 -c '
import json, sys
# Summarize the three-way receipt (removed / archived / kept). The previous
# summary read an "unregistered" key from the old two-way schema, so every cron
# tick raised KeyError after producing a valid receipt -- the receipt landed in
# the log, the summary crashed, and the run looked dead.
r = json.load(sys.stdin)
verb = "" if r.get("apply") else "would have "
removed = len(r.get("removed") or [])
archived = len(r.get("archived") or [])
kept = len(r.get("kept") or [])
total = r.get("registered_total", removed + archived + kept)
print(f"{verb}removed {removed}, archived {archived}, kept {kept} of {total} worktrees")
'
