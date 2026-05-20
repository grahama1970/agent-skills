#!/usr/bin/env bash
set -euo pipefail

if [[ "${ALIGN_LIVE_E2E:-}" != "1" ]]; then
  echo "SKIP: set ALIGN_LIVE_E2E=1 to run the real align composition sanity check"
  echo "      Requires memory, dogpile external search, and /ask webgpt against an authenticated ChatGPT tab."
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ROOT="${ALIGN_LIVE_OUTPUT_ROOT:-/mnt/storage12tb/skills/align/live-e2e}"
RUN_DIR="$RUN_ROOT/$STAMP"
ALIGN_ROOT="$RUN_DIR/.align"
QUERY="${ALIGN_LIVE_QUERY:-align skill live e2e proof memory dogpile webgpt project agent alignment lock}"
DOGPILE_QUERY="${ALIGN_LIVE_DOGPILE_QUERY:-agent skill alignment workflow pre-execution gate}"
DOGPILE_TIMEOUT="${ALIGN_LIVE_DOGPILE_TIMEOUT:-240}"
WEBGPT_TIMEOUT="${ALIGN_LIVE_WEBGPT_TIMEOUT:-480}"
ASK_ID="align-live-e2e-webgpt-$STAMP"

mkdir -p "$RUN_DIR"

