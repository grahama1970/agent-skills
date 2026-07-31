#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/agentic-evals/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
OUT="$(mktemp)"
TIMEOUT_FIXTURE="$(mktemp)"
TIMEOUT_OUT="$(mktemp)"
ENV_FIXTURE="$(mktemp)"
ENV_OUT="$(mktemp)"
AUDIT_ROOT="$(mktemp -d)"
AUDIT_OUT=""
APPLY_OUT=""
trap 'rm -f "$OUT" "$TIMEOUT_FIXTURE" "$TIMEOUT_OUT" "$ENV_FIXTURE" "$ENV_OUT" "$AUDIT_OUT" "$APPLY_OUT"; rm -rf "$AUDIT_ROOT"' EXIT

"$SCRIPT_DIR/run.sh" run "$SCRIPT_DIR/fixtures/agentic_eval.json" --output "$OUT" >/dev/null

uv run --project "$SCRIPT_DIR" python - "$OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "agentic_evals.report.v1"
assert report["readiness"] == "READY"
assert report["mocked"] is False
assert report["fixture_backed"] is True
assert report["live"] is False
assert report["proof_scope"] == "fixture wiring smoke"
assert report["case_count"] == 2
assert report["trial_count"] == 6
assert all(case["pass_rate"] == 1.0 for case in report["cases"])
PY

cat > "$TIMEOUT_FIXTURE" <<'EOF'
{
  "version": 2,
  "skill": "agentic-evals-timeout",
  "trials": 1,
  "proof_scope": "timeout receipt serialization",
  "claims": {
    "proves": "timeout output is JSON-serializable",
    "does_not_prove": "skill semantic correctness"
  },
  "cases": [
    {
      "name": "timeout-captures-output",
      "type": "negative",
      "command": ["bash", "-c", "printf partial-output; sleep 1"],
      "expected": {"exit_code": 0}
    }
  ]
}
EOF
"$SCRIPT_DIR/run.sh" run "$TIMEOUT_FIXTURE" --timeout-seconds 0.1 --output "$TIMEOUT_OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$TIMEOUT_OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
trial = report["cases"][0]["trials"][0]
assert report["readiness"] == "NOT_READY"
assert trial["timed_out"] is True
assert isinstance(trial["stdout"], str)
assert "partial-output" in trial["stdout"]
PY

cat > "$ENV_FIXTURE" <<'EOF'
{
  "version": 2,
  "skill": "agentic-evals-env-scrub",
  "trials": 1,
  "proof_scope": "trial environment isolation",
  "claims": {
    "proves": "runner uv environment variables are not inherited by evaluated commands",
    "does_not_prove": "skill semantic correctness"
  },
  "cases": [
    {
      "name": "uv-env-scrubbed",
      "type": "positive",
      "command": ["bash", "-c", "test -z \"${UV_PROJECT_ENVIRONMENT:-}\" && test -z \"${VIRTUAL_ENV:-}\" && test -z \"${PYTHONPYCACHEPREFIX:-}\""],
      "expected": {"exit_code": 0}
    }
  ]
}
EOF
UV_PROJECT_ENVIRONMENT=/tmp/poison-agentic-evals-env \
VIRTUAL_ENV=/tmp/poison-virtual-env \
PYTHONPYCACHEPREFIX=/tmp/poison-pycache \
  "$SCRIPT_DIR/run.sh" run "$ENV_FIXTURE" --output "$ENV_OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$ENV_OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["readiness"] == "READY"
assert report["cases"][0]["passed_trials"] == 1
PY

mkdir -p \
  "$AUDIT_ROOT/covered/fixtures" \
  "$AUDIT_ROOT/missing" \
  "$AUDIT_ROOT/static-missing" \
  "$AUDIT_ROOT/best-practices-skills/scripts"
cat > "$AUDIT_ROOT/best-practices-skills/scripts/validate_skill.py" <<'EOF'
#!/usr/bin/env python3
import json

print(json.dumps([]))
EOF
chmod +x "$AUDIT_ROOT/best-practices-skills/scripts/validate_skill.py"
cat > "$AUDIT_ROOT/covered/SKILL.md" <<'EOF'
---
name: covered
description: >
  Temporary skill with an agentic eval fixture.
triggers:
  - covered eval fixture
provides:
  - task-orchestration
composes: []
complies:
  - best-practices-skills
---

# covered
EOF
cat > "$AUDIT_ROOT/covered/fixtures/agentic_eval.json" <<'EOF'
{"version": 2, "trials": 3, "cases": []}
EOF
cat > "$AUDIT_ROOT/missing/SKILL.md" <<'EOF'
---
name: missing
description: >
  Temporary executable skill without an eval posture.
triggers:
  - missing eval fixture
provides:
  - task-orchestration
composes: []
complies:
  - best-practices-skills
---

# missing
EOF
cat > "$AUDIT_ROOT/missing/run.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$AUDIT_ROOT/missing/run.sh"
cat > "$AUDIT_ROOT/static-missing/SKILL.md" <<'EOF'
---
name: static-missing
description: >
  Temporary non-executable orchestration skill without an eval posture.
triggers:
  - static missing eval fixture
provides:
  - task-orchestration
composes: []
complies:
  - best-practices-skills
---

# static-missing
EOF
AUDIT_OUT="$(mktemp)"
"$SCRIPT_DIR/run.sh" audit-skills "$AUDIT_ROOT" --output "$AUDIT_OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$AUDIT_OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "agentic_evals.skill_posture_audit.v1"
assert report["summary"]["skills_checked"] == 3
assert report["summary"]["eval001_count"] == 2
assert report["summary"]["recommended_action_counts"]["scaffold_fixture"] == 1
assert report["summary"]["recommended_action_counts"]["scaffold_static_validation_fixture"] == 1
assert report["summary"]["posture_counts"]["agentic_fixture"] == 1
assert report["summary"]["posture_counts"]["missing"] == 2
missing = next(item for item in report["skills"] if item["skill"] == "missing")
assert missing["recommended_action"] == "scaffold_fixture"
static_missing = next(item for item in report["skills"] if item["skill"] == "static-missing")
assert static_missing["recommended_action"] == "scaffold_static_validation_fixture"
PY

SCAFFOLD_OUT="$AUDIT_ROOT/missing/fixtures/agentic_eval.json"
"$SCRIPT_DIR/run.sh" scaffold-fixture "$AUDIT_ROOT/missing" --output "$SCAFFOLD_OUT" >/dev/null
"$SCRIPT_DIR/run.sh" run "$SCAFFOLD_OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$SCAFFOLD_OUT" <<'PY'
import json
import sys

fixture = json.load(open(sys.argv[1], encoding="utf-8"))
assert fixture["version"] == 2
assert fixture["trials"] == 3
assert fixture["cases"][0]["name"] == "run-help"
assert fixture["cases"][0]["expected"]["exit_code"] == 0
PY

APPLY_OUT="$(mktemp)"
"$SCRIPT_DIR/run.sh" apply-scaffolds "$AUDIT_ROOT" --write --output "$APPLY_OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$APPLY_OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "agentic_evals.scaffold_apply_report.v1"
assert report["mocked"] is False
assert report["live"] is False
assert report["summary"]["eligible"] == 1
assert report["summary"]["created"] == 1
assert report["results"][0]["case"] == "skill-contract-validation"
PY
"$SCRIPT_DIR/run.sh" run "$AUDIT_ROOT/static-missing/fixtures/agentic_eval.json" >/dev/null
