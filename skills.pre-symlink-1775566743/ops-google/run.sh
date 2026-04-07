#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

# Wrapper to run ops-google commands with uv

# Determine skill directory
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

# Helper to check if uv handles venv
has_uv() {
    command -v uv >/dev/null 2>&1
}

# Ensure dependencies are installed
if [ ! -d ".venv" ]; then
    if has_uv; then
        uv venv && uv pip install .
    else
        python3 -m venv .venv && . .venv/bin/activate
        max_tries=3
        try=1
        while true; do
          if python -m pip install .; then
            break
          fi
          if [ "$try" -ge "$max_tries" ]; then
            echo "ERROR: Failed to install dependencies after $max_tries attempts" >&2
            exit 1
          fi
          try=$((try+1))
          sleep 2
        done
    fi
fi

# Load environment variables via common.sh (searches $HOME/.env, $PROJECT_ROOT/.env, ./.env)
COMMON_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common.sh"
if [ -f "$COMMON_SH" ]; then
    source "$COMMON_SH"
else
    # Fallback: walk up to find .env
    _dir="$SKILL_DIR"
    while [ "$_dir" != "/" ]; do
        if [ -f "$_dir/.env" ]; then
            set -a; source "$_dir/.env"; set +a
            break
        fi
        _dir="$(dirname "$_dir")"
    done
fi

# Run the manager
uv run manager.py "$@"
