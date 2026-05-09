#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ORCH="$ROOT/skills/orchestrate/run.sh"
TMP="${TMPDIR:-/tmp}/orchestrate-code-runner-live-e2e-$$"
REPO="$TMP/repo"
ORCH_HOME="$TMP/orchestrate-home"

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

curl -fsS --max-time 5 http://localhost:4001/health >/dev/null

mkdir -p "$REPO/src" "$REPO/tests" "$ORCH_HOME"
cd "$REPO"
git init -q
git config user.email "orchestrate-code-runner-e2e@example.invalid"
git config user.name "Orchestrate Code Runner E2E"
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

cat > "$TMP/plan.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: live code-runner patch artifact e2e
repo_root: "$REPO"
capability_overlap:
  - "No existing skill replaces this bounded composed /orchestrate -> /code-runner -> /scillm smoke."
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "E2E"
tasks:
  - id: "1"
    title: Fix answer function through code-runner
    lane: "0"
    runner: code-runner
    backend: codex
    mode: iterative
    skills:
      - code-runner
    prompt: "Modify only src/target.py. Make answer() return the integer 42. Do not change any other file."
    allowlist:
      - src/target.py
    read_context:
      - src/target.py
      - tests/test_target.py
    dirty_worktree_policy: isolated_worktree
    max_rounds: 1
    timeout_seconds: 900
    definition_of_done:
      command: "python -m pytest tests/test_target.py -q"
      assertion: "exit_code == 0"
    tests:
      - "python -m pytest tests/test_target.py -q"
    blind_tests:
      - command: "python -m pytest tests/test_target.py -q"
YAML

env -u CODE_RUNNER_MOCK_RESPONSE \
  SKILLS_DIR="$ROOT/skills" \
  ORCHESTRATE_HOME="$ORCH_HOME" \
  ORCHESTRATE_ALLOW_LOCAL_BLIND_TESTS=1 \
  CODE_RUNNER_LIVE_BACKEND=codex \
  "$ORCH" run "$TMP/plan.yaml"

SESSION_DIR="$(find "$ORCH_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$SESSION_DIR"

python - <<PY
import json
from pathlib import Path

repo = Path("$REPO")
session = Path("$SESSION_DIR")
status = json.loads((session / "status.json").read_text())
assert all(task["status"] == "passed" or task.get("raw_status") == "completed" for task in status["tasks"]), status

result_files = sorted(session.glob("1*.result.json"))
assert result_files, list(session.iterdir())
result = json.loads(result_files[-1].read_text())
assert result["status"] == "pass", result
assert result["dod_passed"] is True, result
assert result["execution_mode"] == "isolated_worktree", result
assert result["worktree_removed"] is True, result
assert not Path(result["worktree_path"]).exists(), result
assert result["backend"] == "codex", result

patch = Path(result["patch_artifact"])
assert patch.exists() and patch.read_text().strip(), result
patch_text = patch.read_text()
assert "src/target.py" in patch_text, patch_text
assert "return 42" in patch_text, patch_text
assert "scratch.txt" not in patch_text, patch_text

assert (repo / "src/target.py").read_text().strip().endswith("return 0")
assert (repo / "scratch.txt").read_text() == "operator scratch\n"
print("live orchestrate code-runner patch artifact e2e passed")
PY

test "$(git rev-parse HEAD)" = "$BASE_HEAD"
test "$(git status --short)" = "?? scratch.txt"
