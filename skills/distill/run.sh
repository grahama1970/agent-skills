#!/usr/bin/env bash
# Distill skill runner - converts large content to QRA pairs in memory
#
# Usage:
#   ./run.sh --file paper.pdf --scope research --dry-run
#   ./run.sh --file paper.pdf --mode accurate --preflight
#   ./run.sh --url https://arxiv.org/... --scope research
#   ./run.sh --text "large text..." --scope research --dry-run
#
# Modes:
#   --mode fast      Use pymupdf4llm (default, local, fast)
#   --mode accurate  Use marker-pdf + Chutes LLM (slower, better for complex PDFs)
#   --mode auto      Let preflight assessment decide

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add local scillm to PYTHONPATH if SCILLM_PATH is set
# (for local development with litellm fork)
if [[ -n "${SCILLM_PATH:-}" && -d "${SCILLM_PATH}" ]]; then
    export PYTHONPATH="${SCILLM_PATH}:${PYTHONPATH:-}"
fi

# Run with uv to ensure proper environment
exec uv run python "${SCRIPT_DIR}/distill.py" "$@"