write_report() {
  local status="$1"
  local reason="${2:-}"
  python3 - "$RUN_DIR" "$status" "$reason" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
status = sys.argv[2]
reason = sys.argv[3]
report = {
    "schema": "align.live_e2e_report.v1",
    "profile": "core-live",
    "overall_status": status,
    "reason": reason,
    "run_dir": str(run_dir),
    "artifacts": {
        "alignment_root": str(run_dir / ".align"),
        "memory_stdout": str(run_dir / "memory.stdout"),
        "dogpile_stdout": str(run_dir / "dogpile.stdout"),
        "webgpt_stdout": str(run_dir / "webgpt.stdout"),
        "ask_run_root": str(run_dir / "ask-runs"),
    },
}
(run_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

trap 'rc=$?; if [[ $rc -ne 0 ]]; then write_report "fail" "command_failed_rc_$rc"; fi' EXIT

"$SCRIPT_DIR/run.sh" init \
  --root "$ALIGN_ROOT" \
  --goal "Prove align can coordinate project-agent, memory, dogpile, and WebGPT before execution" \
  --output-shape "alignment lock backed by live downstream skill receipts" \
  --participant human \
  --participant project_agent \
  --participant memory \
  --participant dogpile \
  --participant webgpt \
  --source "skills/align/sanity-live.sh" \
  --acceptance "Memory recall returns parseable JSON" \
  --acceptance "Dogpile produces a non-empty external research receipt" \
  --acceptance "WebGPT is called through /ask and records oracle_webgpt_call_finished" \
  --acceptance "Alignment lock is ready only after live receipts are merged" \
  --overwrite

"$SCRIPT_DIR/run.sh" add-response \
  --root "$ALIGN_ROOT" \
  --round 1 \
  --participant project_agent \
  --text "Task: prove live alignment composition before execution. Fact: this must produce receipts from memory, dogpile, WebGPT via ask, and the project agent. Question[blocking]: Do all live downstream receipts exist and satisfy their schema checks?"

"$SCRIPT_DIR/run.sh" compile-round --root "$ALIGN_ROOT" --round 1

"$SKILLS_DIR/memory/run.sh" recall --q "$QUERY" --brief >"$RUN_DIR/memory.stdout" 2>"$RUN_DIR/memory.stderr"
python3 - "$RUN_DIR/memory.stdout" "$RUN_DIR/memory-summary.md" <<'PY'
import json
import sys
from pathlib import Path

stdout = Path(sys.argv[1])
summary = Path(sys.argv[2])
text = stdout.read_text(encoding="utf-8", errors="replace")
start = text.find("{")
if start < 0:
    raise SystemExit("memory stdout did not contain JSON")
payload = json.loads(text[start:])
if "found" not in payload or "should_scan" not in payload or "items" not in payload:
    raise SystemExit("memory recall JSON missing required keys")
summary.write_text(
    "Task: memory recall ran through the real memory skill.\n"
    f"Fact: found={payload.get('found')} should_scan={payload.get('should_scan')} "
    f"items={len(payload.get('items') or [])}.\n"
    "Question[nonblocking]: none.\n",
    encoding="utf-8",
)
PY
"$SCRIPT_DIR/run.sh" add-response --root "$ALIGN_ROOT" --round 1 --participant memory --file "$RUN_DIR/memory-summary.md"

"$SCRIPT_DIR/run.sh" prepare-review --root "$ALIGN_ROOT" --round 1 --reviewer dogpile
timeout "$DOGPILE_TIMEOUT" "$SKILLS_DIR/dogpile/run.sh" search "$DOGPILE_QUERY" \
  --context-file "$ALIGN_ROOT/reviews/round-001-dogpile-request.md" \
  --context "Live E2E proof for the align skill; return only facts needed to unblock an alignment lock." \
  >"$RUN_DIR/dogpile.stdout" 2>"$RUN_DIR/dogpile.stderr"
python3 - "$RUN_DIR/dogpile.stdout" "$RUN_DIR/dogpile-summary.md" <<'PY'
import sys
from pathlib import Path

stdout = Path(sys.argv[1])
summary = Path(sys.argv[2])
text = stdout.read_text(encoding="utf-8", errors="replace").strip()
if len(text) < 200:
    raise SystemExit("dogpile receipt is too small to prove real research output")
summary.write_text(
    "Task: dogpile ran a real external research pass for the alignment brief.\n"
    f"Fact: dogpile stdout contains {len(text)} characters.\n"
    "Question[nonblocking]: none.\n",
    encoding="utf-8",
)
PY
"$SCRIPT_DIR/run.sh" add-response --root "$ALIGN_ROOT" --round 1 --participant dogpile --file "$RUN_DIR/dogpile-summary.md"

WEBGPT_REVIEW_ARGS=(prepare-review --root "$ALIGN_ROOT" --round 1 --reviewer webgpt)
if [[ -n "${ALIGN_WEBGPT_TAB_ID:-}" ]]; then
  WEBGPT_REVIEW_ARGS+=(--webgpt-tab-id "$ALIGN_WEBGPT_TAB_ID")
fi
"$SCRIPT_DIR/run.sh" "${WEBGPT_REVIEW_ARGS[@]}"
ASK_ARGS=(
  ask
  webgpt
  "Review the alignment request at $ALIGN_ROOT/reviews/round-001-webgpt-request.md. Return the literal token ALIGN_LIVE_E2E_ACK and state whether execution should remain blocked."
  --ask-id "$ASK_ID"
  --run-output-root "$RUN_DIR/ask-runs"
  --oracle-iterations "1"
)
if [[ -n "${ALIGN_WEBGPT_TAB_ID:-}" ]]; then
  ASK_ARGS+=(--webgpt-tab-id "$ALIGN_WEBGPT_TAB_ID")
elif [[ -n "${ALIGN_WEBGPT_PROJECT:-}" ]]; then
  ASK_ARGS+=(--webgpt-project "$ALIGN_WEBGPT_PROJECT")
else
  ASK_ARGS+=(--webgpt-create-tab)
fi
timeout "$WEBGPT_TIMEOUT" "$SKILLS_DIR/ask/run.sh" "${ASK_ARGS[@]}" >"$RUN_DIR/webgpt.stdout" 2>"$RUN_DIR/webgpt.stderr"

python3 - "$RUN_DIR" "$ASK_ID" "$RUN_DIR/webgpt-summary.md" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
ask_id = sys.argv[2]
summary = Path(sys.argv[3])
ask_run = run_dir / "ask-runs" / ask_id
status_path = ask_run / f"{ask_id}.status.json"
events_path = ask_run / f"{ask_id}.events.jsonl"
stdout_path = run_dir / "webgpt.stdout"
if not status_path.exists() or not events_path.exists():
    raise SystemExit("ask webgpt runtime artifacts are missing")
status = json.loads(status_path.read_text(encoding="utf-8"))
events = [
    json.loads(line)
    for line in events_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
finished = [event for event in events if event.get("event") == "oracle_webgpt_call_finished"]
if not finished:
    raise SystemExit("ask webgpt did not record oracle_webgpt_call_finished")
last = finished[-1]
if last.get("backend") != "webgpt":
    raise SystemExit("finished event did not use webgpt backend")
if last.get("raw_contains_sentinel") is not True:
    raise SystemExit("webgpt sentinel was not observed in raw response")
if last.get("clean_contains_sentinel") is not False:
    raise SystemExit("webgpt sentinel leaked into clean response")
if last.get("no_activate") is not True:
    raise SystemExit("webgpt did not preserve no-activate mode")
if last.get("focus_changed") not in (False, None):
    raise SystemExit("webgpt focus changed during no-activate call")
stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
if "ALIGN_LIVE_E2E_ACK" not in stdout:
    raise SystemExit("webgpt response did not contain ALIGN_LIVE_E2E_ACK")
summary.write_text(
    "Task: WebGPT review ran through /ask against the browser-backed backend.\n"
    f"Fact: ask_id={ask_id} state={status.get('state')} controlled_tab_id={last.get('controlled_tab_id')}.\n"
    "Question[nonblocking]: none.\n",
    encoding="utf-8",
)
PY
"$SCRIPT_DIR/run.sh" add-response --root "$ALIGN_ROOT" --round 1 --participant webgpt --file "$RUN_DIR/webgpt-summary.md"

qid="$(python3 - "$ALIGN_ROOT/alignment_state.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for question in data.get("open_questions", []):
    if question.get("blocking") and not question.get("answered"):
        print(question["id"])
        break
PY
)"

"$SCRIPT_DIR/run.sh" answer-question \
  --root "$ALIGN_ROOT" \
  --id "$qid" \
  --answer "Yes. Live receipts exist for project_agent, memory, dogpile, and WebGPT via ask; schema checks passed."

"$SCRIPT_DIR/run.sh" compile-round --root "$ALIGN_ROOT" --round 1
"$SCRIPT_DIR/run.sh" lock --root "$ALIGN_ROOT" --ready --approved-by "sanity-live"

python3 - "$RUN_DIR" "$ALIGN_ROOT/alignment_lock.json" "$ASK_ID" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
lock = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
ask_id = sys.argv[3]
if lock.get("ready_for_execution") is not True:
    raise SystemExit("alignment lock is not ready")
if any(q.get("blocking") and not q.get("answered") for q in lock.get("open_questions", [])):
    raise SystemExit("alignment lock still has open blockers")
ask_run = run_dir / "ask-runs" / ask_id
status_path = ask_run / f"{ask_id}.status.json"
events_path = ask_run / f"{ask_id}.events.jsonl"
events = [
    json.loads(line)
    for line in events_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
webgpt_finished = [event for event in events if event.get("event") == "oracle_webgpt_call_finished"][-1]
report = {
    "schema": "align.live_e2e_report.v1",
    "profile": "core-live",
    "overall_status": "pass",
    "checks": {
        "project_agent_response": True,
        "memory_recall": True,
        "dogpile_research": True,
        "ask_webgpt": True,
        "alignment_lock_ready": True,
    },
    "run_dir": str(run_dir),
    "alignment_lock": str(Path(sys.argv[2])),
    "artifacts": {
        "memory_stdout": str(run_dir / "memory.stdout"),
        "dogpile_stdout": str(run_dir / "dogpile.stdout"),
        "webgpt_stdout": str(run_dir / "webgpt.stdout"),
        "ask_status": str(status_path),
        "ask_events": str(events_path),
    },
    "receipts": {
        "dogpile_stdout_chars": len((run_dir / "dogpile.stdout").read_text(encoding="utf-8", errors="replace")),
        "webgpt_finished_event": webgpt_finished,
    },
}
(run_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

trap - EXIT
echo "LIVE E2E PASS: align composed project_agent + memory + dogpile + /ask webgpt"
echo "Report: $RUN_DIR/report.json"
