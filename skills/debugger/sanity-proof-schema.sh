#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-proof-schema.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PYTHON=(uv run --project "$SCRIPT_DIR" python)
VALIDATOR="$SCRIPT_DIR/scripts/validate_debugger_proof.py"

"${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/canonical-valid.json" --expect-valid
"${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/canonical-invalid-no-state.json" --expect-invalid

# A producer may not certify its own success: a hand-edited proofValid=true
# over a stop that never happened, or a frame borrowed from an unrelated
# source, must be rejected by independent recomputation (#1436). These fail
# closed under --expect-valid and are caught under --expect-invalid.
"${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/canonical-tampered-proofvalid.json" --expect-invalid
"${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/canonical-tampered-frame-mismatch.json" --expect-invalid
if "${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/canonical-tampered-proofvalid.json" --expect-valid 2>/dev/null; then
  echo "proof-independence failed: tampered proofValid=true was accepted" >&2
  exit 1
fi
"${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/vscode-bridge-status-valid.json" \
  --expect-valid \
  --canonical-out "$WORK_DIR/vscode-canonical.json"
"${PYTHON[@]}" "$VALIDATOR" "$SCRIPT_DIR/fixtures/proofs/rust-gdb-valid.txt" \
  --expect-valid \
  --canonical-out "$WORK_DIR/rust-canonical.json"

cat > "$WORK_DIR/target.py" <<'PY'
def classify(value):
    label = "large" if value > 10 else "small"
    return label


assert classify(14) == "large"
PY

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/capture_breakpoints.py" \
  --break "$WORK_DIR/target.py:3" \
  --local value \
  --local label \
  --watch label \
  --allow-watch-eval \
  --out "$WORK_DIR/python-proof.json" \
  -- "$WORK_DIR/target.py"

"${PYTHON[@]}" "$VALIDATOR" "$WORK_DIR/python-proof.json" \
  --expect-valid \
  --canonical-out "$WORK_DIR/python-canonical.json"

cat > "$WORK_DIR/sample.ts" <<'TS'
export function classify(value: number): string {
  const label: string = value > 10 ? 'large' : 'small';
  return label;
}
TS

node --experimental-strip-types "$SCRIPT_DIR/scripts/node_inspector_breakpoint_proof.mjs" \
  --file "$WORK_DIR/sample.ts" \
  --line 3 \
  --function classify \
  --arg 14 \
  --local value \
  --local label \
  --out "$WORK_DIR/typescript-proof.json"

"${PYTHON[@]}" "$VALIDATOR" "$WORK_DIR/typescript-proof.json" \
  --expect-valid \
  --canonical-out "$WORK_DIR/typescript-canonical.json"

for canonical in "$WORK_DIR"/*-canonical.json; do
  "${PYTHON[@]}" "$VALIDATOR" "$canonical" --expect-valid
done

echo "debugger proof schema sanity passed: $WORK_DIR"
