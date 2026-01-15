#!/bin/bash
# Self-contained surf skill - auto-installs via npx from GitHub
# Usage: ./run.sh go "https://example.com"
set -e

# Git source for surf-cli
REPO="github:nicobailon/surf-cli"

if command -v npx &> /dev/null; then
    npx "$REPO" "$@"
elif command -v surf &> /dev/null; then
    surf "$@"
else
    echo "Error: Neither npx nor surf found" >&2
    echo "Install Node.js: https://nodejs.org/" >&2
    exit 1
fi
