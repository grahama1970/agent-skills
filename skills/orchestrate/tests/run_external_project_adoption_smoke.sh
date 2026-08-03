#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PLAN="$ROOT/skills/plan/run.sh"
REVIEW_PLAN="$ROOT/skills/review-plan/run.sh"
ORCH="$ROOT/skills/orchestrate/run.sh"
TMP="${TMPDIR:-/tmp}/external-project-adoption-smoke-$$"
REPO="$TMP/repo"
FAIL_HOME="$TMP/orchestrate-fail-home"
PASS_HOME="$TMP/orchestrate-pass-home"
export PLAN_ARTIFACT_ROOT="${PLAN_ARTIFACT_ROOT:-$TMP/plan-artifacts}"

cleanup() {
  status=$?
  if [[ "${PRESERVE_E2E_TMP:-0}" == "1" || "$status" != "0" ]]; then
    echo "Preserving external adoption smoke temp dir: $TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

mkdir -p "$REPO/skills/hack/tests" "$FAIL_HOME" "$PASS_HOME"
cd "$REPO"
git init -q
git config user.email "external-adoption-smoke@example.invalid"
git config user.name "External Project Adoption Smoke"

cat > README.md <<'MD'
# external adoption smoke
MD

touch skills/__init__.py skills/hack/__init__.py skills/hack/tests/__init__.py

cat > skills/hack/tests/test_evolutionary_campaign.py <<'PY'
import unittest

from skills.hack.evolutionary_campaign import answer


class EvolutionaryCampaignTests(unittest.TestCase):
    def test_answer_is_42(self):
        self.assertEqual(answer(), 42)


if __name__ == "__main__":
    unittest.main()
PY

git add README.md skills/__init__.py skills/hack/__init__.py skills/hack/tests/__init__.py skills/hack/tests/test_evolutionary_campaign.py
git commit -q -m "initial tracked project"

cat > skills/hack/evolutionary_campaign.py <<'PY'
def answer():
    return 0
PY

echo "operator scratch" > scratch.txt

cat > "$TMP/hack-plan.yaml" <<YAML
version: 1
kind: orchestrate-plan
metadata:
  title: external project adoption smoke
  goal: Prove project agents get a deterministic baseline failure, then success after a narrow baseline commit.
  plan_type: code
repo_root: "$REPO"
capability_overlap:
  - "This composes /plan, /review-plan, /orchestrate, and /code-runner against an external git repo."
questions_blockers:
  - "None"
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "External adoption"
tasks:
  - id: "hack-1"
    title: Continue hack runtime implementation
    lane: "0"
    runner: code-runner
    backend: codex
    mode: iterative
    prompt: "Modify only skills/hack/evolutionary_campaign.py. Make answer() return the integer 42."
    allowlist:
      - skills/hack/evolutionary_campaign.py
    read_context:
      - skills/hack/evolutionary_campaign.py
      - skills/hack/tests/test_evolutionary_campaign.py
    dirty_worktree_policy: isolated_worktree
    max_rounds: 1
    timeout_seconds: 120
    apply_to_source: true
    commit_on_success: true
    rollback_on_failure: true
    definition_of_done:
      command: "python -m unittest discover -s skills/hack/tests -q"
      assertion: "exit_code == 0"
    tests:
      - "python -m unittest discover -s skills/hack/tests -q"
    blind_tests:
      - command: "python -m unittest discover -s skills/hack/tests -q"
YAML

"$PLAN" --validate "$TMP/hack-plan.yaml" > "$TMP/plan.log" 2>&1
"$REVIEW_PLAN" review "$TMP/hack-plan.yaml" > "$TMP/review.log" 2>&1

if env \
  SKILLS_DIR="$ROOT/skills" \
  ORCHESTRATE_HOME="$FAIL_HOME" \
  ORCHESTRATE_ALLOW_LOCAL_BLIND_TESTS=1 \
  TEST_LAB_URL="http://127.0.0.1:9" \
  CODE_RUNNER_MOCK_RESPONSE=$'### FILE: skills/hack/evolutionary_campaign.py\n```python\ndef answer():\n    return 42\n```' \
  "$ORCH" run "$TMP/hack-plan.yaml" > "$TMP/orchestrate-fail.log" 2>&1; then
  echo "Expected untracked existing allowlist file to fail baseline preflight" >&2
  exit 1
fi

FAIL_SESSION="$(find "$FAIL_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$FAIL_SESSION"

python - <<PY
import json
from pathlib import Path

session = Path("$FAIL_SESSION")
artifact = session / "hack-1.baseline-preflight.json"
assert artifact.exists(), sorted(p.name for p in session.iterdir())
payload = json.loads(artifact.read_text())
assert payload["failure_code"] == "CODE_RUNNER_UNTRACKED_BASELINE_REQUIRED", payload
assert payload["untracked_existing_allowlist"] == ["skills/hack/evolutionary_campaign.py"], payload
assert payload["untracked_read_context"] == ["skills/hack/evolutionary_campaign.py"], payload
assert not (session / "hack-1.code-runner-spec.json").exists()
failure_bundle = session / "hack-1.failure-bundle.json"
assert failure_bundle.exists(), sorted(p.name for p in session.iterdir())
bundle = json.loads(failure_bundle.read_text())
assert bundle["failure_code"] == "CODE_RUNNER_UNTRACKED_BASELINE_REQUIRED", bundle
PY

git add skills/hack/evolutionary_campaign.py
git commit -q -m "baseline hack runtime file"
BASELINE_HEAD="$(git rev-parse HEAD)"

env \
  SKILLS_DIR="$ROOT/skills" \
  ORCHESTRATE_HOME="$PASS_HOME" \
  ORCHESTRATE_ALLOW_LOCAL_BLIND_TESTS=1 \
  TEST_LAB_URL="http://127.0.0.1:9" \
  CODE_RUNNER_MOCK_RESPONSE=$'### FILE: skills/hack/evolutionary_campaign.py\n```python\ndef answer():\n    return 42\n```' \
  "$ORCH" run "$TMP/hack-plan.yaml" > "$TMP/orchestrate-pass.log" 2>&1

PASS_SESSION="$(find "$PASS_HOME/structured" -maxdepth 1 -type d -name 'session-*' | sort | tail -1)"
test -n "$PASS_SESSION"

python - <<PY
import json
import subprocess
from pathlib import Path

repo = Path("$REPO")
session = Path("$PASS_SESSION")
status = json.loads((session / "status.json").read_text())
assert all(task["status"] == "passed" or task.get("raw_status") == "completed" for task in status["tasks"]), status
assert not (session / "hack-1.baseline-preflight.json").exists(), sorted(p.name for p in session.iterdir())

spec = json.loads((session / "hack-1.code-runner-spec.json").read_text())
assert spec["allowlist"] == ["skills/hack/evolutionary_campaign.py"], spec
assert spec["read_context"] == [
    "skills/hack/evolutionary_campaign.py",
    "skills/hack/tests/test_evolutionary_campaign.py",
], spec
assert spec["apply_to_source"] is True, spec
assert spec["commit_on_success"] is True, spec

result = json.loads((session / "hack-1.result.json").read_text())
assert result["status"] == "pass", result
assert result["dod_passed"] is True, result
assert result["source_patch_applied"] is True, result
assert result["source_dod_passed"] is True, result
assert result["source_commit"], result
assert result["worktree_removed"] is True, result
assert not Path(result["worktree_path"]).exists(), result

head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip()
assert head == result["source_commit"], (head, result)
assert head != "$BASELINE_HEAD", head
assert (repo / "skills/hack/evolutionary_campaign.py").read_text().strip().endswith("return 42")
assert (repo / "scratch.txt").read_text() == "operator scratch\n"
assert subprocess.run(["git", "status", "--short"], cwd=repo, text=True, capture_output=True, check=True).stdout == "?? scratch.txt\n"
subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=True)
show = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.splitlines()
assert show == ["skills/hack/evolutionary_campaign.py"], show
worktrees = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=repo, text=True, capture_output=True, check=True).stdout
assert str(result["worktree_path"]) not in worktrees, worktrees
PY

echo "external project adoption smoke passed"
