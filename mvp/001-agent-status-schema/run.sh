#!/usr/bin/env bash
# Fixture gate for pi.agent_status.v1. Valid cases must pass, illegal must fail.
set -euo pipefail
cd "$(dirname "$0")"

pass=0; fail=0
check() { # check <expected_exit> <name> <json>
  local expected="$1" name="$2" json="$3" rc=0
  echo "$json" | python3 status_schema.py validate - >/dev/null || rc=$?
  if [ "$rc" -eq "$expected" ]; then pass=$((pass+1)); echo "OK   $name"
  else fail=$((fail+1)); echo "FAIL $name (exit $rc, expected $expected)"; fi
}

check 0 valid_done '{"schema":"pi.agent_status.v1","goal":"g","state":"done","verified":[{"command":"ls x","result":"x"}],"proof":["/tmp/x"]}'
check 0 valid_continuing '{"schema":"pi.agent_status.v1","goal":"g","state":"continuing","not_done":[{"item":"build","next_command":"./run.sh"}]}'
check 0 valid_failed_catalog_code '{"schema":"pi.agent_status.v1","goal":"g","state":"failed","failure":{"triage":{"code":"tau_project_dag_missing_required_evidence","cause":"c"}}}'
check 0 valid_failed_minted_code '{"schema":"pi.agent_status.v1","goal":"g","state":"failed","failure":{"triage":{"code":"unknown_unclassified_953afe1d","cause":"c"}}}'
check 1 illegal_ambiguous_label '{"schema":"pi.agent_status.v1","goal":"g","state":"failed","failure":{"triage":{"code":"something went wrong","cause":"c"}}}'
check 1 illegal_freeform_code '{"schema":"pi.agent_status.v1","goal":"g","state":"failed","failure":{"triage":{"code":"browser_broke_idk","cause":"c"}}}'
check 1 illegal_failed_without_triage '{"schema":"pi.agent_status.v1","goal":"g","state":"failed"}'
check 1 illegal_continuing_without_next_command '{"schema":"pi.agent_status.v1","goal":"g","state":"continuing"}'
check 1 illegal_done_without_proof '{"schema":"pi.agent_status.v1","goal":"g","state":"done","verified":[{"command":"c","result":"r"}]}'
check 0 valid_needs_human '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_human","needs_human":{"action":"run /reload","reason":"stale resident extensions"}}'
check 1 illegal_needs_human_without_action '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_human"}'
check 1 illegal_legacy_blocked_state '{"schema":"pi.agent_status.v1","goal":"g","state":"blocked"}'
check 0 valid_needs_brave_search '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_brave_search","needs_brave_search":{"queries":["q1"]}}'
check 0 valid_needs_agent '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_agent","needs_agent":{"handler":"claude-fable-low","question":"q"}}'
check 0 valid_needs_webgpt_with_rung_receipts '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_webgpt","needs_webgpt":{"question":"q","brave_search_receipt":"/tmp/r0.json","agent_receipt":"/tmp/r1.json"}}'
check 0 valid_needs_roundtable_quorum3 '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_roundtable","needs_roundtable":{"immutable_goal":"ig","question":"q","handlers":["webgpt","webkimi","claude-fable-low"]}}'
check 0 valid_needs_competition '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_competition","needs_competition":{"immutable_goal":"ig","task":"t","handlers":["webgpt","webkimi"],"criteria":["correctness"]}}'
check 1 illegal_webgpt_without_rung_receipts '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_webgpt","needs_webgpt":{"question":"q"}}'
check 1 illegal_roundtable_below_quorum '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_roundtable","needs_roundtable":{"immutable_goal":"ig","question":"q","handlers":["webgpt","webkimi"]}}'
check 1 illegal_competition_single_handler '{"schema":"pi.agent_status.v1","goal":"g","state":"needs_competition","needs_competition":{"immutable_goal":"ig","task":"t","handlers":["webgpt"],"criteria":["c"]}}'
check 1 illegal_extra_field '{"schema":"pi.agent_status.v1","goal":"g","state":"done","verified":[{"command":"c","result":"r"}],"proof":["p"],"vibes":"good"}'

echo "pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
printf '{"ok":true,"schema":"pi.agent_status.v1","cases_passed":%d,"cases_failed":%d}\n' "$pass" "$fail" > receipt.json
