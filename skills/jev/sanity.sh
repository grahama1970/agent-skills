#!/usr/bin/env bash
# Sanity: compile, presets valid, egress gate blocks restricted content and
# unauthorized calls, key presence (warn only).
set -euo pipefail
cd "$(dirname "$0")"
pass=0; fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "PASS $1"; pass=$((pass+1)); else echo "FAIL $1"; fail=$((fail+1)); fi; }

check "python compiles"       'uv run --quiet --with httpx,typer,loguru python -m py_compile scripts/jev.py'
check "presets valid JSON"    'python3 -c "import json,glob; [json.load(open(p)) for p in glob.glob(\"questions/*.json\")]"'
check "tasks lists presets"   './run.sh tasks | grep -q goal_drift'

echo '{"doc": "CUI// SPARTA test doc"}' > /tmp/jev_sanity_cui.json
./run.sh gate --state @/tmp/jev_sanity_cui.json >/dev/null 2>&1 && rc=0 || rc=$?
[ "$rc" = "1" ] && { echo "PASS egress gate blocks CUI marker"; pass=$((pass+1)); } || { echo "FAIL egress gate blocks CUI marker"; fail=$((fail+1)); }

./run.sh ask --preset edge_stance --state '{"claim":"x","passage":"y"}' >/dev/null 2>&1 && rc=0 || rc=$?
[ "$rc" = "2" ] && { echo "PASS ask refuses without --allow-egress"; pass=$((pass+1)); } || { echo "FAIL ask refuses without --allow-egress"; fail=$((fail+1)); }


# Positive control: one live judgment when a key exists (skips gracefully otherwise)
if [ -n "${JEV_API_KEY:-}" ]; then
  out=$(./run.sh ask --questions '{"ok":{"type":"noul","instructions":"Is this a sanity probe?"}}' --state '{"note":"sanity"}' --allow-egress 2>/dev/null) && rc=0 || rc=$?
  echo "$out" | grep -q '"schema": "jev.receipt.v1"' && found=0 || found=1
  if [ "$rc" = "0" ] || [ "$rc" = "3" ]; then rc_ok=0; else rc_ok=1; fi
  if [ "$rc_ok" = "0" ] && [ "$found" = "0" ]; then
    echo "PASS live positive control (typed receipt emitted; accept/abstain is calibration, not health)"; pass=$((pass+1))
  else
    echo "FAIL live positive control (rc=$rc)"; fail=$((fail+1))
  fi
else
  echo "INFO live positive control skipped (no JEV_API_KEY)"
fi

grep -q JEV_API_KEY ~/.zshrc 2>/dev/null && echo "INFO JEV_API_KEY present in ~/.zshrc" || echo "INFO JEV_API_KEY not found (live calls will fail)"
echo "sanity: $pass passed, $fail failed"
[ "$fail" = "0" ]
