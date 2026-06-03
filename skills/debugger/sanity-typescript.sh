#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="$(mktemp -d /tmp/debugger-ts-sanity.XXXXXX)"
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
      "type": "node",
      "request": "launch",
      "program": "${workspaceFolder}/old.js",
      "serverReadyAction": {"uriFormat": "http://localhost:%s"},
      "args": ["literal // not a comment", "literal /* not a comment */", "literal ,] not trailing", "literal ,} not trailing", "literal , } not trailing"],
    },
  ],
}
JSONC

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/write_vscode_typescript_launch.py" \
  --workspace "$WORK_DIR" \
  --name "Debug TS node with \$debugger" \
  --kind node \
  --program "\${workspaceFolder}/src/index.ts" \
  --runtime-executable node \
  --runtime-arg --loader \
  --runtime-arg ts-node/esm \
  --arg --case \
  --arg sample \
  --env NODE_ENV=test \
  --out-file "\${workspaceFolder}/dist/**/*.js"

"${PYTHON[@]}" "$SCRIPT_DIR/scripts/write_vscode_typescript_launch.py" \
  --workspace "$WORK_DIR" \
  --name "Debug VS Code extension with \$debugger" \
  --kind extensionHost \
  --arg "--extensionDevelopmentPath=\${workspaceFolder}/vscode-bridge" \
  --out-file "\${workspaceFolder}/vscode-bridge/out/**/*.js"

"${PYTHON[@]}" - "$WORK_DIR/.vscode/launch.json" <<'PY'
import json
import sys
from pathlib import Path

launch = json.loads(Path(sys.argv[1]).read_text())
configs = {entry["name"]: entry for entry in launch["configurations"]}
assert "Existing" in configs, launch
assert configs["Existing"]["serverReadyAction"]["uriFormat"] == "http://localhost:%s", launch
assert configs["Existing"]["args"] == [
    "literal // not a comment",
    "literal /* not a comment */",
    "literal ,] not trailing",
    "literal ,} not trailing",
    "literal , } not trailing",
], launch

node = configs["Debug TS node with $debugger"]
assert node["type"] == "pwa-node", node
assert node["sourceMaps"] is True, node
assert node["program"] == "${workspaceFolder}/src/index.ts", node
assert node["runtimeArgs"] == ["--loader", "ts-node/esm"], node
assert node["args"] == ["--case", "sample"], node
assert node["env"] == {"NODE_ENV": "test"}, node

extension = configs["Debug VS Code extension with $debugger"]
assert extension["type"] == "extensionHost", extension
assert extension["request"] == "launch", extension
assert extension["args"] == ["--extensionDevelopmentPath=${workspaceFolder}/vscode-bridge"], extension
assert extension["outFiles"] == ["${workspaceFolder}/vscode-bridge/out/**/*.js"], extension
PY

echo "debugger TypeScript launch sanity passed"
