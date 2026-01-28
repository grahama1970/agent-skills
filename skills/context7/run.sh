#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Create venv if needed
if [[ ! -d .venv ]]; then
    uv venv .venv
fi

# Install deps if pyproject.toml exists
if [[ -f pyproject.toml ]]; then
    uv pip install -e . 2>/dev/null || true
fi

# Run the main Python script
source .venv/bin/activate
python context7.py "$@"
