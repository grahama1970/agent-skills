#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${ARTIFACT_READER_UV_ENV:-/mnt/storage12tb/skills/artifact-reader/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

exec uv run --project "$SCRIPT_DIR" python \
  "$SCRIPT_DIR/scripts/artifact_reader.py" "$@"
