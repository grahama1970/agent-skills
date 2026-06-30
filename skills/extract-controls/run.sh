#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
MEMORY_ROOT="${MEMORY_ROOT:-${HOME}/workspace/experiments/memory}"
EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-${HOME}/workspace/experiments/extractor}"

# Load .env from memory project if present
if [ -f "$MEMORY_ROOT/.env" ]; then
    set -a
    source "$MEMORY_ROOT/.env"
    set +a
fi

cmd="${1:-help}"
shift || true

case "$cmd" in
  extract)
    if [[ "${1:-}" == "--text" ]]; then
      shift
      cd "$MEMORY_ROOT" && uv run python "$SKILL_DIR/extract_controls.py" extract-text "$@"
    else
      cd "$EXTRACTOR_ROOT" && uv run python -m extractor.pipeline.run_pipeline "$@"
    fi
    ;;
  backfill)
    cd "$MEMORY_ROOT" && uv run python scripts/backfill_chunk_control_edges.py "$@"
    ;;
  validate)
    cd "$MEMORY_ROOT" && uv run python scripts/shadow_lego_control_extraction.py "$@"
    ;;
  prove)
    cd "$MEMORY_ROOT" && uv run python scripts/consume_proof_jobs.py "$@"
    ;;
  coverage|stats)
    cd "$MEMORY_ROOT" && uv run python "$SKILL_DIR/extract_controls.py" "$cmd" "$@"
    ;;
  help|--help|-h|*)
    echo "Usage: ./run.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  extract <path>                   Extract controls from PDF (extractor pipeline + s12)"
    echo "  extract --text \"...\"             Extract controls from inline text (regex + rapidfuzz)"
    echo "  backfill [--dry-run]             Backfill all existing datalake_chunks"
    echo "  backfill [--fuzz-threshold 85]   Tune fuzz match threshold"
    echo "  validate [--sample-rate 0.10]    Shadow-LEGO validation on sample of chunks"
    echo "  prove [--batch-size 10]          Process proof_jobs queue via lean4-prove"
    echo "  prove [--priority 1]             Process high-priority (NIST/SPARTA) jobs only"
    echo "  coverage [--framework NIST]      Report extraction coverage per framework"
    echo "  stats                            Show edge collection counts and proof_jobs status"
    echo ""
    echo "Environment:"
    echo "  MEMORY_ROOT    Memory project path (default: ${HOME}/workspace/experiments/memory)"
    echo "  EXTRACTOR_ROOT Extractor project path (default: ${HOME}/workspace/experiments/extractor)"
    echo "  ARANGO_HOST    ArangoDB host (default: http://localhost:8529)"
    echo "  ARANGO_DB      Database name (default: memory)"
    ;;
esac
