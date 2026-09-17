#!/bin/bash
# triage-error: classify ambiguous pipeline errors into unambiguous codes.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
exec uv run --quiet --with httpx python triage_error.py "$@"
