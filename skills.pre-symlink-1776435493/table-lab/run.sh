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

CMD="${1:-help}"
shift || true

case "$CMD" in
    tune)           uv run python -m table_lab.cli tune "$@" ;;
    probe)          uv run python -m table_lab.cli probe "$@" ;;
    show)           uv run python -m table_lab.cli show "$@" ;;
    apply)          uv run python -m table_lab.cli apply "$@" ;;
    tune-corpus)    uv run python -m table_lab.cli tune-corpus "$@" ;;
    tune-merge)     uv run python -m table_lab.cli tune-merge "$@" ;;
    watchdog)       uv run python -m table_lab.cli watchdog "$@" ;;
    sanity)         bash "$SCRIPT_DIR/sanity.sh" ;;
    help|--help|-h)
        cat << 'EOF'
table-lab v2: Iterative Camelot parameter tuning with convergence, watchdog, and taxonomy

COMMANDS:
  tune <pdf>         Sweep parameter grid, find best settings for a PDF
  probe <pdf>        Single extraction attempt with specific parameters
  tune-merge <pdf>   Diagnose cross-page merge decisions, collect labels
  show               Display stored strategy hints
  apply              Export hints to corpus metadata for S05
  tune-corpus <dir>  Batch tune all PDFs with watchdog monitoring
  watchdog           Show checkpoint and watchdog status

TUNE OPTIONS:
  --dry-run           Show sample pages only, don't sweep
  --converge          Enable convergence loop for iterative refinement
  --max-iterations N  Max convergence iterations (default 3)
  --preset P          S00 preset name for hint storage
  --category C        PDF category for hint storage
  --no-early-stop     Try all strategies even if perfect found
  --json              Machine-readable JSON output

TUNE-MERGE OPTIONS:
  --profile-dir DIR   Pipeline output dir with S05/S05b tables
  --tables-json PATH  Path to pre-merge tables JSON (05_tables.json)
  --label             Interactive labeling mode (terminal)
  --visual            Visual labeling via /interview HTML panes
  --json              JSON output

PROBE OPTIONS:
  --flavor F        lattice or stream
  --line-scale N    Camelot line_scale (lattice mode, default 15)
  --edge-tol N      Camelot edge_tol (stream mode, default 50)
  --page N          Test specific page (1-based)
  --json            JSON output

TUNE-CORPUS OPTIONS:
  --task-name NAME    Checkpoint/monitor name (default: corpus_tune)
  --glob PATTERN      PDF glob pattern (default: **/*_clean.pdf)
  --max-iterations N  Convergence iterations per PDF (default 3)
  --json-stream       NDJSON output per PDF
  --no-resume         Ignore checkpoint, start fresh
  --json              JSON summary output

APPLY OPTIONS:
  --to-corpus       Write to CORPUS_ROOT/metadata/table_hints.json

WATCHDOG OPTIONS:
  --task-name NAME  Task to check (default: corpus_tune)
  --json            JSON output

ENVIRONMENT:
  CORPUS_ROOT                         Corpus path (default: /mnt/storage12tb/extractor_corpus)
  DEBUG_TABLE_DATA                    Data dir (default: ~/.pi/table-lab)
  WATCHDOG_WARN_FRAGMENTATION_RATE    Warn threshold (default: 0.65)
  WATCHDOG_STOP_FRAGMENTATION_RATE    Stop threshold (default: 0.55)
  CIRCUIT_BREAKER_MAX_FAILURES        Max consecutive failures (default: 5)
  MAX_CONVERGENCE_ITERATIONS          Max convergence iters (default: 3)

EXAMPLES:
  ./run.sh tune document.pdf --converge
  ./run.sh probe document.pdf --flavor lattice --line-scale 25 --page 5
  ./run.sh show --preset requirements_spec --category Engineering
  ./run.sh apply --to-corpus
  ./run.sh tune-corpus /mnt/storage12tb/extractor_corpus/results --json-stream
  ./run.sh watchdog --task-name corpus_tune
EOF
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
