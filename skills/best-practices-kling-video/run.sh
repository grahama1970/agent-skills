#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec uv run --with pydantic --with typer --with fal-client python scripts/compile_kling_request.py "$@"
