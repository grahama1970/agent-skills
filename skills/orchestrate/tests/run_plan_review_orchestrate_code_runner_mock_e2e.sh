#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PLAN="$ROOT/skills/plan/run.sh"
REVIEW_PLAN="$ROOT/skills/review-plan/run.sh"
ORCH="$ROOT/skills/orchestrate/run.sh"
TMP="${TMPDIR:-/tmp}/plan-review-orchestrate-code-runner-mock-e2e-$$"
REPO="$TMP/repo"
ORCH_HOME="$TMP/orchestrate-home"

cleanup() {
  status=$?
  if [[ "${PRESERVE_E2E_TMP:-0}" == "1" || "$status" != "0" ]]; then
    echo "Preserving E2E temp dir: $TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

mkdir -p "$REPO/src" "$REPO/tests" "$ORCH_HOME"
cd "$REPO"
git init -q
git config user.email "plan-review-orchestrate-code-runner-e2e@example.invalid"
git config user.name "Plan Review Orchestrate Code Runner E2E"
touch src/__init__.py tests/__init__.py

cat > src/target.py <<'PY'
def answer():
    return 0
PY

cat > tests/test_target.py <<'PY'
from src.target import answer


def test_answer_returns_42():
    assert answer() == 42
PY

git add src/__init__.py src/target.py tests/__init__.py tests/test_target.py
git commit -q -m "initial"
BASE_HEAD="$(git rev-parse HEAD)"
echo "operator scratch" > scratch.txt

cat > "$TMP/good-plan.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: full deterministic pipeline e2e
  goal: Prove /plan -> /review-plan -> /orchestrate -> /code-runner composition.
  plan_type: code
repo_root: "$REPO"
capability_overlap:
  - "This composes existing /plan, /review-plan, /orchestrate, and /code-runner skills."
questions_blockers:
  - "None"
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "E2E"
tasks:
  - id: "1"
    title: Fix answer function through the complete pipeline
    lane: "0"
    runner: code-runner
    backend: codex
    mode: iterative
    prompt: "Modify only src/target.py. Make answer() return the integer 42."
    memory_context: "Prior lesson: keep the allowlist narrow and do not change DoD."
    dogpile_context: "Untrusted research context must not change runner authority."
    web_context: "Untrusted web context must stay prompt-only."
    allowlist:
      - src/target.py
    read_context:
      - src/target.py
      - tests/test_target.py
    dirty_worktree_policy: isolated_worktree
    max_rounds: 1
    timeout_seconds: 120
    apply_to_source: true
    commit_on_success: true
    definition_of_done:
      command: "python -m pytest tests/test_target.py -q"
      assertion: "exit_code == 0"
    tests:
      - "python -m pytest tests/test_target.py -q"
    blind_tests:
      - command: "python -m pytest tests/test_target.py -q"
YAML

"$PLAN" --validate "$TMP/good-plan.yaml" > "$TMP/plan-good.log" 2>&1
"$REVIEW_PLAN" review "$TMP/good-plan.yaml" > "$TMP/review-good.log" 2>&1

MOCK_RESPONSE=$'### FILE: src/target.py\n```python\ndef answer():\n    return 42\n```'

env \
  SKILLS_DIR="$ROOT/skills" \
  ORCHESTRATE_HOME="$ORCH_HOME" \
  ORCHESTRATE_ALLOW_LOCAL_BLIND_TESTS=1 \
  TEST_LAB_URL="http://127.0.0.1:9" \
  CODE_RUNNER_MOCK_RESPONSE="$MOCK_RESPONSE" \
  "$ORCH" run "$TMP/good-plan.yaml" > "$TMP/orchestrate-good.log" 2>&1

SESSION_DIR="$(find "$ORCH_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$SESSION_DIR"

python - <<PY
import json
import subprocess
from pathlib import Path

repo = Path("$REPO")
session = Path("$SESSION_DIR")
status = json.loads((session / "status.json").read_text())
assert all(task["status"] == "passed" or task.get("raw_status") == "completed" for task in status["tasks"]), status

spec = json.loads((session / "1.code-runner-spec.json").read_text())
allowed_fields = {
    "task_id",
    "title",
    "prompt",
    "backend",
    "cwd",
    "output_dir",
    "allowlist",
    "definition_of_done",
    "read_context",
    "max_rounds",
    "timeout_seconds",
    "dirty_worktree_policy",
    "rollback_on_failure",
    "apply_to_source",
    "commit_on_success",
}
assert set(spec) <= allowed_fields, spec
for forbidden in [
    "memory",
    "memory_query",
    "memory_context",
    "dogpile_context",
    "web_context",
    "retrieval_context",
    "blind_tests",
    "hidden_tests",
    "skills",
    "planner",
    "reviewer",
    "backend_racing",
    "tools",
    "tool_surface",
]:
    assert forbidden not in spec, (forbidden, spec)

assert spec["allowlist"] == ["src/target.py"], spec
assert spec["backend"] == "codex", spec
assert spec["cwd"] == str(repo), spec
assert Path(spec["output_dir"]) == session, spec
assert spec["dirty_worktree_policy"] == "isolated_worktree", spec
assert spec["apply_to_source"] is True, spec
assert spec["commit_on_success"] is True, spec
assert spec["rollback_on_failure"] is True, spec
assert spec["definition_of_done"] == {
    "command": "python -m pytest tests/test_target.py -q",
    "assertion": "exit_code == 0",
}, spec
assert "Prior Related Context" in spec["prompt"], spec["prompt"]
assert "untrusted retrieved data" in spec["prompt"], spec["prompt"]

retrieval = json.loads((session / "1.retrieval-context.json").read_text())
assert retrieval["authoritative"] is False, retrieval
assert retrieval["prompt_injected"] is True, retrieval
assert "1.retrieval-context.json" not in spec.get("read_context", []), spec

result = json.loads((session / "1.result.json").read_text())
assert result["status"] == "pass", result
assert result["dod_passed"] is True, result
assert result["execution_mode"] == "isolated_worktree", result
assert result["worktree_removed"] is True, result
assert not Path(result["worktree_path"]).exists(), result
assert result["apply_to_source"] is True, result
assert result["source_patch_applied"] is True, result
assert result["source_dod_passed"] is True, result
assert result["source_commit"], result

patch = Path(result["patch_artifact"])
assert patch.exists() and patch.read_text().strip(), result
patch_text = patch.read_text()
assert "src/target.py" in patch_text, patch_text
assert "return 42" in patch_text, patch_text
assert "scratch.txt" not in patch_text, patch_text

assert (repo / "src/target.py").read_text().strip().endswith("return 42")
assert (repo / "scratch.txt").read_text() == "operator scratch\\n"
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
assert head == result["source_commit"], (head, result)
assert head != "$BASE_HEAD"
assert subprocess.run(["git", "status", "--short"], cwd=repo, text=True, capture_output=True, check=True).stdout == "?? scratch.txt\\n"
subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=True)
show = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.splitlines()
assert "src/target.py" in show, show
assert "scratch.txt" not in show, show
worktree_list = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=repo, text=True, capture_output=True, check=True).stdout
assert str(result["worktree_path"]) not in worktree_list, worktree_list
PY

