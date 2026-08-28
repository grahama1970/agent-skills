#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo "=== triage-error sanity ==="
uv run python -c "import triage_error; print('OK: import')"
uv run python triage_error.py catalog | head -3
# known signal classifies to the canonical code
uv run python -c "
import triage_error as t
r = t.classify('surf webgpt error: zip contains 9 files; maximum is 5', 'surf')
assert r['code']=='webgpt_attachment_bundle_rejected' and not r['ambiguous'], r
amb = t.classify('some totally novel gizmo exploded 0xdead', 'tau')
assert amb['ambiguous'] and amb['code'].startswith('tau_unclassified_'), amb
print('OK: classify known + minted ambiguous')
"
echo "=== sanity passed ==="
