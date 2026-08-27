#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

set +e
node "$SCRIPT_DIR/scripts/gate-check.mjs" --status "$SCRIPT_DIR/fixtures/gates/valid-gates.md" >/tmp/unlazy-valid-status.out 2>/tmp/unlazy-valid-status.err
valid_rc=$?
set -e
if [[ "$valid_rc" -ne 1 ]]; then
  echo "valid unmet gate ledger returned unexpected rc=$valid_rc" >&2
  exit 1
fi
grep -q "UNMET" /tmp/unlazy-valid-status.out

node "$SCRIPT_DIR/scripts/gate-lint.mjs" "$SCRIPT_DIR/fixtures/gates/valid-gates.md" >/tmp/unlazy-valid-lint.out
grep -q "LINT OK" /tmp/unlazy-valid-lint.out

set +e
node "$SCRIPT_DIR/scripts/gate-check.mjs" --status "$SCRIPT_DIR/fixtures/gates/invalid-gates.md" >/tmp/unlazy-invalid-status.out 2>/tmp/unlazy-invalid-status.err
invalid_rc=$?
set -e
if [[ "$invalid_rc" -ne 2 ]]; then
  echo "invalid gate returned unexpected rc=$invalid_rc" >&2
  exit 1
fi
grep -Eq "malformed|usage|ERROR|Invalid|invalid" /tmp/unlazy-invalid-status.err /tmp/unlazy-invalid-status.out

echo "UNLAZY_SANITY_OK"
