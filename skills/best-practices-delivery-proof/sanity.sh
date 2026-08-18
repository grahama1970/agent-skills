#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [best-practices-delivery-proof] Sanity Check ==="
# Positive control: the committed contract passes.
python3 "$SCRIPT_DIR/scripts/verify_contract.py"
# Negative control: dropping a rule must fail the same gate.
if python3 "$SCRIPT_DIR/scripts/verify_contract.py" --mutate-drop-rule 6 >/dev/null 2>&1; then
  echo "FAIL: gate did not fail closed on a dropped rule" >&2
  exit 1
fi
echo "PASS: gate fails closed on a dropped rule"
echo "=== Sanity OK ==="
