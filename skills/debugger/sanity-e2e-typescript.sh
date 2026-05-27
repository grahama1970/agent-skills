#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-ts-e2e.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/sample.ts" <<'TS'
export function classify(value: number): string {
  const label: string = value > 10 ? 'large' : 'small';
  return label;
}
TS

proof=/tmp/debugger-typescript-e2e-proof.json
node --experimental-strip-types "$SCRIPT_DIR/scripts/node_inspector_breakpoint_proof.mjs" \
  --file "$WORK_DIR/sample.ts" \
  --line 3 \
  --function classify \
  --arg 14 \
  --local value \
  --local label \
  --out "$proof"

node - "$proof" <<'JS'
const fs = require('node:fs');
const proof = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (!proof.hit_breakpoint) throw new Error('TypeScript breakpoint was not hit');
if (!proof.proofAssessment.variableInspectionValid) throw new Error('TypeScript variable inspection was invalid');
if (proof.locals.value !== 14) throw new Error(`expected value=14, got ${proof.locals.value}`);
if (proof.locals.label !== 'large') throw new Error(`expected label=large, got ${proof.locals.label}`);
JS

export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/validate_debugger_proof.py" "$proof" \
  --expect-valid \
  --canonical-out /tmp/debugger-typescript-e2e-proof.canonical.json

echo "debugger TypeScript E2E sanity passed: $proof"
