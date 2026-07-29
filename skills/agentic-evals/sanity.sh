#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/agentic-evals/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
OUT="$(mktemp)"

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

AUDIT_ROOT="$(mktemp -d)"
trap 'rm -f "$OUT" "$AUDIT_OUT"; rm -rf "$AUDIT_ROOT"' EXIT
mkdir -p "$AUDIT_ROOT/covered/fixtures" "$AUDIT_ROOT/missing"
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
AUDIT_OUT="$(mktemp)"
"$SCRIPT_DIR/run.sh" audit-skills "$AUDIT_ROOT" --output "$AUDIT_OUT" >/dev/null
uv run --project "$SCRIPT_DIR" python - "$AUDIT_OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "agentic_evals.skill_posture_audit.v1"
assert report["summary"]["skills_checked"] == 2
assert report["summary"]["eval001_count"] == 1
assert report["summary"]["posture_counts"]["agentic_fixture"] == 1
assert report["summary"]["posture_counts"]["missing"] == 1
PY
