#!/usr/bin/env bash
set -euo pipefail
skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
html="${1:?usage: verify_progress_report.sh PATH/TO/GOAL_PAGE.html [repo-root] [gates-yaml]}"
repo="${2:-.}"
gates="${3:-}"
args=(--html "$html" --repo "$repo")
[[ -n "$gates" ]] && args+=(--gates "$gates")
exec python3 "$skill_dir/verify_progress_report.py" "${args[@]}"
