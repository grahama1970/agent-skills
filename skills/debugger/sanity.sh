#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-sanity.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PYTHON=(uv run --project "$SCRIPT_DIR" python)

TARGET="$WORK_DIR/target.py"
POSITIVE_OUT="$WORK_DIR/positive.json"
NEGATIVE_OUT="$WORK_DIR/negative.json"

cat > "$TARGET" <<'PY'
def never_called():
    unreachable = "no-hit"
    return unreachable


def classify(value):
    label = "large" if value > 10 else "small"
    return {"value": value, "label": label}


result = classify(14)
assert result["label"] == "large"
PY

before_hash="$(sha256sum "$TARGET" | awk '{print $1}')"

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/capture_breakpoints.py" \
  --break "$TARGET:7" \
  --local value \
  --watch value \
  --allow-watch-eval \
  --out "$POSITIVE_OUT" \
  -- "$TARGET"

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/validate_debugger_proof.py" "$POSITIVE_OUT" --expect-valid \
  --canonical-out "$WORK_DIR/positive-canonical.json"

if "${PYTHON[@]}" "$SCRIPT_DIR/scripts/capture_breakpoints.py" \
  --break "$TARGET:2" \
  --watch unreachable \
  --out "$NEGATIVE_OUT" \
  -- "$TARGET"; then
  echo "negative-control failed: unreachable breakpoint unexpectedly passed" >&2
  exit 1
fi

after_hash="$(sha256sum "$TARGET" | awk '{print $1}')"
if [[ "$before_hash" != "$after_hash" ]]; then
  echo "safety-boundary failed: debugger mutated target file" >&2
  exit 1
fi

"${PYTHON[@]}" - "$POSITIVE_OUT" "$NEGATIVE_OUT" <<'PY'
import json
import sys
from pathlib import Path

positive = json.loads(Path(sys.argv[1]).read_text())
negative = json.loads(Path(sys.argv[2]).read_text())

assert positive["status"]["ok"] is True, positive
assert positive["hit_count"] == 1, positive
hit = positive["hits"][0]
assert hit["source"] == 'label = "large" if value > 10 else "small"', hit
assert hit["locals"]["value"] == "14", hit
assert hit["watches"]["value"] == {"ok": "true", "value": "14"}, hit
assert positive["locals_allowlist"] == ["value"], positive
assert positive["allow_watch_eval"] is True, positive
assert json.loads(Path(sys.argv[1]).with_name("positive-canonical.json").read_text())["schema"] == "debugger.proof.v1"

assert negative["hit_count"] == 0, negative
assert negative["status"]["ok"] is True, negative
PY

(
  cd "$WORK_DIR"
  "${PYTHON[@]}" "$SCRIPT_DIR/scripts/capture_breakpoints.py" \
    --break "$TARGET:7" \
    --local value \
    --out "$WORK_DIR/python-m.json" \
    -- python -m target
)

mkdir -p "$WORK_DIR/.vscode"
cat > "$WORK_DIR/.vscode/launch.json" <<'JSONC'
{
  // JSONC comments and trailing commas are valid in VS Code launch.json.
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Existing Python",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "serverReadyAction": {"uriFormat": "http://localhost:%s"},
      "args": ["literal // not a comment", "literal /* not a comment */", "literal ,] not trailing", "literal ,} not trailing", "literal , } not trailing"],
    },
  ],
}
JSONC

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/write_vscode_launch.py" \
  --workspace "$WORK_DIR" \
  --name "Debug Python JSONC with \$debugger" \
  --module pytest \
  --arg -q

"${PYTHON[@]}" - "$WORK_DIR/.vscode/launch.json" <<'PY'
import json
import sys
from pathlib import Path

launch = json.loads(Path(sys.argv[1]).read_text())
configs = {entry["name"]: entry for entry in launch["configurations"]}
assert "Existing Python" in configs, launch
assert configs["Existing Python"]["serverReadyAction"]["uriFormat"] == "http://localhost:%s", launch
assert configs["Existing Python"]["args"] == [
    "literal // not a comment",
    "literal /* not a comment */",
    "literal ,] not trailing",
    "literal ,} not trailing",
    "literal , } not trailing",
], launch
assert configs["Debug Python JSONC with $debugger"]["type"] == "debugpy", launch
PY

cat > "$WORK_DIR/exit_string.py" <<'PY'
import sys

value = "seen"
sys.exit("boom")
PY

if "${PYTHON[@]}" "$SCRIPT_DIR/scripts/capture_breakpoints.py" \
  --break "$WORK_DIR/exit_string.py:4" \
  --local value \
  --out "$WORK_DIR/exit-string.json" \
  -- "$WORK_DIR/exit_string.py"; then
  echo "SystemExit string unexpectedly succeeded" >&2
  exit 1
fi

"${PYTHON[@]}" - "$WORK_DIR/exit-string.json" <<'PY'
import json
import sys
from pathlib import Path

proof = json.loads(Path(sys.argv[1]).read_text())
assert proof["hit_count"] == 1, proof
assert proof["status"]["ok"] is False, proof
assert proof["status"]["exit"] == 1, proof
assert proof["status"]["error"] == "'boom'", proof
PY

cat > "$WORK_DIR/silent_adapter.py" <<'PY'
import time
time.sleep(10)
PY

"${PYTHON[@]}" - "$SCRIPT_DIR/scripts/vscode_dap_breakpoint_proof.py" "$WORK_DIR/silent_adapter.py" <<'PY'
import importlib.util
import sys
from pathlib import Path

module_path = Path(sys.argv[1])
adapter_path = Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("dap_proof", module_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

client = module.DapClient(extension=Path("/unused"), adapter_command=[sys.executable, str(adapter_path)])
try:
    try:
        client.read(timeout=0.2)
    except TimeoutError:
        pass
    else:
        raise AssertionError("silent adapter did not time out")
finally:
    client.proc.kill()
    client.selector.close()
PY

echo "debugger sanity passed"
