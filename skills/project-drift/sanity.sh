#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

python3 -m compileall -q "$SCRIPT_DIR/project_drift"
python3 -m project_drift schema --out "$SCRIPT_DIR/references/drift_report.schema.json" >/dev/null
python3 -m project_drift validate-report "$SCRIPT_DIR/references/example_drift_report.json" >/dev/null

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

if rg -n 'ArangoClient|/_api/cursor|sys\.path\.insert\(0, .*memory|memory/run\.sh learn|project-knowledge/run\.sh update' "$SCRIPT_DIR/project_drift" "$SCRIPT_DIR/hooks" >/tmp/project-drift-forbidden.$$ 2>/dev/null; then
  cat /tmp/project-drift-forbidden.$$
  rm -f /tmp/project-drift-forbidden.$$
  echo "project-drift sanity failed: forbidden direct durable-write pattern found" >&2
  exit 1
fi
rm -f /tmp/project-drift-forbidden.$$

cat > "$tmpdir/PROJECT_KNOWLEDGE.md" <<'PK'
# Project Knowledge: sample

**Last updated:** 2026-05-09 09:00 by agent
**Status:** Active development

## Current Understanding

- project_drift should not update PROJECT_KNOWLEDGE.md directly.
- The drift smoke command is currently broken and must not be trusted.

## Open Questions

