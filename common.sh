#!/usr/bin/env bash
# Common utilities for sanity tests

# Load .env files from common locations
load_env() {
    local env_files=(
        "$HOME/.env"
        "/home/graham/workspace/experiments/litellm/.env"
        ".env"
    )

    for env_file in "${env_files[@]}"; do
        if [[ -f "$env_file" ]]; then
            # Export variables from .env (handles comments and empty lines)
            set -a
            source "$env_file" 2>/dev/null || true
            set +a
        fi
    done
}

# Call automatically when sourced
load_env
