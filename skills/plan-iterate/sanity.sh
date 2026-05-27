#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_SH="$SCRIPT_DIR/run.sh"
TMP_ROOT="${TMPDIR:-/tmp}/plan-iterate-sanity.$$"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "SANITY FAIL: $*" >&2
  exit 1
}

expect_fail_contains() {
  local expected="$1"
  shift
  local log="$TMP_ROOT/expected-failure.log"
  if "$@" >"$log.out" 2>"$log"; then
    cat "$log.out" >&2 || true
    fail "expected command to fail: $*"
  fi
  if ! grep -Fq "$expected" "$log"; then
    echo "--- stderr ---" >&2
    cat "$log" >&2
    fail "expected failure output to contain: $expected"
  fi
}

mkdir -p "$TMP_ROOT"

REPO="$TMP_ROOT/repo"
PHASE_ROOT="$TMP_ROOT/.plan-iterate"
PHASE="phase-01-sanity"
PHASE_DIR="$PHASE_ROOT/$PHASE"
mkdir -p "$REPO"

git -C "$REPO" init -q
git -C "$REPO" config user.email plan-iterate-sanity@example.invalid
git -C "$REPO" config user.name plan-iterate-sanity
printf 'before\n' > "$REPO/target.txt"
git -C "$REPO" add target.txt
git -C "$REPO" commit -q -m 'initial sanity fixture'
printf 'after\n' > "$REPO/target.txt"

"$RUN_SH" --root "$PHASE_ROOT" init --phase "$PHASE" >/dev/null

mkdir -p "$PHASE_DIR/evidence-artifacts" "$PHASE_DIR/validation-logs"
printf 'deterministic proof\n' > "$PHASE_DIR/evidence-artifacts/proof.txt"
printf 'validation ok\n' > "$PHASE_DIR/validation-logs/local.log"

python3 - "$SCRIPT_DIR" "$PHASE_ROOT" "$PHASE" "$REPO" <<'PY'
import hashlib
import sys
from pathlib import Path

script_dir = Path(sys.argv[1])
phase_root = Path(sys.argv[2])
phase = sys.argv[3]
repo = Path(sys.argv[4])
sys.path.insert(0, str(script_dir / "scripts"))

from phase_status import load_status, save_status, status_path  # noqa: E402

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

status_file = status_path(phase_root, phase)
phase_dir = status_file.parent
status = load_status(status_file)
status.update(
    {
        "status": "ready_for_review",
        "implementation_summary": "Sanity fixture changes target.txt and records deterministic proof.",
        "acceptance_contract": ["target.txt is changed and deterministic evidence exists"],
        "changed_files": [
            {"path": "target.txt", "sha256": sha256_file(repo / "target.txt")},
        ],
        "validation_commands": [
            {
                "command": "test \"$(cat target.txt)\" = after",
                "exit_code": 0,
                "log": "validation-logs/local.log",
                "log_sha256": sha256_file(phase_dir / "validation-logs/local.log"),
            }
        ],
        "evidence_artifacts": [
            {"path": "evidence-artifacts/proof.txt", "sha256": sha256_file(phase_dir / "evidence-artifacts/proof.txt")},
            {"path": "validation-logs/local.log", "sha256": sha256_file(phase_dir / "validation-logs/local.log")},
        ],
        "claims": [
            {
                "claim": "The sanity fixture has deterministic evidence for the phase contract.",
                "evidence_artifacts": ["evidence-artifacts/proof.txt", "validation-logs/local.log"],
                "acceptance_contract": ["target.txt is changed and deterministic evidence exists"],
            }
        ],
        "reviewer_policy": {
            "required": True,
            "comparison_required": True,
            "closure_rule": "deterministic_validation_and_external_review",
        },
    }
)
save_status(status_file, status)
PY

expect_fail_contains \
  "ready_for_review requires skill_context_artifacts when reviewer_policy.required=true" \
  "$RUN_SH" --root "$PHASE_ROOT" validate --phase "$PHASE" --repo-root "$REPO"

cat > "$TMP_ROOT/headless-skill-context.md" <<EOF
# Headless Skill Context

- Orchestrator: \$plan-iterate at $SCRIPT_DIR/SKILL.md.
- Reviewer bundle: \$review-code must package the phase evidence before model review.
- Reviewer: \$scillm model gpt-5.5 with top-level reasoning_effort high and no max_tokens.
- Memory: repeated review progress context uses ArangoDB collection plan_iterate_phase_context.
- Human escalation: use \$interview if blockers repeat or ambiguity remains.
- Role boundary: reviewer critiques; project agent implements and validates.
EOF

"$RUN_SH" --root "$PHASE_ROOT" record-skill-context --phase "$PHASE" --context "$TMP_ROOT/headless-skill-context.md" --repo-root "$REPO" >/dev/null

cat > "$TMP_ROOT/progress-context.md" <<'EOF'
# Phase Progress Context

