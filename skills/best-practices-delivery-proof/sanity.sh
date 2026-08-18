#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [best-practices-delivery-proof] Sanity Check ==="
# Positive control: the committed contract passes.
UV_PROJECT_ENVIRONMENT=/mnt/storage12tb/skills/best-practices-delivery-proof/.venv uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/verify_contract.py" check
# Negative control: dropping a rule must fail the same gate.
if UV_PROJECT_ENVIRONMENT=/mnt/storage12tb/skills/best-practices-delivery-proof/.venv uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/verify_contract.py" check --mutate-drop-rule 6 >/dev/null 2>&1; then
  echo "FAIL: gate did not fail closed on a dropped rule" >&2
  exit 1
fi
echo "PASS: gate fails closed on a dropped rule"
echo "=== Sanity OK ==="
