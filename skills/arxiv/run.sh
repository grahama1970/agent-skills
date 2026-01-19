#!/usr/bin/env bash
# Arxiv skill runner - search and download arXiv papers
#
# Usage:
#   ./run.sh search -q "hypergraph transformer" -n 10
#   ./run.sh search -q "LLM reasoning" --smart -c cs.LG
#   ./run.sh get -i 2601.08058
#   ./run.sh download -i 2601.08058 -o ./papers/
#   ./run.sh categories

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_ROOT="${PI_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"

# Load environment
[[ -f "$PI_ROOT/.env" ]] && { set -a; source "$PI_ROOT/.env"; set +a; }

# Add scillm to PYTHONPATH for smart query translation
if [[ -n "${SCILLM_PATH:-}" && -d "${SCILLM_PATH}" ]]; then
    export PYTHONPATH="${SCILLM_PATH}:${PYTHONPATH:-}"
fi

# Run with uv for dependency management
exec uv run python "${SCRIPT_DIR}/arxiv_cli.py" "$@"
