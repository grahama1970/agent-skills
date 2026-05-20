#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

"$SCRIPT_DIR/run.sh" init \
  --root "$ROOT/.align" \
  --goal "Create a source-derived workflow storyboard before rendering" \
  --output-shape "alignment lock for a future infographic request" \
  --participant human \
  --participant project_agent \
  --participant project_knowledge \
  --participant scillm \
  --participant ask \
  --participant dogpile \
  --participant webgpt \
  --source "PROJECT_KNOWLEDGE.md" \
  --acceptance "No execution before blocking questions are answered" \
  --webgpt-tab-id 837343529

"$SCRIPT_DIR/run.sh" add-response \
  --root "$ROOT/.align" \
  --round 1 \
  --participant project_agent \
  --text "Task: align all parties before execution. Fact: the output must be a lock, not a render. Question[blocking]: Which concrete sample project anchors the artifact?"

"$SCRIPT_DIR/run.sh" compile-round --root "$ROOT/.align" --round 1

if "$SCRIPT_DIR/run.sh" lock --root "$ROOT/.align" --ready --approved-by human >/tmp/align-lock.out 2>/tmp/align-lock.err; then
  echo "FAIL: ready lock succeeded with open blocking question" >&2
  exit 1
fi

qid="$(python3 - "$ROOT/.align/alignment_state.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data["open_questions"][0]["id"])
PY
)"

"$SCRIPT_DIR/run.sh" answer-question \
  --root "$ROOT/.align" \
  --id "$qid" \
  --answer "Use an Incident Intake Portal sample with three phases."

"$SCRIPT_DIR/run.sh" prepare-review \
  --root "$ROOT/.align" \
  --round 1 \
  --reviewer scillm \
  --scillm-model gpt-5.5 \
  --reasoning-effort high \
  --persona-prompt "You are a skeptical alignment reviewer."
"$SCRIPT_DIR/run.sh" prepare-review --root "$ROOT/.align" --round 1 --reviewer ask
"$SCRIPT_DIR/run.sh" prepare-review --root "$ROOT/.align" --round 1 --reviewer dogpile
"$SCRIPT_DIR/run.sh" prepare-review --root "$ROOT/.align" --round 1 --reviewer webgpt --webgpt-tab-id 837343529
"$SCRIPT_DIR/run.sh" lock --root "$ROOT/.align" --ready --approved-by human

python3 - "$ROOT/.align/alignment_lock.json" <<'PY'
import json, sys
lock = json.load(open(sys.argv[1]))
assert lock["schema"] == "align.lock.v1"
assert lock["ready_for_execution"] is True
assert lock["participants"] == ["human", "project_agent", "project_knowledge", "scillm", "ask", "dogpile", "webgpt"]
assert lock["open_questions"][0]["answered"] is True
PY

test -f "$ROOT/.align/reviews/round-001-scillm-request.json"
test -x "$ROOT/.align/reviews/round-001-scillm-command.sh"
test -f "$ROOT/.align/reviews/round-001-ask-request.md"
test -f "$ROOT/.align/reviews/round-001-dogpile-request.md"
test -f "$ROOT/.align/reviews/round-001-webgpt-request.md"
test -x "$ROOT/.align/reviews/round-001-webgpt-ask-command.sh"
grep -q "skills/ask/run.sh ask webgpt" "$ROOT/.align/reviews/round-001-webgpt-ask-command.sh"
grep -q -- "--webgpt-tab-id 837343529" "$ROOT/.align/reviews/round-001-webgpt-ask-command.sh"
grep -q "localhost:4001/v1/chat/completions" "$ROOT/.align/reviews/round-001-scillm-command.sh"
grep -q "skeptical alignment reviewer" "$ROOT/.align/reviews/round-001-scillm-request.json"

echo "SANITY PASS: align round loop, blocking question gate, review requests, and ready lock"
