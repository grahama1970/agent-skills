#!/usr/bin/env bash
set -euo pipefail

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$skill_dir/scripts/validate_font_receipt.py" "$skill_dir/fixtures/valid-font-receipt.json" >/tmp/best-practices-font-valid.out

if python3 "$skill_dir/scripts/validate_font_receipt.py" "$skill_dir/fixtures/invalid-font-receipt.json" >/tmp/best-practices-font-invalid.out 2>&1; then
  echo "FAIL: invalid fixture unexpectedly passed"
  exit 1
fi

grep -q "world_model is required" /tmp/best-practices-font-invalid.out
echo "OK: best-practices-font sanity passed"
