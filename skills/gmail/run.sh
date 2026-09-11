#!/usr/bin/env bash
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"
exec uv run --with typer --with pydantic python3 scripts/gmail_read.py "$@"
