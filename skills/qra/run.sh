#!/usr/bin/env bash
# QRA skill runner - extract Q&A pairs from text with optional domain context
#
# Usage:
#   ./run.sh --file doc.md --scope research
#   ./run.sh --text "large text..." --context "cybersecurity expert"
#   cat document.txt | ./run.sh --scope myproject
#   ./run.sh --file paper.md --context-file ~/.prompts/ml-expert.txt

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add local scillm to PYTHONPATH if SCILLM_PATH is set
# (for local development with litellm fork)
if [[ -n "${SCILLM_PATH:-}" && -d "${SCILLM_PATH}" ]]; then
    export PYTHONPATH="${SCILLM_PATH}:${PYTHONPATH:-}"
fi

# Run with uv to ensure proper environment
exec uv run python "${SCRIPT_DIR}/qra.py" "$@"