- [ ] Should project_drift block on resolved open questions?
PK
knowledge_before="$(sha256sum "$tmpdir/PROJECT_KNOWLEDGE.md" | awk '{print $1}')"
cat > "$tmpdir/transcript.jsonl" <<'JSONL'
{"timestamp":"2026-05-09T10:00:00Z","type":"user","message":{"role":"user","content":"project_drift should focus on contradictions and stale claims, not random additions."}}
{"timestamp":"2026-05-09T10:01:00Z","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"./run.sh validate-report drift_report.json"},"tool_response":{"exit_code":0,"stdout":"Valid drift report: verdict=warn"}}
JSONL
(cd "$tmpdir" && "$SCRIPT_DIR/run.sh" scan --transcript "$tmpdir/transcript.jsonl" --out-dir "$tmpdir/out" --no-execute >/dev/null)
test -f "$tmpdir/out/prompt_payload.json"
test -f "$tmpdir/out/cleaned_transcript.json"
knowledge_after="$(sha256sum "$tmpdir/PROJECT_KNOWLEDGE.md" | awk '{print $1}')"
if [[ "$knowledge_before" != "$knowledge_after" ]]; then
  echo "project-drift sanity failed: no-execute scan mutated PROJECT_KNOWLEDGE.md" >&2
  exit 1
fi

cat > "$tmpdir/routine-tools.jsonl" <<'JSONL'
{"timestamp":"2026-05-09T10:00:00Z","hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"ls -la"},"tool_response":{"exit_code":0,"stdout":"total 8\n-rw-r--r-- PROJECT_KNOWLEDGE.md"}}
{"timestamp":"2026-05-09T10:00:01Z","hook_event_name":"PostToolUse","tool_name":"Grep","tool_input":{"pattern":"project_drift","path":"PROJECT_KNOWLEDGE.md"},"tool_response":{"status":"success","output":"project_drift should not update PROJECT_KNOWLEDGE.md directly."}}
JSONL
python3 -m project_drift clean-transcript --transcript "$tmpdir/routine-tools.jsonl" --out "$tmpdir/routine-cleaned.json" >/dev/null
python3 - "$tmpdir/routine-cleaned.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
if payload.get("observation_count") != 0:
    raise SystemExit(f"routine tool noise should not become drift evidence: {payload}")
if payload.get("routine_successful_tool_calls", 0) < 2:
    raise SystemExit(f"expected routine tool calls to be counted, got {payload}")
PY

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

python3 - "$SCRIPT_DIR/references/invalid_drift_reports.json" "$tmpdir/invalid-kind.json" <<'PY'
import json
import sys
from pathlib import Path

invalid_reports = json.loads(Path(sys.argv[1]).read_text())
for case in invalid_reports:
    if case["name"] == "invented_kind":
        Path(sys.argv[2]).write_text(json.dumps(case["report"], indent=2), encoding="utf-8")
        break
else:
    raise SystemExit("missing invented_kind invalid report fixture")
PY
if python3 -m project_drift validate-report "$tmpdir/invalid-kind.json" >/dev/null 2>&1; then
  echo "project-drift sanity failed: invalid closed-vocabulary report passed validation" >&2
  exit 1
fi

cat > "$tmpdir/fake_openai_server.py" <<'PY'
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

port_file = Path(sys.argv[1])
request_file = Path(sys.argv[2])

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        request_file.write_text(json.dumps({
            "path": self.path,
            "caller": self.headers.get("x-caller-skill"),
            "body": json.loads(body.decode("utf-8")),
        }, indent=2), encoding="utf-8")
        verdict = os.environ.get("FAKE_DRIFT_VERDICT", "warn")
        report = {
            "verdict": verdict,
            "severity": "high" if verdict == "block" else "medium",
            "summary": "Verifier evidence stale-dates the broken drift smoke command claim.",
            "candidates": [
                {
                    "id": "drift-sanity-001",
                    "kind": "stale_status",
                    "affected_section": "Current Understanding",
                    "current_project_knowledge_claim": "The drift smoke command is currently broken and must not be trusted.",
                    "new_evidence": "Transcript command ./run.sh validate-report drift_report.json exited with code 0.",
                    "why_it_matters": "Future agents would avoid a working verifier if the stale broken-status claim remains.",
                    "recommended_action": "block_until_reviewed" if verdict == "block" else "review_update",
                    "suggested_project_knowledge_update": "The drift smoke command passed validation and can be used as a verifier.",
                    "confidence": "high",
                    "evidence": [
                        {"type": "command", "value": "./run.sh validate-report drift_report.json"},
                        {"type": "verifier", "value": "exit_code=0"}
                    ],
                }
            ],
            "ignored": {
                "routine_successful_tool_calls": 0,
                "reason": "No routine-only tool calls were needed for the candidate."
            },
        }
        response = {"choices": [{"message": {"content": json.dumps(report)}}]}
        data = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        return

server = HTTPServer(("127.0.0.1", 0), Handler)
port_file.write_text(str(server.server_address[1]), encoding="utf-8")
server.serve_forever()
PY
python3 "$tmpdir/fake_openai_server.py" "$tmpdir/fake-openai-port" "$tmpdir/fake-openai-request.json" &
server_pid="$!"
trap 'kill "$server_pid" 2>/dev/null || true; rm -rf "$tmpdir"' EXIT
for _ in $(seq 1 50); do
  [[ -s "$tmpdir/fake-openai-port" ]] && break
  sleep 0.1
done
if [[ ! -s "$tmpdir/fake-openai-port" ]]; then
  echo "project-drift sanity failed: fake OpenAI-compatible server did not start" >&2
  exit 1
fi
fake_base_url="http://127.0.0.1:$(cat "$tmpdir/fake-openai-port")"
(cd "$tmpdir" && "$SCRIPT_DIR/run.sh" scan --transcript "$tmpdir/transcript.jsonl" --out-dir "$tmpdir/execute-out" --execute --llm-base-url "$fake_base_url" --since none >/dev/null)
python3 - "$tmpdir/execute-out/drift_report.json" "$tmpdir/execute-out/scan_summary.json" "$tmpdir/fake-openai-request.json" "$tmpdir/PROJECT_KNOWLEDGE.md" "$knowledge_before" <<'PY'
import json
import sys
from hashlib import sha256
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
summary = json.loads(Path(sys.argv[2]).read_text())
request = json.loads(Path(sys.argv[3]).read_text())
knowledge_path = Path(sys.argv[4])
knowledge_before = sys.argv[5]
if sha256(knowledge_path.read_bytes()).hexdigest() != knowledge_before:
    raise SystemExit("execute scan mutated PROJECT_KNOWLEDGE.md")
if summary.get("execute") is not True or summary.get("verdict") != "warn":
    raise SystemExit(f"execute summary missing verified verdict: {summary}")
if request.get("path") != "/v1/chat/completions":
    raise SystemExit(f"wrong LLM path: {request.get('path')}")
if request.get("caller") != "project-drift":
    raise SystemExit(f"missing project-drift caller header: {request.get('caller')}")
candidate = report["candidates"][0]
if candidate["kind"] != "stale_status":
    raise SystemExit(f"expected stale_status candidate, got {candidate['kind']}")
if "drift smoke command is currently broken" not in candidate["current_project_knowledge_claim"]:
    raise SystemExit(f"candidate did not cite exact affected claim: {candidate}")
if "future agents" not in candidate["why_it_matters"].lower():
    raise SystemExit(f"candidate lacks future-agent impact: {candidate}")
body = request["body"]
if body.get("response_format", {}).get("type") != "json_schema":
    raise SystemExit("prompt payload did not request strict json_schema response")
messages = body.get("messages", [])
joined = "\n".join(m.get("content", "") for m in messages)
if "PROJECT_KNOWLEDGE path" not in joined or "drift smoke command is currently broken" not in joined:
    raise SystemExit("prompt payload did not include project knowledge claims")
PY

hook_warn_output="$(printf '{"cwd":"%s","transcript_path":"%s","stop_hook_active":true}' "$tmpdir" "$tmpdir/transcript.jsonl" | PROJECT_DRIFT_SKILL_DIR="$SCRIPT_DIR" PROJECT_DRIFT_OUT_DIR="$tmpdir/python-hook-warn" PROJECT_DRIFT_LLM_BASE_URL="$fake_base_url" python3 "$SCRIPT_DIR/hooks/project_drift_stop.py")"
python3 - "$hook_warn_output" "$tmpdir/python-hook-warn" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
out_dir = Path(sys.argv[2])
if payload.get("continue") is not True:
    raise SystemExit(f"warn verdict hook must continue: {payload}")
if "project-drift warn" not in payload.get("systemMessage", ""):
    raise SystemExit(f"warn verdict hook did not surface project-drift warning: {payload}")
summary = json.loads((out_dir / "scan_summary.json").read_text())
if summary.get("execute") is not True or summary.get("verdict") != "warn":
    raise SystemExit(f"warn hook summary missing executed verdict: {summary}")
if not (out_dir / "drift_report.json").exists():
    raise SystemExit("warn hook did not write drift_report.json")
PY

hook_no_execute_output="$(printf '{"cwd":"%s","transcript_path":"%s","stop_hook_active":true}' "$tmpdir" "$tmpdir/transcript.jsonl" | PROJECT_DRIFT_SKILL_DIR="$SCRIPT_DIR" PROJECT_DRIFT_OUT_DIR="$tmpdir/python-hook-no-execute" PROJECT_DRIFT_HOOK_EXECUTE=0 python3 "$SCRIPT_DIR/hooks/project_drift_stop.py")"
python3 - "$hook_no_execute_output" "$tmpdir/python-hook-no-execute" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
out_dir = Path(sys.argv[2])
if payload.get("continue") is not True:
    raise SystemExit(f"no-execute hook must continue: {payload}")
if "no LLM drift verdict was executed" not in payload.get("systemMessage", ""):
    raise SystemExit(f"no-execute hook did not explain missing verdict: {payload}")
summary = json.loads((out_dir / "scan_summary.json").read_text())
if summary.get("execute") is not False or summary.get("observations", 0) < 1:
    raise SystemExit(f"no-execute summary missing candidate evidence: {summary}")
if not (out_dir / "prompt_payload.json").exists():
    raise SystemExit("no-execute hook did not write prompt_payload.json")
PY

kill "$server_pid" 2>/dev/null || true
FAKE_DRIFT_VERDICT=block python3 "$tmpdir/fake_openai_server.py" "$tmpdir/fake-openai-block-port" "$tmpdir/fake-openai-block-request.json" &
server_pid="$!"
for _ in $(seq 1 50); do
  [[ -s "$tmpdir/fake-openai-block-port" ]] && break
  sleep 0.1
done
if [[ ! -s "$tmpdir/fake-openai-block-port" ]]; then
  echo "project-drift sanity failed: fake block server did not start" >&2
  exit 1
fi
fake_block_base_url="http://127.0.0.1:$(cat "$tmpdir/fake-openai-block-port")"
hook_block_output="$(printf '{"cwd":"%s","transcript_path":"%s","stop_hook_active":true}' "$tmpdir" "$tmpdir/transcript.jsonl" | PROJECT_DRIFT_SKILL_DIR="$SCRIPT_DIR" PROJECT_DRIFT_OUT_DIR="$tmpdir/python-hook-block" PROJECT_DRIFT_LLM_BASE_URL="$fake_block_base_url" python3 "$SCRIPT_DIR/hooks/project_drift_stop.py")"
python3 - "$hook_block_output" "$tmpdir/python-hook-block" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
out_dir = Path(sys.argv[2])
if payload.get("continue") is not False:
    raise SystemExit(f"block verdict hook must stop: {payload}")
if "project-drift block" not in payload.get("systemMessage", ""):
    raise SystemExit(f"block verdict hook did not surface project-drift block: {payload}")
summary = json.loads((out_dir / "scan_summary.json").read_text())
if summary.get("execute") is not True or summary.get("verdict") != "block":
    raise SystemExit(f"block hook summary missing executed verdict: {summary}")
PY

hook_output="$(PROJECT_ROOT="$tmpdir" PROJECT_DRIFT_SKILL_DIR="$SCRIPT_DIR" TRANSCRIPT_PATH="$tmpdir/transcript.jsonl" PROJECT_DRIFT_OUT_DIR="$tmpdir/hook-out" "$SCRIPT_DIR/hooks/codex-stop-project-drift.sh")"
python3 - "$hook_output" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("continue") is not True:
    raise SystemExit(f"candidate-only hook must not block: {payload}")
if payload.get("suppressOutput") is not True:
    raise SystemExit(f"hook should suppress output after writing artifacts: {payload}")
PY
test -f "$tmpdir/hook-out/prompt_payload.json"

echo "project-drift sanity passed"
