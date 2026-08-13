#!/usr/bin/env bash
# Measure deck-level architecture from a corpus of real .pptx decks.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/measure_deck_architecture.py" "$@"
