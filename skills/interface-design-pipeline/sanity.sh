#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

test -f "$SKILL_DIR/SKILL.md"
test -x "$SKILL_DIR/run.sh"
test -x "$SKILL_DIR/scripts/pipeline.py"
test -x "$SKILL_DIR/scripts/check_artifact.py"
test -x "$SKILL_DIR/scripts/interface_loop_agent.py"
test -f "$SKILL_DIR/examples/sparta-chat.json"
test -f "$SKILL_DIR/examples/SPARTA_CHAT_BRIEF.md"

python3 -m py_compile \
  "$SKILL_DIR/scripts/pipeline.py" \
  "$SKILL_DIR/scripts/pipeline_common.py" \
  "$SKILL_DIR/scripts/pipeline_planner.py" \
  "$SKILL_DIR/scripts/check_artifact.py" \
  "$SKILL_DIR/scripts/interface_loop_agent.py" \
  "$SKILL_DIR/scripts/research_phase.py"
python3 -m unittest discover -s "$SKILL_DIR/tests" -p 'test_*.py'
"$SKILL_DIR/run.sh" validate --manifest "$SKILL_DIR/examples/sparta-chat.json" >/dev/null

run_dir="$(mktemp -d)/sparta-chat-plan"
"$SKILL_DIR/run.sh" plan --manifest "$SKILL_DIR/examples/sparta-chat.json" --output "$run_dir" >/dev/null
test -f "$run_dir/phases/03-mockup-tournament/plan.json"
test -f "$run_dir/phases/05-implementation-tournament/plan.json"

echo "interface-design-pipeline sanity: PASS"