- Attempt: medium-complexity sanity path.
- Prior findings: none; this is the first review package.
- Current delta: skill context is present, deterministic evidence exists, and comparison review is required.
- Blockers: none.
- Decision: require two distinct passing reviewer receipts before comparison closure.
EOF

"$RUN_SH" --root "$PHASE_ROOT" record-context \
  --phase "$PHASE" \
  --context "$TMP_ROOT/progress-context.md" \
  --memory-key "$PHASE-sanity-progress-001" \
  --skip-memory-upsert \
  --repo-root "$REPO" >/dev/null

"$RUN_SH" --root "$PHASE_ROOT" validate --phase "$PHASE" --repo-root "$REPO" >/dev/null

BUNDLE="$TMP_ROOT/phase-review.zip"
"$RUN_SH" --root "$PHASE_ROOT" package --phase "$PHASE" --output "$BUNDLE" --repo-root "$REPO" >/dev/null
test -s "$BUNDLE" || fail "review bundle was not created"

python3 - "$BUNDLE" <<'PY'
import sys
import zipfile

bundle = zipfile.ZipFile(sys.argv[1])
names = set(bundle.namelist())
required = {
    "PHASE_STATUS.json",
    "PHASE_REVIEW_REQUEST.md",
    "changed-files.diff",
    "manifest.json",
}
missing = sorted(required - names)
if missing:
    raise SystemExit(f"bundle missing required entries: {missing}")
if not any(name.startswith("skill-context/") for name in names):
    raise SystemExit("bundle missing skill-context artifact")
if "target.txt" not in bundle.read("changed-files.diff").decode("utf-8", errors="replace"):
    raise SystemExit("changed-files.diff does not reference target.txt")
PY

printf 'PASS: sanity review\n' > "$TMP_ROOT/review.md"
cat > "$TMP_ROOT/request.json" <<'EOF'
{"model":"gpt-5.5","reasoning_effort":"high","messages":[{"role":"user","content":"review sanity bundle"}]}
EOF

python3 - "$SCRIPT_DIR" "$PHASE_ROOT" "$PHASE" "$REPO" "$TMP_ROOT/review.md" "$TMP_ROOT/request.json" "$BUNDLE" "$TMP_ROOT/receipt.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

script_dir = Path(sys.argv[1])
phase_root = Path(sys.argv[2])
phase = sys.argv[3]
repo = Path(sys.argv[4])
review = Path(sys.argv[5])
request = Path(sys.argv[6])
bundle = Path(sys.argv[7])
receipt = Path(sys.argv[8])
sys.path.insert(0, str(script_dir / "scripts"))

from phase_status import (  # noqa: E402
    compute_phase_subject_sha256,
    compute_progress_context_sha256,
    compute_skill_context_sha256,
    load_status,
    status_path,
)

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

status_file = status_path(phase_root, phase)
status = load_status(status_file)
phase_dir = status_file.parent
data = {
    "status": "completed",
    "reviewer_id": "scillm-gpt55-high",
    "adjudicator_kind": "scillm",
    "request_sha256": sha256_file(request),
    "response_sha256": sha256_file(review),
    "review_bundle_sha256": sha256_file(bundle),
    "phase_subject_sha256": compute_phase_subject_sha256(status),
    "progress_context_sha256": compute_progress_context_sha256(status, phase_dir),
    "skill_context_sha256": compute_skill_context_sha256(status, phase_dir),
    "run_id": "sanity-local-receipt",
}
receipt.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

"$RUN_SH" --root "$PHASE_ROOT" record-review \
  --phase "$PHASE" \
  --reviewer scillm-gpt55-high \
  --adjudicator-kind scillm \
  --verdict passed \
  --review "$TMP_ROOT/review.md" \
  --review-request "$TMP_ROOT/request.json" \
  --review-bundle "$BUNDLE" \
  --invocation-command "sanity local scillm receipt" \
  --invocation-receipt "$TMP_ROOT/receipt.json" \
  --model gpt-5.5 \
  --repo-root "$REPO" >/dev/null

printf 'PASS: comparison sanity review\n' > "$TMP_ROOT/comparison-review.md"
cat > "$TMP_ROOT/comparison-request.json" <<'EOF'
{"model":"gpt-5.5","reasoning_effort":"high","messages":[{"role":"user","content":"comparison review sanity bundle"}]}
EOF

python3 - "$SCRIPT_DIR" "$PHASE_ROOT" "$PHASE" "$REPO" "$TMP_ROOT/comparison-review.md" "$TMP_ROOT/comparison-request.json" "$BUNDLE" "$TMP_ROOT/comparison-receipt.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

script_dir = Path(sys.argv[1])
phase_root = Path(sys.argv[2])
phase = sys.argv[3]
repo = Path(sys.argv[4])
review = Path(sys.argv[5])
request = Path(sys.argv[6])
bundle = Path(sys.argv[7])
receipt = Path(sys.argv[8])
sys.path.insert(0, str(script_dir / "scripts"))

