#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BRIDGE_DIR="$SKILL_DIR/vscode-bridge"
REPORT_JSON=""
REQUIRE_REMOTE_SSH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --report-json)
      REPORT_JSON="${2:?--report-json requires a path}"
      shift 2
      ;;
    --require-remote-ssh)
      REQUIRE_REMOTE_SSH=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

REMOTE_NAME="${VSCODE_REMOTE_NAME:-}"
if [[ -z "$REMOTE_NAME" && -n "${SSH_CONNECTION:-}" && -n "${VSCODE_IPC_HOOK_CLI:-}" ]]; then
  REMOTE_NAME="ssh-remote"
fi
INSTALL_CONTEXT="local"
if [[ "$REMOTE_NAME" == "ssh-remote" ]]; then
  INSTALL_CONTEXT="remote-ssh-workspace-host"
fi
if [[ "$REQUIRE_REMOTE_SSH" == "1" && "$INSTALL_CONTEXT" != "remote-ssh-workspace-host" ]]; then
  echo "debugger_bridge_remote_ssh_required: this shell is not a Remote SSH integrated terminal." >&2
  exit 20
fi

cd "$BRIDGE_DIR"
npm ci
npm run compile
npm run package

VSIX="$(ls -t "$BRIDGE_DIR"/debugger-vscode-bridge-*.vsix | head -n 1)"
code --install-extension "$VSIX" --force
INSTALLED_VERSION="$(code --list-extensions --show-versions | awk -F@ '$1 == "agent-skills.debugger-vscode-bridge" {print $2; exit}')"

python3 - "$REPORT_JSON" "$VSIX" "$INSTALL_CONTEXT" "$REMOTE_NAME" "$INSTALLED_VERSION" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report_path, vsix, install_context, remote_name, installed_version = sys.argv[1:6]
report = {
    "schema": "debugger.vscode_bridge_install.v1",
    "installed": bool(installed_version),
    "installed_version": installed_version or None,
    "vsix": vsix,
    "install_context": install_context,
    "remote_name": remote_name or None,
    "extension_kind": ["workspace"],
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
if report_path:
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")
print(encoded, end="")
PY

echo "Installed Debugger VS Code Bridge. Reload the VS Code window if it was already open before installation."
