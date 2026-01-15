#!/bin/bash
# Self-contained fetcher skill - auto-installs via uv
# Usage: ./run.sh get https://example.com
set -e

# Git source for fetcher
REPO="git+https://github.com/grahama1970/fetcher.git"

if command -v uv &> /dev/null; then
    uv run --from "$REPO" fetcher "$@"
elif command -v fetcher &> /dev/null; then
    fetcher "$@"
else
    echo "Error: Neither uv nor fetcher found" >&2
    echo "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi
