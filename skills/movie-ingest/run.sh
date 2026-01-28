#!/usr/bin/env bash
# Movie-Ingest skill runner
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec uv run --directory "$SCRIPT_DIR" python movie_ingest.py "$@"
