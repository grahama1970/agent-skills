#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-rust-sanity.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
PYTHON=(uv run --project "$SCRIPT_DIR" python)

mkdir -p "$WORK_DIR/.vscode"
cat > "$WORK_DIR/.vscode/launch.json" <<'JSONC'
{
  // Existing user config must survive JSONC parsing.
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Existing",
      "type": "lldb",
      "request": "launch",
      "program": "${workspaceFolder}/target/debug/old",
      "args": ["literal // not a comment", "literal /* not a comment */", "literal ,] not trailing"],
    },
  ],
}
JSONC

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/write_vscode_rust_launch.py" \
  --workspace "$WORK_DIR" \
  --name "Debug Rust test with \$debugger" \
  --kind cargo-test \
  --cargo-arg test \
  --cargo-arg --no-run \
  --cargo-arg exact_case \
  --cargo-arg -- \
  --cargo-arg --exact \
  --filter-name debugger_fixture \
  --filter-kind test \
  --arg --nocapture \
  --env RUST_BACKTRACE=1

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/write_vscode_rust_launch.py" \
  --workspace "$WORK_DIR" \
  --name "Debug Rust binary with \$debugger" \
  --kind cargo-run \
  --cargo-arg run \
  --cargo-arg --bin \
  --cargo-arg debugger_fixture \
  --arg --sample \
  --filter-name debugger_fixture

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/write_vscode_rust_launch.py" \
  --workspace "$WORK_DIR" \
  --name "Debug Rust compiled program with \$debugger" \
  --kind program \
  --program "\${workspaceFolder}/target/debug/debugger_fixture" \
  --arg --sample

"${PYTHON[@]}" - "$WORK_DIR/.vscode/launch.json" <<'PY'
import json
import sys
from pathlib import Path

launch = json.loads(Path(sys.argv[1]).read_text())
configs = {entry["name"]: entry for entry in launch["configurations"]}
assert "Existing" in configs, launch
assert configs["Existing"]["args"] == [
    "literal // not a comment",
    "literal /* not a comment */",
    "literal ,] not trailing",
], launch

test = configs["Debug Rust test with $debugger"]
assert test["type"] == "lldb", test
assert test["request"] == "launch", test
assert test["sourceLanguages"] == ["rust"], test
assert test["cargo"]["args"] == ["test", "--no-run", "exact_case", "--", "--exact"], test
assert test["cargo"]["filter"] == {"name": "debugger_fixture", "kind": "test"}, test
assert test["args"] == ["--nocapture"], test
assert test["env"] == {"RUST_BACKTRACE": "1"}, test

binary = configs["Debug Rust binary with $debugger"]
assert binary["cargo"]["args"] == ["run", "--bin", "debugger_fixture"], binary
assert binary["cargo"]["filter"] == {"name": "debugger_fixture", "kind": "bin"}, binary
assert binary["args"] == ["--sample"], binary

program = configs["Debug Rust compiled program with $debugger"]
assert program["program"] == "${workspaceFolder}/target/debug/debugger_fixture", program
assert program["args"] == ["--sample"], program
PY

echo "debugger Rust launch sanity passed"
