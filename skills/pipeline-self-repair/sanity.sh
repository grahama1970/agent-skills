#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/pipeline-self-repair-uv-env}"
uv run --project . pytest tests -q
TMP="$(mktemp -d /tmp/pipeline-self-repair-sanity.XXXXXX)"
./run.sh record-failure \
  --pipeline persona-dream \
  --step-id phase_11_kling_submit \
  --run-id sanity-run \
  --raw-signal "multi_prompt prompt exceeds 512 characters" \
  --layer kling \
  --target skills/persona-dream \
  --run-root "$TMP" \
  --ledger "$TMP/replay_ledger.jsonl" \
  --skip-memory \
  --skip-github \
  --no-ticket \
  --json > "$TMP/record.json"
./run.sh inspect --ledger "$TMP/replay_ledger.jsonl" --json > "$TMP/inspect.json"
./run.sh monitor \
  --ledger "$TMP/replay_ledger.jsonl" \
  --subagent-run-id sanity-subagent-run \
  --skip-watchdog \
  --json > "$TMP/monitor.json"
cat > "$TMP/webgpt-response.md" <<'EOF'
TICKET
Type: feature
Title: Add hardening cycle orchestration
Target: skills/pipeline-self-repair
Current state: Memory hardening review output is translated into tickets by hand.
Requested outcome: One command emits the WebGPT prompt, parsed ticket candidates, ticket projections, and monitor receipt.
Route: backend_python_or_skill_runtime
Requested repair agent: agent-skill-maintainer
Scoped files: skills/pipeline-self-repair/scripts/pipeline_self_repair.py
Non-goals: broad memory refactor
Required proof: pipeline-self-repair sanity passes and hardening-cycle emits a receipt.
Failure code: pipeline_self_repair_missing_hardening_cycle

NO_TICKET: Existing scorecard status is already a fact, not a repair item.
EOF
./run.sh hardening-cycle \
  --ledger "$TMP/replay_ledger.jsonl" \
  --replay-ledger "$TMP/hardening-cycle-ledger.jsonl" \
  --webgpt-response "$TMP/webgpt-response.md" \
  --output-dir "$TMP/hardening-cycle" \
  --skip-scorecard \
  --skip-watchdog \
  --skip-triage \
  --json > "$TMP/hardening-cycle.json"
python - <<'PY' "$TMP/record.json" "$TMP/inspect.json" "$TMP/monitor.json" "$TMP/hardening-cycle.json" "$TMP/hardening-cycle-ledger.jsonl"
import json, sys
record=json.load(open(sys.argv[1]))
inspect=json.load(open(sys.argv[2]))
monitor=json.load(open(sys.argv[3]))
cycle=json.load(open(sys.argv[4]))
cycle_event=json.loads(open(sys.argv[5]).read().splitlines()[-1])
assert record["status"] in {"RECORDED_REPAIR_REQUIRED", "RECORDED_NEEDS_TRIAGE"}, record
assert inspect["event_count"] >= 1, inspect
assert inspect["open_failure_count"] == 1, inspect
assert monitor["schema"] == "pipeline_self_repair.monitor.v1", monitor
assert monitor["project_agent_role"]["owner"] == "project-agent", monitor
assert monitor["monitoring"]["push"]["pi_wake_subscriptions"], monitor
assert cycle["schema"] == "pipeline_self_repair.hardening_cycle.v1", cycle
assert cycle["webgpt_parse"]["ticket_count"] == 1, cycle
assert cycle["ticket_projections"][0]["status"] == "PROJECTED", cycle
assert cycle_event["schema"] == "pipeline_self_repair.hardening_cycle_event.v1", cycle_event
assert cycle_event["event_type"] == "hardening_cycle.generated", cycle_event
print("PIPELINE_SELF_REPAIR_SANITY_OK")
PY
