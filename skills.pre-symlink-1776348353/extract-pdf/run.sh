#!/usr/bin/env bash
set -euo pipefail

# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# pdf_oxide lives in an external project — delegate via uv run
PDF_OXIDE_ROOT="${PDF_OXIDE_ROOT:-$HOME/workspace/experiments/pdf_oxide}"

# Load .env if present (for LLM keys, ArangoDB config, etc.)
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SKILL_DIR")")")"
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# extract_pdf package lives in skill dir; pdf_oxide comes from external project
export PYTHONPATH="${SKILL_DIR}:${PYTHONPATH:-}"

CMD="${1:-help}"
shift || true

case "$CMD" in
  extract)
    # Full extraction pipeline
    # Usage: ./run.sh extract <pdf_path> [--output-dir <dir>] [--features arango,describe]
    exec uv run --directory "$PDF_OXIDE_ROOT" \
      python -m extract_pdf.main extract "$@"
    ;;

  survey)
    # Lightweight page-by-page survey (profiling without full extraction)
    # Usage: ./run.sh survey <pdf_path> [--enrich-profile]
    exec uv run --directory "$PDF_OXIDE_ROOT" \
      python -m extract_pdf.main survey "$@"
    ;;

  text)
    # Raw text extraction only (fast)
    # Usage: ./run.sh text <pdf_path> [--page N]
    exec uv run --directory "$PDF_OXIDE_ROOT" \
      python -m extract_pdf.main text "$@"
    ;;

  batch)
    # Batch extraction across a directory
    # Usage: ./run.sh batch <dir> [--output-dir <dir>] [--workers N]
    exec uv run --directory "$PDF_OXIDE_ROOT" \
      python -m extract_pdf.main batch "$@"
    ;;

  profile)
    # Document profiling only (domain, preset, complexity, is_scanned)
    # Usage: ./run.sh profile <pdf_path>
    exec uv run --directory "$PDF_OXIDE_ROOT" \
      python -m extract_pdf.main profile "$@"
    ;;

  pipeline)
    # Extractor-compatible pipeline output (replaces S00-S06 in /extractor)
    # Writes same directory structure as run_pipeline.py for drop-in replacement
    # Usage: ./run.sh pipeline <pdf_path> --output-dir <dir>
    exec uv run --directory "$PDF_OXIDE_ROOT" \
      python -m extract_pdf.main pipeline "$@"
    ;;

  shadow)
    # Show shadow correction log
    if [ -f "$SKILL_DIR/shadow.jsonl" ]; then
      python3 -c "
import json
for line in open('$SKILL_DIR/shadow.jsonl'):
    r = json.loads(line)
    status = 'AGREE' if r.get('agree') else 'DISAGREE'
    print(f\"{r.get('timestamp','')} [{status}] predicted={r.get('predicted','')} actual={r.get('actual','')}\")" | tail -20
    else
      echo "No shadow logs yet."
    fi
    ;;

  status)
    bash "$SKILL_DIR/sanity.sh"
    ;;

  help|*)
    cat <<HELP
/extract-pdf — Rust-native PDF extraction (replaces PyMuPDF)

Usage:
  ./run.sh extract <pdf> [--output-dir <dir>]    Full extraction pipeline
  ./run.sh survey <pdf> [--enrich-profile]        Lightweight page survey
  ./run.sh text <pdf> [--page N]                  Raw text only
  ./run.sh batch <dir> [--output-dir <dir>]       Batch extraction
  ./run.sh profile <pdf>                          Document profiling only
  ./run.sh shadow                                 Show shadow correction log
  ./run.sh status                                 Health check
HELP
    ;;
esac
