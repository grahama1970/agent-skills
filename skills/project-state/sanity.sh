#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SANITY_TMP="$(mktemp -d)"
export UV_PROJECT_ENVIRONMENT="$SANITY_TMP/project-state-venv"
trap 'rm -rf "$SANITY_TMP"' EXIT

echo "=== project-state sanity check ==="

# Check Python files are valid syntax.
for py_file in "$SCRIPT_DIR"/*.py; do
    python3 -m py_compile "$py_file"
done
echo "PASS: Python files compile"

# Check run.sh is executable
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "PASS: run.sh is executable"
else
    echo "FAIL: run.sh not executable"
    exit 1
fi

# Check SKILL.md exists
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "PASS: SKILL.md exists"
else
    echo "FAIL: SKILL.md missing"
    exit 1
fi

# Check best-practices-skills frontmatter/rule validator.
python3 "$REPO_ROOT/skills/best-practices-skills/scripts/validate_skill.py" "$SCRIPT_DIR" --skills-root "$REPO_ROOT/skills"
echo "PASS: best-practices-skills validator passed"

# Assert required frontmatter contract fields.
uv run --project "$SCRIPT_DIR" python - "$SCRIPT_DIR/SKILL.md" <<'PY'
import sys
from pathlib import Path

import yaml

text = Path(sys.argv[1]).read_text()
frontmatter = text.split("---", 2)[1]
data = yaml.safe_load(frontmatter)
for field in ("triggers", "provides", "composes", "complies", "runtime_self_improvement"):
    assert field in data, f"missing {field}"
assert "best-practices-skills" in data["complies"]
assert data["runtime_self_improvement"] == "basic"
PY
echo "PASS: SKILL.md declares compliance metadata"

# Positive control: quick JSON report has required fields.
OUTPUT=$("$SCRIPT_DIR/run.sh" report --quick --json)
printf '%s' "$OUTPUT" | uv run --project "$SCRIPT_DIR" python -c "import json,sys; d=json.load(sys.stdin); assert 'project' in d and 'phase_1_infrastructure' in d"
echo "PASS: quick JSON report generated with required fields"

# Config doctor is non-interactive and machine-readable.
CONFIG_OUTPUT=$("$SCRIPT_DIR/run.sh" config doctor --json)
printf '%s' "$CONFIG_OUTPUT" | uv run --project "$SCRIPT_DIR" python -c "import json,sys; d=json.load(sys.stdin); assert d['schema'] == 'project_state.config_doctor.v1'; assert 'needs_attention' in d"
echo "PASS: config doctor JSON contract"

# Cleanup-tail positive control plus artifact/schema assertions.
TMP_DIR="$SANITY_TMP/fixtures"
mkdir -p "$TMP_DIR"
FIXTURE="$TMP_DIR/cleanup-receipt.json"
printf '{"moved_files":["obsolete.md"],"kept_files":["required.py"],"review_required":["maybe.md"]}\n' > "$FIXTURE"
TAIL_JSON="$TMP_DIR/cleanup-tail-output.json"
"$SCRIPT_DIR/run.sh" report --cleanup-tail --cleanup-receipt "$FIXTURE" --quick --json --output "$TAIL_JSON"
uv run --project "$SCRIPT_DIR" python - "$TAIL_JSON" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
out_dir = Path(report["artifacts"]["report_json"]).parent
assert report["schema"] == "skill.readiness_report.v1"
assert report["profile"] == "cleanup-tail-smoke"
assert report["release_readiness"] == "NOT_ESTABLISHED"
assert report["cleanup_counts"]["moved"] == 1
assert report["cleanup_counts"]["review_required"] == 1
assert report["project_sanity"]["assertion_status"] == "not_established"
assert report["repo_dirty_state"]["available"] is True
assert (out_dir / "report.json").exists()
assert (out_dir / "report.md").exists()
assert (out_dir / "index.html").exists()
assert not (out_dir / ".cleanup").exists()
PY
echo "PASS: cleanup-tail positive fixture and artifacts"

# Negative control: invalid cleanup receipt fails closed.
BAD_FIXTURE="$TMP_DIR/bad-cleanup-receipt.json"
printf '{not-json\n' > "$BAD_FIXTURE"
set +e
"$SCRIPT_DIR/run.sh" report --cleanup-tail --cleanup-receipt "$BAD_FIXTURE" --quick --json >/dev/null 2>&1
BAD_STATUS=$?
set -e
if [[ "$BAD_STATUS" -eq 0 ]]; then
    echo "FAIL: invalid cleanup receipt should fail"
    exit 1
fi
echo "PASS: cleanup-tail invalid receipt fails closed"

echo ""
echo "All sanity checks passed."
