#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ORCH="$ROOT/skills/orchestrate/run.sh"
TMP="${TMPDIR:-/tmp}/orchestrate-scillm-live-smoke-$$"
REPO="$TMP/repo"
ORCH_HOME="$TMP/orchestrate-home"

cleanup() {
  status=$?
  if [[ "${PRESERVE_E2E_TMP:-0}" == "1" || "$status" != "0" ]]; then
    echo "Preserving live smoke temp dir: $TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

curl -fsS --max-time 3 http://localhost:4001/health >/dev/null
mkdir -p "$REPO" "$ORCH_HOME"

cat > "$TMP/scillm-smoke.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: live scillm smoke
repo_root: "$REPO"
capability_overlap:
  - "Live smoke for orchestrate direct scillm runner request path."
questions_blockers:
  - "None"
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "Smoke"
tasks:
  - id: "1"
    title: Live scillm one-shot smoke
    lane: "0"
    runner: scillm
    backend: text
    mode: one_shot
    prompt: "Reply with exactly: OK"
    definition_of_done:
      command: "true"
      assertion: "exit_code == 0"
YAML

ORCHESTRATE_HOME="$ORCH_HOME" ORCHESTRATE_ALLOW_NON_CORE_RUNNERS=1 \
  env -u VIRTUAL_ENV "$ORCH" run "$TMP/scillm-smoke.yaml" > "$TMP/out.log" 2>&1

SESSION_DIR="$(find "$ORCH_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$SESSION_DIR"
test -s "$SESSION_DIR/1.response.txt"

python - <<PY
import json
from pathlib import Path
session = Path("$SESSION_DIR")
status = json.loads((session / "status.json").read_text())
assert all(task["status"] == "passed" or task.get("raw_status") == "completed" for task in status["tasks"]), status
text = (session / "1.response.txt").read_text().strip()
assert text, "empty scillm response"
print("live orchestrate scillm smoke passed:", text[:120].replace("\n", " "))
PY
