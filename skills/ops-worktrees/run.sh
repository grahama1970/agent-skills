#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEASE="$SCRIPT_DIR/scripts/worktree_lease.py"
REPO_DEFAULT="${OPS_WORKTREES_REPO:-$HOME/workspace/experiments/agent-skills}"

usage() {
    cat <<'USAGE'
ops-worktrees - worktree leases, unmerged-work detection, recoverable archive

  run.sh unmerged [--repo PATH] [--json]     work that never reached origin/main
  run.sh reap [--repo PATH] [--apply]        remove / archive / keep
  run.sh archive <worktree> [--apply]        archive one worktree
  run.sh backlog [--repo PATH] [--json]      classify pre-lease worktrees
  run.sh register <worktree> --purpose WHY   record a lease
  run.sh schedule                            print the cron line to install

Preview is the default everywhere; --apply acts.
USAGE
}

cmd="${1:-help}"
shift || true

case "$cmd" in
    unmerged) exec uv run --project "$SCRIPT_DIR" python "$LEASE" --unmerged --repo "$REPO_DEFAULT" "$@" ;;
    reap)     exec uv run --project "$SCRIPT_DIR" python "$LEASE" --repo "$REPO_DEFAULT" "$@" ;;
    backlog)  exec uv run --project "$SCRIPT_DIR" python "$LEASE" --assess-backlog --repo "$REPO_DEFAULT" "$@" ;;
    archive)
        target="${1:?archive needs a worktree path}"; shift || true
        exec uv run --project "$SCRIPT_DIR" python "$LEASE" --archive "$target" --repo "$REPO_DEFAULT" "$@" ;;
    register)
        target="${1:?register needs a worktree path}"; shift || true
        exec uv run --project "$SCRIPT_DIR" python "$LEASE" --register "$target" "$@" ;;
    schedule)
        echo "# Reclaim abandoned worktrees hourly. Preview until you set APPLY=1."
        echo "0 * * * * WORKTREE_REAP_APPLY=1 $SCRIPT_DIR/scripts/reap_worktrees.sh >> \$HOME/.cleanup/worktree-reap.log 2>&1"
        ;;
    help|--help|-h) usage ;;
    *) usage >&2; exit 2 ;;
esac
