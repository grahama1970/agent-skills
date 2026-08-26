#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

ALLOW_LIVE=0
OUT_DIR="${DEBUGGER_REMOTE_SSH_PROOF_DIR:-}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --allow-live)
      ALLOW_LIVE=1
      shift
      ;;
    --out)
      OUT_DIR="${2:?--out requires a directory}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="$(mktemp -d /tmp/debugger-bridge-remote-ssh.XXXXXX)"
fi
mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/remote-ssh-proof-summary.json"
BRIDGE_DIR="$SCRIPT_DIR/vscode-bridge"

python3 - "$BRIDGE_DIR/package.json" "$BRIDGE_DIR/src/extension.ts" "$BRIDGE_DIR/src/protocol.ts" \
  "$SCRIPT_DIR/scripts/request_vscode_bridge.py" "$SCRIPT_DIR/scripts/install_vscode_bridge.sh" <<'PY'
import json
import sys
from pathlib import Path

package = json.loads(Path(sys.argv[1]).read_text())
extension = Path(sys.argv[2]).read_text()
protocol = Path(sys.argv[3]).read_text()
requester = Path(sys.argv[4]).read_text()
installer = Path(sys.argv[5]).read_text()

assert package["extensionKind"] == ["workspace"], package
assert "buildBridgeAuthority(folder)" in extension, extension
assert "validateBridgeAuthority(request, authority)" in extension, extension
assert "debugger_bridge_authority_mismatch" in extension, extension
assert "breakpointEvidenceForFrame(frame, request)" in extension, extension
assert "sourceSymbolRangeForLine" in extension, extension
assert "sourceSha256" in extension, extension
assert "actual stopped frame is an adapter-relocated executable line inside the requested current symbol range" in extension, extension
assert "expectedRemoteName" in protocol, protocol
assert "expectedExtensionHostKind" in protocol, protocol
assert "BridgeBreakpointEvidence" in protocol, protocol
assert "--expect-remote-name" in requester, requester
assert "--expect-extension-host-kind" in requester, requester
assert "--require-remote-ssh" in installer, installer
assert "debugger.vscode_bridge_install.v1" in installer, installer
PY

REMOTE_NAME="${VSCODE_REMOTE_NAME:-}"
if [[ -z "$REMOTE_NAME" && -n "${SSH_CONNECTION:-}" && -n "${VSCODE_IPC_HOOK_CLI:-}" ]]; then
  REMOTE_NAME="ssh-remote"
fi

if [[ "$ALLOW_LIVE" != "1" ]]; then
  python3 - "$SUMMARY" "$OUT_DIR" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

summary = {
    "schema": "debugger.remote_ssh_bridge_proof.v1",
    "status": "deterministic_only",
    "mocked": False,
    "live": False,
    "proof_dir": sys.argv[2],
    "checks": ["static_remote_authority_contract"],
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
Path(sys.argv[1]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "$SUMMARY"
  exit 0
fi

if [[ "$REMOTE_NAME" != "ssh-remote" ]]; then
  python3 - "$SUMMARY" "$OUT_DIR" "${REMOTE_NAME:-}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

summary = {
    "schema": "debugger.remote_ssh_bridge_proof.v1",
    "status": "blocked",
    "blocker": "remote_ssh_extension_host_unavailable",
    "mocked": False,
    "live": False,
    "proof_dir": sys.argv[2],
    "observed": {
        "remote_name": sys.argv[3] or None,
        "ssh_connection_present": False,
        "vscode_ipc_hook_cli_present": False,
    },
    "required": {
        "remote_name": "ssh-remote",
        "extension_host_kind": "workspace",
        "local_client": "macOS VS Code or equivalent local VS Code client",
        "remote_workspace": "Ubuntu workspace opened through Remote SSH",
    },
    "next_command": "Open this repository through VS Code Remote SSH, then rerun: bash skills/debugger/sanity-bridge-remote-ssh.sh --allow-live --out <proof-dir>",
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
Path(sys.argv[1]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "$SUMMARY"
  exit 30
fi

# The remote-CLI --install-extension proxies through the window IPC and can
# stall for minutes; when the bridge is already present in the remote server''s
# extensions, DEBUGGER_REMOTE_SSH_SKIP_INSTALL=1 skips the reinstall (the
# presence check below still fails closed if it is missing).
if [[ "${DEBUGGER_REMOTE_SSH_SKIP_INSTALL:-0}" == "1" ]]; then
  if ! ls "$HOME/.vscode-server/extensions/"agent-skills.debugger-vscode-bridge-* >/dev/null 2>&1; then
    echo "debugger_bridge_remote_install_missing: skip-install set but no bridge in ~/.vscode-server/extensions" >&2
    exit 21
  fi
  printf '{"schema": "debugger.vscode_bridge_install.v1", "skipped": true, "reason": "already installed in remote server extensions"}
' > "$OUT_DIR/install.json"
else
  "$SCRIPT_DIR/scripts/install_vscode_bridge.sh" --require-remote-ssh --report-json "$OUT_DIR/install.json" >/dev/null
fi

PROJECT_ROOT="${DEBUGGER_REMOTE_SSH_PROJECT_ROOT:-$OUT_DIR/workspace}"
mkdir -p "$PROJECT_ROOT"
cp "$SCRIPT_DIR/fixtures/remote-ssh/relocated_breakpoint.py" "$PROJECT_ROOT/remote_ssh_fixture.py"
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/write_vscode_launch.py" \
  --workspace "$PROJECT_ROOT" \
  --name "Debug Remote SSH relocated breakpoint (\$debugger)" \
  --python "$(command -v python3)" \
  --module remote_ssh_fixture

mapfile -t REQUEST_PATHS < <(uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/request_vscode_bridge.py" \
  --workspace "$PROJECT_ROOT" \
  --action restart \
  --launch-config-name "Debug Remote SSH relocated breakpoint (\$debugger)" \
  --break "remote_ssh_fixture.py:3" \
  --local value \
  --expect-remote-name ssh-remote \
  --expect-extension-host-kind workspace \
  --stop-timeout-ms 45000)
REQUEST_JSON="${REQUEST_PATHS[0]}"
STATUS_JSON="${REQUEST_PATHS[1]}"

deadline=$((SECONDS + 60))
while [[ $SECONDS -lt $deadline ]]; do
  if [[ -f "$STATUS_JSON" ]] && python3 - "$STATUS_JSON" <<'PY'
import json
import sys
from pathlib import Path
status = json.loads(Path(sys.argv[1]).read_text())
raise SystemExit(0 if status.get("status") not in {"pending", "starting", "running"} else 1)
PY
  then
    break
  fi
  sleep 1
done

python3 - "$SUMMARY" "$OUT_DIR" "$REQUEST_JSON" "$STATUS_JSON" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

summary_path, proof_dir, request_path, status_path = sys.argv[1:5]
status = json.loads(Path(status_path).read_text())
evidence = status.get("stoppedState", {}).get("breakpointEvidence", [])
accepted_relocation = any(
    item.get("accepted") is True and item.get("relocated") is True and item.get("sourceSymbolRange", {}).get("sourceSha256")
    for item in evidence
)
summary = {
    "schema": "debugger.remote_ssh_bridge_proof.v1",
    "status": "passed" if status.get("proofValid") is True and accepted_relocation else "failed",
    "mocked": False,
    "live": True,
    "proof_dir": proof_dir,
    "request_json": request_path,
    "status_json": status_path,
    "proof_valid": status.get("proofValid"),
    "accepted_relocation": accepted_relocation,
    "authority": status.get("authority"),
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if summary["status"] == "passed" else 31)
PY

echo "$SUMMARY"
