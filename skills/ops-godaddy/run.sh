#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec uv run --with typer --with pydantic python3 scripts/godaddy_dns.py "$@"
