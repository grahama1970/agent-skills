#!/usr/bin/env bash
# Non-vacuity proof for the render-dream-workspace guard: reintroduce the
# 2026-08-19 defect (loadPhase02MediaGate unexported after the 99-file split)
# in a temporary copy of ui/src and confirm the guard FAILS against it.
# Exits 0 only when the guard fails on broken code AND passes on real code.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

TMP=$(mktemp -d /tmp/pd-broken-ui.XXXXXX)
trap 'rm -rf "$TMP"' EXIT
cp -r ../../ui/src "$TMP/src"
sed -i 's/^export async function loadPhase02MediaGate/async function loadPhase02MediaGate/' "$TMP/src/lib/script.tsx"
grep -q '^async function loadPhase02MediaGate' "$TMP/src/lib/script.tsx" || { echo "PROOF_SETUP_FAILED: defect not injected"; exit 2; }

if PD_UI_SRC="$TMP/src/index.ts" node scripts/eval/render_dream_workspace.mjs >/dev/null 2>&1; then
  echo "GUARD_VACUOUS: render eval passed against broken ui/src"
  exit 1
fi
node scripts/eval/render_dream_workspace.mjs >/dev/null 2>&1 || { echo "GUARD_BROKEN: render eval fails on current code"; exit 3; }
echo "FAIL_BEFORE_FIX_PROVEN: guard fails on broken copy, passes on current code"
