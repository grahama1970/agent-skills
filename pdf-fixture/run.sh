#!/bin/bash
# Self-contained pdf-fixture skill - auto-installs via uv
# Usage: ./run.sh --example --name test_fixture
set -e

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
