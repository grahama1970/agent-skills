#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/book-extraction-verifier/.venv}"
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"

BOOK_ID="${BOOK_ID:-galaxy_in_flames}"
BOOK="${BOOK:-Galaxy in Flames}"
PERSONA_ID="${PERSONA_ID:-horus_lupercal}"
BOOK_ROOT="${BOOK_ROOT:-/mnt/storage12tb/skills/audiobook-extractor/outputs/${BOOK_ID}}"
FACT_ROOT="${FACT_ROOT:-/mnt/storage12tb/skills/fact-extractor/outputs/${BOOK_ID}}"
OUT_ROOT="${OUT_ROOT:-/mnt/storage12tb/skills/book-extraction-verifier/outputs/${BOOK_ID}}"
FIXTURE_PATH="${FIXTURE_PATH:-${OUT_ROOT}/fixtures.jsonl}"

"$SCRIPT_DIR/run.sh" verify-book \
  --book-id "$BOOK_ID" \
  --book "$BOOK" \
  --persona-id "$PERSONA_ID" \
  --book-root "$BOOK_ROOT" \
  --fact-root "$FACT_ROOT" \
  --out-root "$OUT_ROOT" \
  --fixture-path "$FIXTURE_PATH" \
  --require-memory

rm -rf "$SCRIPT_DIR/.pytest_cache" "$SCRIPT_DIR/book_extraction_verifier/__pycache__" "$SCRIPT_DIR/tests/__pycache__"
