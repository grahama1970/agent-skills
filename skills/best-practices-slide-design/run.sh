#!/usr/bin/env bash
# best-practices-slide-design — exemplar corpus tooling (stdlib python only).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-verify-exemplars}" in
  build-manifest)       python3 "$SCRIPT_DIR/scripts/exemplar_corpus.py" build ;;
  verify-exemplars)     python3 "$SCRIPT_DIR/scripts/exemplar_corpus.py" verify ;;
  contact-sheet)        python3 "$SCRIPT_DIR/scripts/exemplar_corpus.py" sheet ;;
  analyze-style)        shift; exec "$SCRIPT_DIR/../pitchdeck/run.sh" analyze-style "$@" ;;
  *) echo "usage: run.sh {build-manifest|verify-exemplars|contact-sheet|analyze-style ...}"; exit 2 ;;
esac
