#!/usr/bin/env bash
# Common utilities for sanity tests

# Detect repo root relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Load .env files from common locations
load_env() {
    local env_files=(
        "$HOME/.env"
        "${PROJECT_ROOT}/.env"
        ".env"
    )

    if [[ -n "${SKILLS_COMMON_ENV_PATHS:-}" ]]; then
        IFS=":" read -r -a extra_paths <<< "$SKILLS_COMMON_ENV_PATHS"
        env_files+=("${extra_paths[@]}")
    fi

    local seen=()
    for env_file in "${env_files[@]}"; do
        [[ -z "$env_file" ]] && continue
        local normalized
        normalized=$(realpath -m "$env_file" 2>/dev/null || echo "$env_file")
        if [[ " ${seen[*]} " == *" $normalized "* ]]; then
            continue
        fi
        seen+=("$normalized")
        if [[ -f "$normalized" ]]; then
            # Export variables from .env (handles comments and empty lines)
            set -a
            source "$normalized" 2>/dev/null || true
            set +a
        fi
    done
}

# Call automatically when sourced
load_env

# Report progress to task-monitor state file
# Usage: report_progress <state_file> <completed> <total> <current_item> [status]
report_progress() {
    local state_file="$1"
    local completed="$2"
    local total="$3"
    local current_item="$4"
    local status="${5:-running}"
    
    local last_updated
    last_updated=$(date "+%Y-%m-%d %H:%M:%S")
    
    # Create directory if needed
    mkdir -p "$(dirname "$state_file")"
    
    # Write JSON state
    cat << EOF > "$state_file"
{
  "completed": $completed,
  "total": $total,
  "current_item": "$current_item",
  "last_updated": "$last_updated",
  "status": "$status"
}
EOF
}

