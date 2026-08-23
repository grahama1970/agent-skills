#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  audit-worktrees.sh [--repo PATH] [--json] [--scope-path PATH ...]

Audits registered git worktrees for ticket lifecycle safety. It never deletes
anything. The command fails closed when it finds:
  - prunable worktree registrations
  - registered worktrees under /tmp
  - dirty secondary worktrees

The primary repository worktree is not counted as a dirty secondary worktree.
When --scope-path is provided, dirty secondary worktrees only fail the audit
when their dirty files overlap one of those repository-relative paths.
EOF
}

repo="."
as_json=0
declare -a scope_paths=()

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
        --scope-path)
            [[ $# -ge 2 ]] || { echo "ERROR: --scope-path requires PATH" >&2; exit 2; }
            scope_paths+=("${2#./}")
            shift 2
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
dirty_secondary_ignored_count=0
declare -a tmp_paths=()
declare -a prunable_paths=()
declare -a dirty_paths=()
declare -a dirty_ignored_paths=()
declare -a detached_paths=()

path_overlaps_scope() {
    local changed="${1#./}"
    local scope
    if [[ "${#scope_paths[@]}" -eq 0 ]]; then
        return 0
    fi
    for scope in "${scope_paths[@]}"; do
        scope="${scope#./}"
        scope="${scope%/}"
        [[ -n "$scope" ]] || continue
        if [[ "$changed" == "$scope" || "$changed" == "$scope/"* || "$scope" == "$changed/"* ]]; then
            return 0
        fi
    done
    return 1
}

dirty_worktree_overlaps_scope() {
    local wt="$1"
    local line changed
    if [[ "${#scope_paths[@]}" -eq 0 ]]; then
        return 0
    fi
    while IFS= read -r line || [[ -n "$line" ]]; do
        changed="${line:3}"
        changed="${changed#\"}"
        changed="${changed%\"}"
        if [[ "$changed" == *" -> "* ]]; then
            if path_overlaps_scope "${changed%% -> *}" || path_overlaps_scope "${changed##* -> }"; then
                return 0
            fi
        elif path_overlaps_scope "$changed"; then
            return 0
        fi
    done < <(git -C "$wt" status --porcelain 2>/dev/null || true)
    return 1
}

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
            if dirty_worktree_overlaps_scope "$path"; then
                dirty_secondary_count=$((dirty_secondary_count + 1))
                dirty_paths+=("$path")
            else
                dirty_secondary_ignored_count=$((dirty_secondary_ignored_count + 1))
                dirty_ignored_paths+=("$path")
            fi
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
    printf '{"ok":%s,"repo":"%s","total":%d,"tmp":%d,"detached":%d,"prunable":%d,"dirty_secondary":%d,"dirty_secondary_ignored":%d,' \
        "$ok" "$(printf '%s' "$repo_root" | sed 's/\\/\\\\/g; s/"/\\"/g')" \
        "$total" "$tmp_count" "$detached_count" "$prunable_count" "$dirty_secondary_count" "$dirty_secondary_ignored_count"
    printf '"scope_paths":'
    json_array "${scope_paths[@]}"
    printf ',"tmp_paths":'
    json_array "${tmp_paths[@]}"
    printf ',"prunable_paths":'
    json_array "${prunable_paths[@]}"
    printf ',"dirty_secondary_paths":'
    json_array "${dirty_paths[@]}"
    printf ',"dirty_secondary_ignored_paths":'
    json_array "${dirty_ignored_paths[@]}"
    printf '}\n'
else
    printf 'repo: %s\n' "$repo_root"
    printf 'total=%d tmp=%d detached=%d prunable=%d dirty_secondary=%d dirty_secondary_ignored=%d\n' \
        "$total" "$tmp_count" "$detached_count" "$prunable_count" "$dirty_secondary_count" "$dirty_secondary_ignored_count"
    if [[ "${#scope_paths[@]}" -gt 0 ]]; then
        printf 'scope paths:\n'
        printf '  %s\n' "${scope_paths[@]}"
    fi
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
    if (( dirty_secondary_ignored_count > 0 )); then
        printf 'dirty secondary worktrees outside scope:\n'
        printf '  %s\n' "${dirty_ignored_paths[@]}"
    fi
fi

if [[ "$ok" != "true" ]]; then
    exit 1
fi