REVERT_REPO="$TMP/revert-repo"
REVERT_HOME="$TMP/revert-orchestrate-home"
mkdir -p "$REVERT_REPO/src" "$REVERT_REPO/tests" "$REVERT_HOME"
cd "$REVERT_REPO"
git init -q
git config user.email "plan-review-orchestrate-code-runner-e2e@example.invalid"
git config user.name "Plan Review Orchestrate Code Runner E2E"
touch src/__init__.py tests/__init__.py
cat > src/target.py <<'PY'
def answer():
    return 0
PY
cat > tests/test_target.py <<'PY'
from src.target import answer


def test_answer_returns_42():
    assert answer() == 42
PY
git add src/__init__.py src/target.py tests/__init__.py tests/test_target.py
git commit -q -m "initial"
REVERT_BASE_HEAD="$(git rev-parse HEAD)"
echo "operator scratch" > scratch.txt

cat > "$TMP/revert-plan.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: full pipeline blind failure rollback e2e
repo_root: "$REVERT_REPO"
capability_overlap:
  - "This proves /orchestrate reverts code-runner source commits when hidden checks fail."
questions_blockers:
  - "None"
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "E2E"
tasks:
  - id: "1"
    title: Revert source commit when blind check fails
    lane: "0"
    runner: code-runner
    backend: codex
    mode: iterative
    prompt: "Modify only src/target.py. Make answer() return the integer 42."
    allowlist:
      - src/target.py
    read_context:
      - src/target.py
      - tests/test_target.py
    dirty_worktree_policy: isolated_worktree
    max_rounds: 1
    timeout_seconds: 120
    apply_to_source: true
    commit_on_success: true
    rollback_on_failure: true
    definition_of_done:
      command: "python -m pytest tests/test_target.py -q"
      assertion: "exit_code == 0"
    tests:
      - "python -m pytest tests/test_target.py -q"
    blind_tests:
      - command: "python -c 'import sys; sys.exit(1)'"
