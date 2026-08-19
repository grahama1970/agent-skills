#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ "${README_SVG_SKIP_SYNC:-0}" == "1" ]]; then
  UV_RUN=(uv run --project "$SCRIPT_DIR" --no-sync)
  echo "[NOT_RUN] uv sync skipped by explicit offline packaging override"
else
  uv sync --project "$SCRIPT_DIR" --group dev
  UV_RUN=(uv run --project "$SCRIPT_DIR")
fi

"${UV_RUN[@]}" python -m pytest -q "$SCRIPT_DIR/tests"
"${UV_RUN[@]}" python "$SCRIPT_DIR/scripts/check_skill_contract.py" "$SCRIPT_DIR"

"${UV_RUN[@]}" create-svg verify \
  "$SCRIPT_DIR/assets/templates/positive-negative.yml" \
  "$TMP_DIR/positive-negative.svg" \
  --receipt "$TMP_DIR/positive-negative.receipt.json" \
  --browser

"${UV_RUN[@]}" create-svg preview \
  "$TMP_DIR/positive-negative.svg" \
  "$TMP_DIR/positive-negative-preview.html"

if "${UV_RUN[@]}" create-svg validate \
  "$SCRIPT_DIR/tests/fixtures/unsafe-script.svg" \
  --receipt "$TMP_DIR/unsafe.receipt.json"; then
  echo "negative gate failed: unsafe SVG was accepted" >&2
  exit 1
fi

VALIDATOR="$SCRIPT_DIR/../best-practices-skills/scripts/validate_skill.py"
VALIDATOR_PROJECT="$SCRIPT_DIR/../best-practices-skills"
if [[ -f "$VALIDATOR" ]]; then
  uv run --project "$VALIDATOR_PROJECT" python "$VALIDATOR" \
    "$SCRIPT_DIR" --skills-root "$SCRIPT_DIR/.."
else
  echo "[NOT_RUN] adjacent best-practices-skills validator is unavailable"
fi

echo "SANITY PASS: tests, real render, browser motion, unsafe-input rejection, and contract checks"
