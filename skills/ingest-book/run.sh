#!/bin/bash
# Readarr Ops Entry Point

# Source .env from project root if it exists
PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

PYTHONPATH="${PYTHONPATH}:$(dirname "$0")" python3 "$(dirname "$0")/readarr_ops.py" "$@"