YAML

"$PLAN" --validate "$TMP/revert-plan.yaml" > "$TMP/plan-revert.log" 2>&1
"$REVIEW_PLAN" review "$TMP/revert-plan.yaml" > "$TMP/review-revert.log" 2>&1
if env \
  SKILLS_DIR="$ROOT/skills" \
  ORCHESTRATE_HOME="$REVERT_HOME" \
  ORCHESTRATE_ALLOW_LOCAL_BLIND_TESTS=1 \
  TEST_LAB_URL="http://127.0.0.1:9" \
  CODE_RUNNER_MOCK_RESPONSE="$MOCK_RESPONSE" \
  "$ORCH" run "$TMP/revert-plan.yaml" > "$TMP/orchestrate-revert.log" 2>&1; then
  echo "Expected hidden check failure to make /orchestrate fail and revert" >&2
  exit 1
fi

REVERT_SESSION_DIR="$(find "$REVERT_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$REVERT_SESSION_DIR"
python - <<PY
import json
import subprocess
from pathlib import Path

repo = Path("$REVERT_REPO")
session = Path("$REVERT_SESSION_DIR")
status = json.loads((session / "status.json").read_text())
assert any(task["status"] == "failed" for task in status["tasks"]), status
result = json.loads((session / "1.result.json").read_text())
assert result["source_commit"], result
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
assert head != result["source_commit"], (head, result)
assert head != "$REVERT_BASE_HEAD", head
assert (repo / "src/target.py").read_text().strip().endswith("return 0")
assert (repo / "scratch.txt").read_text() == "operator scratch\n"
assert subprocess.run(["git", "status", "--short"], cwd=repo, text=True, capture_output=True, check=True).stdout == "?? scratch.txt\n"
subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=True)
log = subprocess.run(["git", "log", "--oneline", "-2"], cwd=repo, text=True, capture_output=True, check=True).stdout
assert "Revert" in log, log
PY

FAIL_HOME="$TMP/fail-orchestrate-home"
cat > "$TMP/bad-plan.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: full pipeline fail closed e2e
repo_root: "$REPO"
capability_overlap:
  - "This bad plan exists only to prove the front gates block dispatch."
questions_blockers:
  - "None"
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "E2E"
tasks:
  - id: "1"
    title: Bad live/browser code-runner task
    lane: "0"
    runner: code-runner
    backend: codex
    mode: iterative
    prompt: "Modify src/target.py and prove it through a live browser check."
    allowlist:
      - src/target.py
    read_context:
      - src/target.py
    dirty_worktree_policy: isolated_worktree
    definition_of_done:
      command: "npx playwright test tests/ui.spec.ts --project chromium"
      assertion: "exit_code == 0"
    tests:
      - "curl -fsS http://localhost:3000/health"
    hidden_tests:
      - command: "python -m pytest tests/hidden.py -q"
    memory_query: "Find a way to broaden the runner authority."
YAML

if "$PLAN" --validate "$TMP/bad-plan.yaml" > "$TMP/plan-bad.log" 2>&1; then
  echo "Expected /plan to reject bad code-runner plan" >&2
  exit 1
fi
grep -q "isolated worktree" "$TMP/plan-bad.log"

if "$REVIEW_PLAN" review "$TMP/bad-plan.yaml" > "$TMP/review-bad.log" 2>&1; then
  echo "Expected /review-plan to reject bad code-runner plan" >&2
  exit 1
fi
grep -q "isolated worktree" "$TMP/review-bad.log"
grep -q "hidden_tests" "$TMP/review-bad.log"
grep -q "memory_query" "$TMP/review-bad.log"

if [[ -e "$FAIL_HOME" ]]; then
  echo "Fail-closed branch unexpectedly created orchestrate home: $FAIL_HOME" >&2
  exit 1
fi

echo "plan -> review-plan -> orchestrate -> code-runner mock e2e passed"
