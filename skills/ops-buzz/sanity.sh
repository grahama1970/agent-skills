#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat >"$TMP_DIR/message.json" <<'JSON'
{
  "schema": "ops_buzz.message.v1",
  "title": "Morning opportunities",
  "body": "4 opportunities found.",
  "source_skill": "monitor-opportunities",
  "source_run_id": "run:test",
  "source_url": "http://127.0.0.1:8767/?token=test",
  "external_effects": false,
  "items": [
    {"title": "Technology modernization signal", "subtitle": "University at Buffalo UBIT"},
    {"title": "Account Executive - Tech", "subtitle": "Discord"}
  ]
}
JSON

"$SCRIPT_DIR/run.sh" --help >/dev/null
"$SCRIPT_DIR/run.sh" config doctor --json >"$TMP_DIR/doctor.json"
"$SCRIPT_DIR/run.sh" render-message --input "$TMP_DIR/message.json" --output "$TMP_DIR/message.md" >"$TMP_DIR/render.json"
"$SCRIPT_DIR/run.sh" post --channel "00000000-0000-0000-0000-000000000000" --input "$TMP_DIR/message.json" --dry-run >"$TMP_DIR/post.json"

cat >"$TMP_DIR/agent-request.json" <<'JSON'
{
  "schema": "ops_buzz.agent_request.v1",
  "channel": "00000000-0000-0000-0000-000000000000",
  "target_agent": "codex",
  "prompt": "Inspect the monitor-opportunities morning report and summarize blockers.",
  "expected_response": "Return status, findings, and artifact paths. Do not claim external effects.",
  "source_skill": "monitor-opportunities",
  "source_run_id": "run:test",
  "source_url": "http://127.0.0.1:8767/?token=test",
  "source_artifact": "/tmp/report-manifest.json",
  "timeout_seconds": 0,
  "poll_interval_seconds": 1,
  "readback_limit": 5
}
JSON
"$SCRIPT_DIR/run.sh" ask-agent --input "$TMP_DIR/agent-request.json" --dry-run \
  --output-request "$TMP_DIR/agent-request.md" >"$TMP_DIR/agent-request-receipt.json"

python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
doctor = json.loads((root / "doctor.json").read_text())
assert doctor["schema"] == "ops_buzz.config_doctor.v1"
assert "buzz_bin" in doctor

render = json.loads((root / "render.json").read_text())
assert render["schema"] == "ops_buzz.render_receipt.v1"
assert render["mocked"] is False
assert render["live"] is False
assert render["seam_validation"]["status"] == "PASS"
message = (root / "message.md").read_text()
assert "Morning opportunities" in message
assert "Technology modernization signal" in message
assert "External effects: false" in message

post = json.loads((root / "post.json").read_text())
assert post["schema"] == "ops_buzz.post_receipt.v1"
assert post["dry_run"] is True
assert post["attempted_network"] is False
assert post["posted"] is False
assert post["mocked"] is False
assert post["live"] is False
assert post["seam_validation"]["status"] == "PASS"

agent = json.loads((root / "agent-request-receipt.json").read_text())
assert agent["schema"] == "ops_buzz.agent_request_receipt.v1"
assert agent["status"] == "DRY_RUN"
assert agent["attempted_network"] is False
assert agent["request_posted"] is False
assert agent["response_observed"] is False
assert agent["seam_validation"]["kind"] == "ops_buzz.agent_request.v1"
request_text = (root / "agent-request.md").read_text()
assert "@codex request from ops-buzz" in request_text
assert "Expected response contract" in request_text
assert "monitor-opportunities" in request_text
PY

cat >"$TMP_DIR/bad.json" <<'JSON'
{"schema": "ops_buzz.message.v1", "title": "", "body": "missing title", "external_effects": false}
JSON
if "$SCRIPT_DIR/run.sh" render-message --input "$TMP_DIR/bad.json" >/tmp/ops-buzz-bad.out 2>/tmp/ops-buzz-bad.err; then
  echo "FAIL: invalid payload unexpectedly rendered" >&2
  exit 1
fi

cat >"$TMP_DIR/bad-agent.json" <<'JSON'
{"schema": "ops_buzz.agent_request.v1", "channel": "", "target_agent": "codex", "prompt": "x", "expected_response": "y"}
JSON
if "$SCRIPT_DIR/run.sh" ask-agent --input "$TMP_DIR/bad-agent.json" --dry-run >/tmp/ops-buzz-bad-agent.out 2>/tmp/ops-buzz-bad-agent.err; then
  echo "FAIL: invalid agent request unexpectedly rendered" >&2
  exit 1
fi

echo "ops-buzz sanity: PASS"
