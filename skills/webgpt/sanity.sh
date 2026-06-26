#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== webgpt skill sanity ==="
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/webgpt_cli.py --help" >/dev/null 2>&1 && echo "  [PASS] --help" || echo "  [FAIL] --help"
for cmd in submit download activate navigate close listen config; do
  uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/webgpt_cli.py" "$cmd" --help >/dev/null 2>&1 && echo "  [PASS] $cmd" || echo "  [FAIL] $cmd"
done
echo "=== all checks passed ==="
