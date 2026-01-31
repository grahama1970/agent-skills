#!/bin/bash
# Debug-fetcher skill - automated fetch failure handling with memory integration
# Usage: ./run.sh fetch https://example.com
#        ./run.sh fetch-batch urls.txt
#        ./run.sh recall example.com

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load .env from project root or parent directories
load_dotenv() {
    local dir="$PWD"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/.env" ]]; then
            set -a
            source "$dir/.env" 2>/dev/null || true
            set +a
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    # Also check home directory
    if [[ -f "$HOME/.env" ]]; then
        set -a
        source "$HOME/.env" 2>/dev/null || true
        set +a
    fi
}

load_dotenv

# Also load fetcher's .env for API keys
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env" 2>/dev/null || true
    set +a
fi

# Default configuration
export DEBUG_FETCHER_MEMORY_SCOPE="${DEBUG_FETCHER_MEMORY_SCOPE:-fetcher_strategies}"
export DEBUG_FETCHER_MAX_RETRIES="${DEBUG_FETCHER_MAX_RETRIES:-2}"
export DEBUG_FETCHER_INTERVIEW_THRESHOLD="${DEBUG_FETCHER_INTERVIEW_THRESHOLD:-3}"

# Run the skill
cd "$SCRIPT_DIR"

if [[ "$1" == "status" ]]; then
    echo '{"ok": true, "skill": "debug-fetcher", "memory_scope": "'"$DEBUG_FETCHER_MEMORY_SCOPE"'"}'
    exit 0
fi

# Execute via uv run from skill directory
exec uv run --project "$SCRIPT_DIR" python -m debug_fetcher.cli "$@"
