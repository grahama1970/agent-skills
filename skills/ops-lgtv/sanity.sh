#!/usr/bin/env bash
# ops-lgtv sanity gate: behavioral + SAFETY (mutation gating) acceptance checks.
# Live-TV checks require pairing (human on-TV prompt) and are SKIPPED, not passed, without LGTV_IP.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/scripts/ops_lgtv.py"
fail=0
note() { printf '  %s\n' "$*"; }

echo "[1/5] uv sync + CLI smoke"
uv sync --project "$SCRIPT_DIR" >/dev/null 2>&1 || { echo "FAIL: uv sync"; exit 1; }
"$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1 || { echo "FAIL: run.sh --help"; exit 1; }
note "ok"

echo "[2/5] SAFETY: mutation gated behind --execute (static + behavioral)"
grep -q 'raise typer.Exit(3)' "$SRC" || { echo "FAIL: no --execute refusal path"; fail=1; }
"$SCRIPT_DIR/run.sh" set-sound-output external_arc --ip 127.0.0.1 >/dev/null 2>&1; code=$?
if [ "$code" -ne 3 ]; then echo "FAIL: expected exit 3 without --execute, got $code"; fail=1; else note "ok — refused"; fi

echo "[3/5] NEGATIVE-CONTROL: unreachable TV -> sound fails closed, exit 2"
ERR="$("$SCRIPT_DIR/run.sh" sound --ip 127.0.0.1 2>&1 >/dev/null)"; code=$?
if [ "$code" -ne 2 ] || ! echo "$ERR" | jq -e '.status == "down"' >/dev/null 2>&1; then
    echo "FAIL: unreachable TV did not fail closed (exit=$code)"; echo "$ERR" | head -2; fail=1
else
    note "ok — status=down/exit 2"
fi

echo "[4/5] COMPOSITION: gain-staging references the ops-wiim skill entrypoint"
grep -q 'ops-wiim' "$SRC" || { echo "FAIL: gain-staging does not compose ops-wiim"; fail=1; }
[ -x "$SCRIPT_DIR/../ops-wiim/run.sh" ] || { echo "FAIL: composed ops-wiim/run.sh missing"; fail=1; }
[ "$fail" -eq 0 ] && note "ok"

echo "[5/5] POSITIVE-CONTROL: live sound read (requires paired LGTV_IP)"
if [ -n "${LGTV_IP:-}" ] && [ "${LGTV_IP}" != "127.0.0.1" ]; then
    OUT="$("$SCRIPT_DIR/run.sh" sound --ip "$LGTV_IP" 2>/dev/null)"; code=$?
    if [ "$code" -ne 0 ] || ! echo "$OUT" | jq -e '.schema == "ops_lgtv.sound.v1"' >/dev/null 2>&1; then
        echo "FAIL: live sound read against $LGTV_IP failed (exit=$code)"; fail=1
    else
        note "ok — sound_output=$(echo "$OUT" | jq -r .sound_output)"
    fi
else
    note "SKIP — LGTV_IP not set; live path NOT_TESTED (coverage gap, not a pass)"
fi

[ "$fail" -ne 0 ] && { echo "SANITY: FAIL"; exit 1; }
echo "SANITY: PASS"
