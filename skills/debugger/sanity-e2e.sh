#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

WORK_DIR="$(mktemp -d /tmp/debugger-vscode-e2e.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

PROJECT_ROOT="${DEBUGGER_E2E_PROJECT_ROOT:-$WORK_DIR/project}"
PYTHON_BIN="${DEBUGGER_E2E_PYTHON:-$(command -v python3)}"
PROOF_OUT="${DEBUGGER_E2E_OUT:-/tmp/debugger-vscode-e2e-proof.json}"
CONFIG_NAME='Debug portable unittest with $debugger'

mkdir -p "$PROJECT_ROOT"
cat > "$PROJECT_ROOT/sample_app.py" <<'PY'
def classify(value):
    label = "large" if value > 10 else "small"
    return {"value": value, "label": label}
PY
cat > "$PROJECT_ROOT/test_sample_app.py" <<'PY'
import unittest

from sample_app import classify


class ClassifyTests(unittest.TestCase):
    def test_large(self):
        self.assertEqual(classify(14)["label"], "large")


if __name__ == "__main__":
    unittest.main()
PY

APP_FILE="$PROJECT_ROOT/sample_app.py"
BREAKPOINT="$APP_FILE:3"

uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/write_vscode_launch.py" \
  --workspace "$PROJECT_ROOT" \
  --name "$CONFIG_NAME" \
  --python "$PYTHON_BIN" \
  --module unittest \
  --arg "-q" \
  --all-code

uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/vscode_dap_breakpoint_proof.py" \
  --break "$BREAKPOINT" \
  --out "$PROOF_OUT" \
  --cwd "$PROJECT_ROOT" \
  --python "$PYTHON_BIN" \
  --module unittest \
  --arg "-q" \
  --local value \
  --local label

if uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/vscode_dap_breakpoint_proof.py" \
  --break "$APP_FILE:2" \
  --out "$WORK_DIR/missing-local-proof.json" \
  --cwd "$PROJECT_ROOT" \
  --python "$PYTHON_BIN" \
  --module unittest \
  --arg "-q" \
  --local label; then
  echo "missing-local proof unexpectedly succeeded" >&2
  exit 1
fi

uv run --project "$SCRIPT_DIR" python - "$PROOF_OUT" "$PROJECT_ROOT/.vscode/launch.json" "$CONFIG_NAME" "$APP_FILE" <<'PY'
import json
import sys
from pathlib import Path

proof = json.loads(Path(sys.argv[1]).read_text())
launch = json.loads(Path(sys.argv[2]).read_text())
config_name = sys.argv[3]
app_file = Path(sys.argv[4]).resolve()
goals = proof["goals"]
configs = {entry["name"]: entry for entry in launch["configurations"]}
assert config_name in configs, launch
assert configs[config_name]["type"] == "debugpy", configs[config_name]
assert configs[config_name]["module"] == "unittest", configs[config_name]
assert goals["set_breakpoint"] is True, goals
assert goals["stop_at_breakpoint"] is True, goals
assert goals["inspect_and_analyze_variables"] is True, goals
assert goals["provide_human_breakpoint"] is True, goals
assert Path(proof["human_breakpoint"]["file"]).resolve() == app_file, proof["human_breakpoint"]
assert proof["human_breakpoint"]["line"] == 3, proof["human_breakpoint"]
assert proof["set_breakpoints_response"][0]["verified"] is True, proof["set_breakpoints_response"]
assert proof["stopped_event"]["body"]["reason"] == "breakpoint", proof["stopped_event"]
assert Path(proof["top_frame"]["source"]["path"]).resolve() == app_file, proof["top_frame"]
assert proof["top_frame"]["line"] == 3, proof["top_frame"]
assert proof["matched_requested_breakpoint"] is True, proof
assert proof["locals"]["value"] == "14", proof["locals"]
assert proof["locals"]["label"] == "'large'", proof["locals"]
assert proof["proofAssessment"]["variableInspectionValid"] is True, proof["proofAssessment"]
assert proof["proofAssessment"]["missingLocals"] == [], proof["proofAssessment"]
assert "set a verified VS Code breakpoint" in proof["analysis"], proof["analysis"]
PY

uv run --project "$SCRIPT_DIR" python - "$WORK_DIR/missing-local-proof.json" <<'PY'
import json
import sys
from pathlib import Path

proof = json.loads(Path(sys.argv[1]).read_text())
assert proof["goals"]["inspect_and_analyze_variables"] is False, proof["goals"]
assert proof["proofAssessment"]["variableInspectionValid"] is False, proof["proofAssessment"]
assert proof["proofAssessment"]["missingLocals"] == ["label"], proof["proofAssessment"]
PY

echo "debugger VS Code E2E sanity passed: $PROOF_OUT"
