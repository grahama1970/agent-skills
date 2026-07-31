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
    uv run --project "$SCRIPT_DIR" python -m py_compile "$py_file"
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
uv run --project "$SCRIPT_DIR" python "$REPO_ROOT/skills/best-practices-skills/scripts/validate_skill.py" "$SCRIPT_DIR" --skills-root "$REPO_ROOT/skills"
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

# Generic-project positive control: no Embry labels or Embry-only gaps.
GENERIC_ROOT="$SANITY_TMP/generic-project"
mkdir -p "$GENERIC_ROOT/tests"
cat > "$GENERIC_ROOT/pyproject.toml" <<'TOML'
[project]
name = "generic-fixture"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = ["pytest>=8.0"]
TOML
printf '# Generic Fixture\n' > "$GENERIC_ROOT/README.md"
cat > "$GENERIC_ROOT/tests/test_smoke.py" <<'PY'
def test_smoke():
    assert True
PY
GENERIC_JSON="$SANITY_TMP/generic-project-state.json"
PROJECT_STATE_ROOT="$GENERIC_ROOT" "$SCRIPT_DIR/run.sh" report --quick --json --output "$GENERIC_JSON"
uv run --project "$SCRIPT_DIR" python - "$GENERIC_JSON" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
infra = report["phase_1_infrastructure"]
gaps = report["phase_6_gaps"]["gaps"]
assert report["project"] == "generic-fixture"
assert report["project_profile"] == "generic"
assert infra["tests"]["total"] == 1
assert infra["daemons"]["applicable"] is False
assert infra["cascade"]["applicable"] is False
assert infra["daemon_cascade_wiring"]["applicable"] is False
assert not any(gap.get("category") == "cascade" for gap in gaps)
assert not any("Embry OS" in json.dumps(section) for section in (report, gaps))
PY
echo "PASS: generic project target is not hard-wired to Embry OS"

# Config doctor is non-interactive and machine-readable.
CONFIG_OUTPUT=$("$SCRIPT_DIR/run.sh" config doctor --json)
printf '%s' "$CONFIG_OUTPUT" | uv run --project "$SCRIPT_DIR" python -c "import json,sys; d=json.load(sys.stdin); assert d['schema'] == 'project_state.config_doctor.v1'; assert 'needs_attention' in d"
echo "PASS: config doctor JSON contract"

# Cleanup-tail positive control plus artifact/schema assertions.
TMP_DIR="$SANITY_TMP/fixtures"
mkdir -p "$TMP_DIR"
FIXTURE="$TMP_DIR/cleanup-receipt.json"
printf '{"moved_files":["obsolete.py"],"kept_files":["required.py"],"review_required":["maybe.md"],"project_knowledge_sync":"synced","memory_sync":"synced"}\n' > "$FIXTURE"
cat > "$PWD/.cleanup-evidence.json" <<'JSON'
{
  "contract": "cleanup.evidence.v1",
  "analysis_complete": true,
  "repository_path": ".",
  "proof_scope": {"languages_with_resolved_edges": ["python"], "known_blind_spots": []},
  "scan_failures": [],
  "files": {
    "obsolete.py": {
      "content_sha256": "fixture",
      "parse_status": "ok",
      "inbound_references": [],
      "entrypoint_references": [],
      "entry_kinds": [],
      "dynamic_reference_warnings": [],
      "outbound_edges": []
    },
    "maybe.md": {
      "content_sha256": "fixture",
      "parse_status": "ok",
      "inbound_references": [],
      "entrypoint_references": [],
      "entry_kinds": [],
      "dynamic_reference_warnings": [],
      "outbound_edges": []
    }
  }
}
JSON
cat > "$PWD/.ingest-code.json" <<'JSON'
{
  "ingested_at": "2026-07-27T00:00:00",
  "started_at": "2026-07-27T00:00:00",
  "path": ".",
  "stem": "project-state",
  "files_scanned": 2,
  "knowledge_stored": 0,
  "cwe_stored": 0,
  "edges_stored": 0,
  "code_index": {"enabled": false, "backend": "memory", "collection": "code_symbols", "treesitter": true, "symbols_stored": 0},
  "scope": "code",
  "run_status": "complete",
  "completed": true,
  "scan_roots": ["."],
  "completed_scan_roots": ["."]
}
JSON
trap 'rm -rf "$SANITY_TMP"; rm -f "$PWD/.cleanup-evidence.json" "$PWD/.ingest-code.json"' EXIT
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
assert report["ingest_code_cleanup_evidence"]["coverage_status"] == "covered"
assert report["ingest_code_marker"]["normalized_status"] == "fresh"
assert report["memory_sync"]["status"] == "synced"
assert report["project_knowledge_sync"]["status"] == "synced"
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
