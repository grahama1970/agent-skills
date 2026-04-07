#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# review-pdf: extraction fidelity auditor for extractor S00/S11 outputs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SKILL_DIR"

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

show_help() {
    cat << 'EOF'
review-pdf: assess extractor PDF quality and drive self-improvement

Usage:
  ./run.sh check <run_dir_or_profile.json> [options]
  ./run.sh batch <root_dir> [options]
  ./run.sh iterate <root_dir> [options]
  ./run.sh loop <root_dir> [options]
  ./run.sh compare <aggregate_a.json> <aggregate_b.json>
  ./run.sh convergence <history.jsonl>
  ./run.sh status <aggregate.json>
  ./run.sh history [--limit N]
  ./run.sh serve [port]              Start review server (default port 8003)

Core options:
  --output-dir PATH       Report output directory
  --run-id ID             Stable run identifier
  --execute-jobs          Auto-run escalation helper skills
  --max-jobs-per-doc N    Max escalation jobs per document
  --memory-events PATH    Mandatory memory event jsonl sink
  --extract-missing       Extract missing PDFs before review
  --ingest-memory         Push reviewed docs into graph memory
  --taxonomy-collection   Attach taxonomy tags to report summaries

Examples:
  ./run.sh check /path/to/run_dir
  ./run.sh batch /mnt/storage12tb/extractor_corpus --limit 200
  ./run.sh iterate /mnt/storage12tb/extractor_corpus --cycles 3 --execute-jobs
  ./run.sh loop /mnt/storage12tb/extractor_corpus --target-score 0.95 --watch
  ./run.sh compare reports/run_a/aggregate.json reports/run_b/aggregate.json
EOF
}

PDF_OXIDE_ROOT="${PDF_OXIDE_ROOT:-$HOME/workspace/experiments/pdf_oxide}"
PROTOTYPE_API_DIR="/home/graham/workspace/experiments/extractor/prototypes/tabbed/api"

case "${1:-help}" in
    check|review|audit|batch|iterate|loop|watch|compare|convergence|status|history)
        cmd="$1"
        shift
        exec uv run --project "$SCRIPT_DIR" python verify.py "$cmd" "$@"
        ;;
    serve)
        shift
        port="${1:-8003}"
        export PYTHONPATH="${PROTOTYPE_API_DIR}${PYTHONPATH:+:$PYTHONPATH}"
        exec uv run --directory "$PDF_OXIDE_ROOT" \
            uvicorn review_server:app --host 0.0.0.0 --port "$port"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: ${1:-}"
        show_help
        exit 1
        ;;
esac
