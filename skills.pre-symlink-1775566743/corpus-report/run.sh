#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if [[ ! -d ".venv" ]]; then
    uv sync --quiet 2>/dev/null || uv venv && uv sync --quiet
fi

CMD="${1:-summary}"
shift || true

case "$CMD" in
    summary)      uv run python -m corpus_report.cli summary "$@" ;;
    quality)      uv run python -m corpus_report.cli quality "$@" ;;
    patterns)     uv run python -m corpus_report.cli patterns "$@" ;;
    bottlenecks)  uv run python -m corpus_report.cli bottlenecks "$@" ;;
    trends)       uv run python -m corpus_report.cli trends "$@" ;;
    sanity)       bash "$SCRIPT_DIR/sanity.sh" ;;
    help|--help|-h)
        cat << 'EOF'
corpus-report: Extractor corpus statistics and quality analysis

COMMANDS:
  summary      Quick stats (default): total/completed/pending/failed, categories
  quality      S00/S04 ratio analysis, label distribution, worst offenders
  patterns     Failure pattern registry: frequency, affected files
  bottlenecks  Pipeline stage timing analysis (scans result dirs)
  trends       Quality metrics over time windows

OPTIONS (all commands):
  --json       Machine-readable JSON output
  --category   Filter by PDF category (arxiv, standards, government, etc.)

BOTTLENECKS OPTIONS:
  --sample N   Limit result directory scanning (default: all completed)

TRENDS OPTIONS:
  --since HOURS  Only include PDFs finished in last N hours (default: all)
  --window HOURS Time window grouping size (default: 6)

ENVIRONMENT:
  CORPUS_ROOT  Override default path (/mnt/storage12tb/extractor_corpus)

EXAMPLES:
  ./run.sh                       # Quick summary
  ./run.sh quality --json        # S00 accuracy as JSON
  ./run.sh bottlenecks --sample 20
  ./run.sh trends --since 24
EOF
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
