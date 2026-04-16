#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Save caller's directory so we can resolve relative path arguments after cd
ORIG_DIR="$(pwd)"
cd "$SCRIPT_DIR"

# Resolve a path relative to caller's directory (not skill dir)
resolve_path() {
    local p="$1"
    if [[ "$p" = /* ]]; then
        echo "$p"
    elif [[ -e "$ORIG_DIR/$p" || -d "$ORIG_DIR/$p" ]]; then
        realpath "$ORIG_DIR/$p"
    else
        echo "$p"
    fi
}

usage() {
    cat <<EOF
Usage: $0 <command> [args...]

Commands:
  review <paper_dir>                     Full multi-persona peer review
  compare-exemplars <paper_dir> [--papers IDS]  Compare against arxiv exemplars
  score-section <tex_file> [--reviewer ID]      Score a single section
  train [--reviewer ID] [--data PATH]           Train reviewer GPTs from shadow
  shadow-report                                  Shadow agreement statistics
  visualize <paper_dir> [--output PATH]         Generate visual review dashboard
  review-arxiv <arxiv_id> [--shadow]            Review arxiv paper for curriculum
  converge <paper_dir> [--threshold N]          Review-refine convergence loop
  benchmark <paper_dir|.tex> [--corpus PATH]   Score paper against arxiv corpus
  ingest-benchmark <arxiv_id> [--tex PATH]     Add paper to benchmark corpus

Examples:
  $0 review artifacts/neophyte_paper_v5/
  $0 compare-exemplars artifacts/neophyte_paper_v5/ --papers 2305.05176,2411.05844
  $0 score-section artifacts/neophyte_paper_v5/sections/eval.tex --reviewer alpha
  $0 train --reviewer alpha
  $0 shadow-report
  $0 visualize artifacts/neophyte_paper_v5/ --output review_dashboard.png
  $0 review-arxiv 2305.05176 --shadow
  $0 converge artifacts/neophyte_paper_v5/ --threshold 6.0 --max-rounds 5
EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

cmd="$1"
shift

case "$cmd" in
    review)
        echo "[create-peer-review] Running full peer review..."
        resolved="$(resolve_path "$1")"; shift
        uv run --project "$SCRIPT_DIR" python -m src.cli review "$resolved" "$@"
        ;;
    compare-exemplars)
        echo "[create-peer-review] Comparing against arxiv exemplars..."
        resolved="$(resolve_path "$1")"; shift
        uv run --project "$SCRIPT_DIR" python -m src.cli compare-exemplars "$resolved" "$@"
        ;;
    score-section)
        echo "[create-peer-review] Scoring section..."
        resolved="$(resolve_path "$1")"; shift
        uv run --project "$SCRIPT_DIR" python -m src.cli score-section "$resolved" "$@"
        ;;
    train)
        echo "[create-peer-review] Training reviewer GPTs from shadow data..."
        uv run --project "$SCRIPT_DIR" python -m src.cli train "$@"
        ;;
    shadow-report)
        echo "[create-peer-review] Shadow agreement report..."
        uv run --project "$SCRIPT_DIR" python -m src.cli shadow-report "$@"
        ;;
    visualize)
        echo "[create-peer-review] Generating visual review dashboard..."
        resolved="$(resolve_path "$1")"; shift
        uv run --project "$SCRIPT_DIR" python -m src.cli visualize "$resolved" "$@"
        ;;
    review-arxiv)
        echo "[create-peer-review] Reviewing arxiv paper for curriculum..."
        uv run --project "$SCRIPT_DIR" python -m src.cli review-arxiv "$@"
        ;;
    converge)
        echo "[create-peer-review] Running convergence loop..."
        resolved="$(resolve_path "$1")"; shift
        uv run --project "$SCRIPT_DIR" python -m src.cli converge "$resolved" "$@"
        ;;
    benchmark)
        echo "[create-peer-review] Benchmarking paper against arxiv corpus..."
        resolved="$(resolve_path "$1")"; shift
        uv run --project "$SCRIPT_DIR" python -m src.cli benchmark "$resolved" "$@"
        ;;
    ingest-benchmark)
        echo "[create-peer-review] Ingesting paper into benchmark corpus..."
        uv run --project "$SCRIPT_DIR" python -m src.cli ingest-benchmark "$@"
        ;;
    *)
        echo "Unknown command: $cmd"
        usage
        exit 1
        ;;
esac
