#!/usr/bin/env bash
# Thin launcher: delegate to the canonical PDF Lab UX in pdf_oxide.
set -euo pipefail
PDF_OXIDE_ROOT="${PDF_OXIDE_ROOT:-$HOME/workspace/experiments/pdf_oxide}"
UI_DIR="$PDF_OXIDE_ROOT/ui"
if [[ ! -d "$UI_DIR" ]]; then
  echo "pdf_oxide UI not found at $UI_DIR — set PDF_OXIDE_ROOT" >&2
  exit 1
fi
cd "$UI_DIR"
exec npm run "${1:-dev}"
