#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BRIDGE_DIR="$SKILL_DIR/vscode-bridge"

cd "$BRIDGE_DIR"
npm ci
npm run compile
npm run package

VSIX="$(ls -t "$BRIDGE_DIR"/debugger-vscode-bridge-*.vsix | head -n 1)"
code --install-extension "$VSIX" --force

echo "$VSIX"
echo "Installed Debugger VS Code Bridge. Reload the VS Code window if it was already open before installation."