from phase_status import (  # noqa: E402
    compute_phase_subject_sha256,
    compute_progress_context_sha256,
    compute_skill_context_sha256,
    load_status,
    status_path,
)

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

status_file = status_path(phase_root, phase)
status = load_status(status_file)
phase_dir = status_file.parent
data = {
    "status": "completed",
    "reviewer_id": "scillm-claude-sonnet-high",
    "adjudicator_kind": "scillm",
    "request_sha256": sha256_file(request),
    "response_sha256": sha256_file(review),
    "review_bundle_sha256": sha256_file(bundle),
    "phase_subject_sha256": compute_phase_subject_sha256(status),
    "progress_context_sha256": compute_progress_context_sha256(status, phase_dir),
    "skill_context_sha256": compute_skill_context_sha256(status, phase_dir),
    "run_id": "sanity-comparison-local-receipt",
}
receipt.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

"$RUN_SH" --root "$PHASE_ROOT" record-review \
  --phase "$PHASE" \
  --reviewer scillm-claude-sonnet-high \
  --adjudicator-kind scillm \
  --verdict passed \
  --review "$TMP_ROOT/comparison-review.md" \
  --review-request "$TMP_ROOT/comparison-request.json" \
  --review-bundle "$BUNDLE" \
  --invocation-command "sanity local comparison scillm receipt" \
  --invocation-receipt "$TMP_ROOT/comparison-receipt.json" \
  --model gpt-5.5 \
  --repo-root "$REPO" >/dev/null

"$RUN_SH" --root "$PHASE_ROOT" record-comparison \
  --phase "$PHASE" \
  --agreement agree \
  --closure-allowed \
  --reason "sanity comparison reviewers passed the same bundle" \
  --repo-root "$REPO" >/dev/null

python3 - "$SCRIPT_DIR" "$PHASE_ROOT" "$PHASE" "$REPO" <<'PY'
import sys
from pathlib import Path

script_dir = Path(sys.argv[1])
phase_root = Path(sys.argv[2])
phase = sys.argv[3]
repo = Path(sys.argv[4])
sys.path.insert(0, str(script_dir / "scripts"))

from phase_status import load_status, status_path, validate_status  # noqa: E402

status_file = status_path(phase_root, phase)
status = load_status(status_file)
errors = validate_status(status, status_file.parent, repo)
if errors:
    raise SystemExit("\n".join(errors))
if status["status"] != "external_review_passed":
    raise SystemExit(f"expected external_review_passed, got {status['status']}")
if len(status["review_results"]) != 2:
    raise SystemExit(f"expected two review results, got {len(status['review_results'])}")
if status["review_comparison"]["closure_allowed"] is not True:
    raise SystemExit("expected comparison closure_allowed=true")
for result in status["review_results"]:
    for key in ["phase_subject_sha256", "progress_context_sha256", "skill_context_sha256", "review_bundle_sha256"]:
        if not result.get(key):
            raise SystemExit(f"review result missing {key}")
PY

python3 - "$SCRIPT_DIR" "$PHASE_ROOT" "$PHASE" <<'PY'
import sys
from pathlib import Path

script_dir = Path(sys.argv[1])
phase_root = Path(sys.argv[2])
phase = sys.argv[3]
sys.path.insert(0, str(script_dir / "scripts"))

from phase_status import load_status, save_status, status_path  # noqa: E402

status_file = status_path(phase_root, phase)
status = load_status(status_file)
status["status"] = "accepted"
save_status(status_file, status)
PY

cat > "$REPO/PROJECT_KNOWLEDGE.md" <<'EOF'
# Project Knowledge

- Current blocker: the broader project still has an unmet acceptance gate.
- Do not claim full project completion.
- Next agent-executable candidate is a deterministic regression fixture for the next source-backed phase.
EOF

CONTINUE_JSON="$("$RUN_SH" --root "$PHASE_ROOT" continue --phase "$PHASE" --repo-root "$REPO")"
python3 - "$CONTINUE_JSON" <<'PY'
import json
import sys

decision = json.loads(sys.argv[1])
if decision.get("decision") != "PROJECT_GOALS_REMAIN":
    raise SystemExit(f"expected PROJECT_GOALS_REMAIN, got {decision.get('decision')}")
if decision.get("should_continue") is not True:
    raise SystemExit("expected should_continue=true")
if decision.get("stop") is not False:
    raise SystemExit("expected stop=false")
next_action = decision.get("next_action", {})
if next_action.get("type") != "create_next_phase_from_project_knowledge":
    raise SystemExit(f"expected create_next_phase_from_project_knowledge, got {next_action.get('type')}")
continuation = decision.get("project_knowledge_continuation", {})
if continuation.get("agent_executable") is not True:
    raise SystemExit("expected agent_executable project knowledge continuation")
PY

echo "SANITY PASS: plan-iterate medium-complexity review gates and project-knowledge continuation guard"
