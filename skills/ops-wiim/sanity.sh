#!/usr/bin/env bash
# ops-wiim sanity gate: behavioral + SAFETY (mutation gating) acceptance checks.
# Live-amp checks run only when WIIM_IP is set; otherwise they are SKIPPED, not passed.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/scripts/ops_wiim.py"
fail=0
note() { printf '  %s\n' "$*"; }

echo "[1/5] uv sync + CLI smoke"
if ! uv sync --project "$SCRIPT_DIR" >/dev/null 2>&1; then
    echo "FAIL: uv sync failed"; exit 1
fi
if ! "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "FAIL: run.sh --help failed"; exit 1
fi
note "ok"

echo "[2/5] SAFETY: mutations are gated behind --execute (static)"
# Every mutating path must go through _mutate(), which refuses without execute.
if ! grep -q 'raise typer.Exit(3)' "$SRC"; then
    echo "FAIL: no --execute refusal path found"; fail=1
fi
if grep -nE 'setPlayerCmd|EQOff|EQOn' "$SRC" | grep -v '_mutate' | grep -vq 'command'; then
    echo "FAIL: mutating command outside _mutate gate"; fail=1
fi
[ "$fail" -eq 0 ] && note "ok — mutations gated"

echo "[3/5] NEGATIVE-CONTROL: unreachable amp -> diagnose status=down, exit 2"
NEG="$(WIIM_IP=127.0.0.1 "$SCRIPT_DIR/run.sh" diagnose --json 2>/dev/null)"; code=$?
if [ "$code" -ne 2 ]; then echo "FAIL: expected exit 2 on unreachable amp, got $code"; fail=1; fi
if ! echo "$NEG" | jq -e '.schema == "ops_wiim.diagnosis.v1" and .status == "down" and .reachable == false' >/dev/null 2>&1; then
    echo "FAIL: unreachable amp did not fail closed to status=down"; echo "$NEG" | head -3; fail=1
else
    note "ok — fails closed to down/exit 2"
fi

echo "[4/5] SAFETY: set-volume without --execute refuses with exit 3 (no network call needed)"
WIIM_IP=127.0.0.1 "$SCRIPT_DIR/run.sh" set-volume 50 >/dev/null 2>&1; code=$?
if [ "$code" -ne 3 ]; then
    echo "FAIL: expected exit 3 for ungated mutation, got $code"; fail=1
else
    note "ok — refused without --execute"
fi

echo "[5/5] POSITIVE-CONTROL: live diagnose (requires WIIM_IP)"
if [ -n "${WIIM_IP:-}" ] && [ "${WIIM_IP}" != "127.0.0.1" ]; then
    OUT="$("$SCRIPT_DIR/run.sh" diagnose --json 2>/dev/null)"; code=$?
    if [ "$code" -ne 0 ] || ! echo "$OUT" | jq -e '.status == "up" and (.findings | length > 0)' >/dev/null 2>&1; then
        echo "FAIL: live diagnose against $WIIM_IP did not produce findings (exit=$code)"; fail=1
    else
        note "ok — live report with $(echo "$OUT" | jq '.findings | length') finding(s)"
    fi
else
    note "SKIP — WIIM_IP not set; live path NOT_TESTED (this is a coverage gap, not a pass)"
fi

if [ "$fail" -ne 0 ]; then echo "SANITY: FAIL"; exit 1; fi
echo "SANITY: PASS"
