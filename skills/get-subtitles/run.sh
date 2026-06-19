#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls.
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use zsh and source ~/.zshrc so locally configured API keys are available
# without printing them.
exec zsh -lc 'source ~/.zshrc >/dev/null 2>&1 || true; export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/get-subtitles-venv}"; cd "$1"; shift; exec uv run python scripts/cli.py "$@"' _ "$SCRIPT_DIR" "$@"
