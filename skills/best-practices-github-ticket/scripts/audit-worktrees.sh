#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  audit-worktrees.sh [--repo PATH] [--json]

Audits registered git worktrees for ticket lifecycle safety. It never deletes
anything. The command fails closed when it finds:
  - prunable worktree registrations
  - registered worktrees under /tmp
  - dirty secondary worktrees

The primary repository worktree is not counted as a dirty secondary worktree.
EOF
}

repo="."
as_json=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            [[ $# -ge 2 ]] || { echo "ERROR: --repo requires PATH" >&2; exit 2; }
            repo="$2"
            shift 2
            ;;
        --json)
            as_json=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown arg: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

repo_root="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)" || {
    echo "ERROR: not a git repository: $repo" >&2
    exit 2
}

records="$(mktemp)"
trap 'rm -f "$records"' EXIT
git -C "$repo_root" worktree list --porcelain > "$records"

total=0
tmp_count=0
detached_count=0
prunable_count=0
dirty_secondary_count=0
declare -a tmp_paths=()
declare -a prunable_paths=()
declare -a dirty_paths=()
declare -a detached_paths=()

flush_record() {
    [[ -n "${path:-}" ]] || return 0
    total=$((total + 1))
    if [[ "$path" != "$repo_root" && "$path" == /tmp/* ]]; then
        tmp_count=$((tmp_count + 1))
        tmp_paths+=("$path")
    fi
    if [[ "${detached:-0}" == "1" ]]; then
        detached_count=$((detached_count + 1))
        detached_paths+=("$path")
    fi
    if [[ "${prunable:-0}" == "1" ]]; then
        prunable_count=$((prunable_count + 1))
        prunable_paths+=("$path")
        return 0
    fi
    if [[ "$path" != "$repo_root" && -d "$path" ]]; then
        if [[ -n "$(git -C "$path" status --porcelain 2>/dev/null || true)" ]]; then
            dirty_secondary_count=$((dirty_secondary_count + 1))
            dirty_paths+=("$path")
        fi
    fi
}

path=""
detached=0
prunable=0
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ -z "$line" ]]; then
        flush_record
        path=""
        detached=0
        prunable=0
        continue
    fi
    case "$line" in
        worktree\ *)
            path="${line#worktree }"
            ;;
        detached)
            detached=1
            ;;
        prunable\ *)
            prunable=1
            ;;
    esac
done < "$records"
flush_record

ok=true
if (( tmp_count > 0 || prunable_count > 0 || dirty_secondary_count > 0 )); then
    ok=false
fi

json_array() {
    local first=1
    printf '['
    local item
    for item in "$@"; do
        if [[ "$first" == "0" ]]; then
            printf ','
        fi
        first=0
        printf '"%s"' "$(printf '%s' "$item" | sed 's/\\/\\\\/g; s/"/\\"/g')"
    done
    printf ']'
}

if [[ "$as_json" == "1" ]]; then
    printf '{"ok":%s,"repo":"%s","total":%d,"tmp":%d,"detached":%d,"prunable":%d,"dirty_secondary":%d,' \
        "$ok" "$(printf '%s' "$repo_root" | sed 's/\\/\\\\/g; s/"/\\"/g')" \
        "$total" "$tmp_count" "$detached_count" "$prunable_count" "$dirty_secondary_count"
    printf '"tmp_paths":'
    json_array "${tmp_paths[@]}"
    printf ',"prunable_paths":'
    json_array "${prunable_paths[@]}"
    printf ',"dirty_secondary_paths":'
    json_array "${dirty_paths[@]}"
    printf '}\n'
else
    printf 'repo: %s\n' "$repo_root"
    printf 'total=%d tmp=%d detached=%d prunable=%d dirty_secondary=%d\n' \
        "$total" "$tmp_count" "$detached_count" "$prunable_count" "$dirty_secondary_count"
    if (( tmp_count > 0 )); then
        printf 'tmp worktrees:\n'
        printf '  %s\n' "${tmp_paths[@]}"
    fi
    if (( prunable_count > 0 )); then
        printf 'prunable registrations:\n'
        printf '  %s\n' "${prunable_paths[@]}"
    fi
    if (( dirty_secondary_count > 0 )); then
        printf 'dirty secondary worktrees:\n'
        printf '  %s\n' "${dirty_paths[@]}"
    fi
fi

if [[ "$ok" != "true" ]]; then
    exit 1
fi
