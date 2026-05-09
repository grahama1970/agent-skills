#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

python3 -m compileall -q "$SCRIPT_DIR/project_drift"
python3 -m project_drift schema --out "$SCRIPT_DIR/references/drift_report.schema.json" >/dev/null
python3 -m project_drift validate-report "$SCRIPT_DIR/references/example_drift_report.json" >/dev/null

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
cat > "$tmpdir/PROJECT_KNOWLEDGE.md" <<'PK'
# Project Knowledge: sample

**Last updated:** 2026-05-09 09:00 by agent
**Status:** Active development

## Current Understanding

- project_drift should not update PROJECT_KNOWLEDGE.md directly.

## Open Questions

- [ ] Should project_drift block on resolved open questions?
PK
cat > "$tmpdir/transcript.jsonl" <<'JSONL'
{"timestamp":"2026-05-09T10:00:00Z","type":"user","message":{"role":"user","content":"project_drift should focus on contradictions and stale claims, not random additions."}}
{"timestamp":"2026-05-09T10:01:00Z","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"./run.sh validate-report drift_report.json"},"tool_response":{"exit_code":0,"stdout":"Valid drift report: verdict=warn"}}
JSONL
(cd "$tmpdir" && "$SCRIPT_DIR/run.sh" scan --transcript "$tmpdir/transcript.jsonl" --out-dir "$tmpdir/out" --no-execute >/dev/null)
test -f "$tmpdir/out/prompt_payload.json"
test -f "$tmpdir/out/cleaned_transcript.json"

cat > "$tmpdir/codex-transcript.jsonl" <<'JSONL'
{"timestamp":"2026-05-09T10:00:00Z","type":"session_meta","payload":{"id":"session-1","cwd":"/tmp/project-drift-sanity"}}
{"timestamp":"2026-05-09T10:00:01Z","type":"event_msg","payload":{"type":"user_message","message":"Project knowledge says the old contract is still active, but verifier output now proves the new contract."}}
{"timestamp":"2026-05-09T10:00:02Z","type":"response_item","payload":{"type":"function_call","name":"exec_command","call_id":"call-1","arguments":"{\"cmd\":\"./run.sh validate-report drift_report.json\"}"}}
{"timestamp":"2026-05-09T10:00:03Z","type":"response_item","payload":{"type":"function_call_output","call_id":"call-1","output":"{\"exit_code\":0,\"stdout\":\"Valid drift report: verdict=warn severity=medium candidates=1\"}"}}
{"timestamp":"2026-05-09T10:00:04Z","type":"event_msg","payload":{"type":"agent_message","message":"The verifier passed and the drift report is a candidate artifact, not an authoritative write."}}
JSONL
(cd "$tmpdir" && "$SCRIPT_DIR/run.sh" scan --transcript "$tmpdir/codex-transcript.jsonl" --out-dir "$tmpdir/codex-out" --no-execute --since none >/dev/null)
python3 - "$tmpdir/codex-out/cleaned_transcript.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
if payload.get("observation_count", 0) < 2:
    raise SystemExit(f"expected Codex payload observations, got {payload.get('observation_count')}")
kinds = {obs.get("kind") for obs in payload.get("observations", [])}
if "human_statement" not in kinds or "command" not in kinds:
    raise SystemExit(f"expected human_statement and command observations, got {sorted(kinds)}")
PY
echo "project-drift sanity passed"
