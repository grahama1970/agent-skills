#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Self-contained pdf-fixture skill - auto-installs via uv
# Usage: ./run.sh --example --name test_fixture
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Git source for extractor project (contains pdf-fixture)
REPO="git+https://github.com/grahama1970/extractor.git"

if command -v uv &> /dev/null; then
    # Run the fixture generator from git repo
    uv run --from "$REPO" python -m extractor.fixtures.create "$@"
else
    echo "Error: uv not found" >&2
    echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi
