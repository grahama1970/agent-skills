#!/bin/bash
# Wrapper to run ops-chutes commands with uv

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

# Run the manager
uv run manager.py "$@"
