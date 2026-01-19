#!/usr/bin/env bash
# QRA skill runner - extract Q&A pairs from text with optional domain context
#
# Usage:
#   ./run.sh --file doc.md --scope research
#   ./run.sh --text "large text..." --context "cybersecurity expert"
#   ./run.sh --from-extractor /path/to/extractor/results --scope research
#   cat document.txt | ./run.sh --scope myproject
#   ./run.sh --file paper.md --context-file ~/.prompts/ml-expert.txt
#
# Extractor integration:
#   Use --from-extractor to consume Stage 10 output from the extractor project.
#   This preserves section structure, table/figure descriptions, and metadata.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add local scillm to PYTHONPATH if SCILLM_PATH is set
# (for local development with litellm fork)
if [[ -n "${SCILLM_PATH:-}" && -d "${SCILLM_PATH}" ]]; then
    export PYTHONPATH="${SCILLM_PATH}:${PYTHONPATH:-}"
fi

# Use python directly (not uv run) to avoid resolving scillm's optional
# 'certainly' extra which has git submodule issues. QRA doesn't need Lean4.
exec python "${SCRIPT_DIR}/qra.py" "$@"
