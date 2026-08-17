#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
VALIDATOR="$ROOT/../.system/skill-creator/scripts/quick_validate.py"

if [[ -f "$VALIDATOR" ]]; then
  "$PYTHON_BIN" -B "$VALIDATOR" "$ROOT"
fi
PYTHONDONTWRITEBYTECODE=1 "$PYTHON_BIN" -B -m unittest discover -s "$ROOT/tests" -v
printf 'transcript-to-leetcode sanity: PASS\n'
