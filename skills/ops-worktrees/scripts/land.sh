#!/usr/bin/env bash
# land.sh — land ONLY the named paths onto origin/main via plumbing.
# Works from any dirty checkout, worktree, or branch. Never touches HEAD,
# never stashes, never stages anything outside the given paths, never
# deletes a worktree (the hourly reaper owns reclamation).
#
# usage: land.sh -m "message" [--repo PATH] <path>...
set -euo pipefail

msg="" repo=""
paths=()
while [ $# -gt 0 ]; do
    case "$1" in
        -m) msg="${2:?-m needs a message}"; shift 2 ;;
        --repo) repo="${2:?--repo needs a path}"; shift 2 ;;
        *) paths+=("$1"); shift ;;
    esac
done
[ -n "$msg" ] || { echo "land: commit message required (-m)" >&2; exit 2; }
[ ${#paths[@]} -gt 0 ] || { echo "land: at least one explicit path required" >&2; exit 2; }
for p in "${paths[@]}"; do
    case "$p" in
        .|./|-A|--all|:/|'*') echo "land: refuse repo-wide pathspec '$p' — name the files" >&2; exit 2 ;;
    esac
done

repo="${repo:-$(git rev-parse --show-toplevel)}"
cd "$repo"
git fetch -q origin main

export GIT_INDEX_FILE="$(mktemp)"
trap 'rm -f "$GIT_INDEX_FILE"' EXIT

for attempt in 1 2 3; do
    git read-tree origin/main
    git add -A -- "${paths[@]}"
    tree=$(git write-tree)
    if [ "$tree" = "$(git rev-parse origin/main^{tree})" ]; then
        echo "land: no change vs origin/main for named paths — nothing to push"
        exit 0
    fi
    sha=$(git commit-tree "$tree" -p origin/main -m "$msg")
    if git push -q origin "$sha:main" 2>/dev/null; then
        git fetch -q origin main
        git merge-base --is-ancestor "$sha" origin/main
        echo "landed $sha on origin/main:"
        git show --stat --oneline "$sha" | sed -n '2,$p'
        exit 0
    fi
    echo "land: push race (attempt $attempt), re-fetching" >&2
    git fetch -q origin main
done
echo "land: push failed after 3 attempts" >&2
exit 1
