#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TMP_DIR="$(mktemp -d -t readme-to-pitchdeck-sanity.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]]; then
  if [[ -d /mnt/storage12tb && -w /mnt/storage12tb ]]; then
    export UV_PROJECT_ENVIRONMENT="/mnt/storage12tb/skills/readme-to-pitchdeck/.venv"
  else
    export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/readme-to-pitchdeck/venv"
  fi
fi

printf '%s\n' '[1/5] Unit and boundary tests'
if "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import PIL, pydantic, pptx, pytest, typer, yaml
PY
then
  "$PYTHON_BIN" -m pytest "$SCRIPT_DIR/tests" -q
else
  uv run --project "$SCRIPT_DIR" --extra dev pytest "$SCRIPT_DIR/tests" -q
fi

printf '%s\n' '[2/5] Positive-control README planning'
"$SCRIPT_DIR/run.sh" plan \
  --source-manifest "$SCRIPT_DIR/fixtures/minimal/source_manifest.yaml" \
  --output-dir "$TMP_DIR/positive" \
  --max-slides 10

printf '%s\n' '[3/5] Editable PPTX build and schema receipt'
"$SCRIPT_DIR/run.sh" build \
  --deck "$TMP_DIR/positive/deck.public.yaml" \
  --claim-ledger "$TMP_DIR/positive/claim_ledger.yaml" \
  --source-manifest "$TMP_DIR/positive/source_manifest.resolved.yaml" \
  --asset-manifest "$TMP_DIR/positive/asset_manifest.yaml" \
  --output "$TMP_DIR/positive/deck.pptx"

printf '%s\n' '[4/5] Bundle verification'
"$SCRIPT_DIR/run.sh" verify \
  --bundle-dir "$TMP_DIR/positive" \
  --pptx "$TMP_DIR/positive/deck.pptx"

printf '%s\n' '[5/5] Optional Linux render/contact-sheet gate'
if command -v libreoffice >/dev/null 2>&1 && command -v pdftoppm >/dev/null 2>&1; then
  "$SCRIPT_DIR/run.sh" render \
    --pptx "$TMP_DIR/positive/deck.pptx" \
    --output-dir "$TMP_DIR/render" \
    --dpi 90
else
  printf '%s\n' 'SKIP: libreoffice or pdftoppm unavailable; PPTX structure was still verified.'
fi

printf '%s\n' 'PASS: positive control, negative controls, editable PPTX, and receipts validated.'
