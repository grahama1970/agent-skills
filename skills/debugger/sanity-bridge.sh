#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

BRIDGE_DIR="$SCRIPT_DIR/vscode-bridge"
TEMP_PROJECT_ROOT=""
if [[ -n "${DEBUGGER_E2E_PROJECT_ROOT:-}" ]]; then
  PROJECT_ROOT="$DEBUGGER_E2E_PROJECT_ROOT"
else
  TEMP_PROJECT_ROOT="$(mktemp -d /tmp/debugger-bridge-project.XXXXXX)"
  PROJECT_ROOT="$TEMP_PROJECT_ROOT"
fi
CONFIG_NAME='Debug agent-operator /api/chat pytest ($debugger)'
trap '[[ -z "$TEMP_PROJECT_ROOT" ]] || rm -rf "$TEMP_PROJECT_ROOT"' EXIT

cd "$BRIDGE_DIR"
npm ci
npm run compile
npm run test:protocol
npm run package

uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/request_vscode_bridge.py" \
  --workspace "$PROJECT_ROOT" \
  --action restart \
  --launch-config-name "$CONFIG_NAME" \
  --break "backend/src/agent_operator/app.py:1659" \
  --local req \
  --local project_registry \
  --watch "req.project_id" \
  --watch "req.patch_allowed" \
  --allow-watch-eval

uv run --project "$SCRIPT_DIR" python - "$PROJECT_ROOT/.vscode/debugger-bridge/request.json" <<'PY'
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text())
assert request["id"].startswith("debugger-"), request
assert request["action"] == "restart", request
assert request["launchConfigName"] == "Debug agent-operator /api/chat pytest ($debugger)", request
assert request["breakpoints"][0]["file"].endswith("backend/src/agent_operator/app.py"), request
assert request["breakpoints"][0]["line"] == 1659, request
assert request["locals"] == ["req", "project_registry"], request
assert request["watches"] == ["req.project_id", "req.patch_allowed"], request
assert request["allowWatchEval"] is True, request
assert request["output"].startswith(".vscode/debugger-bridge/status.debugger-"), request
assert request["output"].endswith(".json"), request
assert request["replaceBreakpoints"] is True, request
assert request["saveBeforeStart"] is True, request
assert request["requestHash"], request
payload = {key: value for key, value in request.items() if key != "requestHash"}
expected_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
assert request["requestHash"] == expected_hash, request
assert request["maxRequestAgeMs"] == 120000, request
datetime.fromisoformat(request["createdAt"])
PY

uv run --project "$SCRIPT_DIR" python - "$PROJECT_ROOT/.vscode/debugger-bridge/request.json" "$PROJECT_ROOT" <<'PY'
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text())
status_path = Path(sys.argv[2]) / request["output"]
status = json.loads(status_path.read_text())
assert status["status"] == "pending", status
assert status["id"] == request["id"], status
assert status["requestHash"] == request["requestHash"], status
PY

uv run --project "$SCRIPT_DIR" python - "$BRIDGE_DIR/package.json" "$BRIDGE_DIR/src/extension.ts" "$BRIDGE_DIR/src/protocol.ts" <<'PY'
import json
import sys
from pathlib import Path

package = json.loads(Path(sys.argv[1]).read_text())
source = Path(sys.argv[2]).read_text()
protocol = Path(sys.argv[3]).read_text()
requester = Path(sys.argv[1]).parent.parent.joinpath("scripts", "request_vscode_bridge.py").read_text()
assert "onStartupFinished" in package["activationEvents"], package
assert "void processWorkspaceRequestFile({ missingOk: true })" not in source, source
assert "canonicalRequestHash(parsedRequest)" in source, source
assert "verifyPendingStatus(outputPath, request)" in source, source
assert "processedRequestIds.add(requestId)" in source, source
assert source.index("verifyPendingStatus(outputPath, request)") < source.index("processedRequestIds.add(requestId)"), source
assert requester.index("Path(temp_name).replace(status_path)") < requester.index("Path(temp_name).replace(request_path)"), requester
assert "const bridgeQueue = new AsyncKeyedQueue()" in source, source
assert "await bridgeQueue.run('vscode-debugger-session'" in source, source
assert "async function writeOwnedStatus" in source, source
assert "readCurrentRequestOwner(filePath)" in source, source
assert "usesSharedRequestOwner(filePath)" in source, source
assert "writeOwnedJsonFile(" in source, source
assert "export function usesSharedRequestOwner" in protocol, protocol
assert "export async function writeOwnedJsonFile" in protocol, protocol
assert "withStatusFileLock(filePath" in protocol, protocol
assert "const lockPath = `${filePath}.lock`" in protocol, protocol
assert "Timed out waiting for debugger bridge status lock" in protocol, protocol
assert "requestErrorStatusPath(uri.fsPath, parsedRequest)" in source, source
assert "resolveContainedWorkspacePath(workspacePath, request.output, 'output')" in source, source
assert "decideOwnedStatusWritePath(filePath, requestId, requestHash, owner)" in protocol, protocol
assert "status.${safeFileName(requestId)}.superseded.json" in protocol, protocol
assert "status.invalid-request.${stamp}.json" in protocol, protocol
assert "isRequestAlreadyClaimed(outputPath, requestId, requestHash)" in source, source
assert "claimRequestId(outputPath, requestId, requestHash)" in source, source
assert source.index("isRequestAlreadyClaimed(outputPath, requestId, requestHash)") < source.index("enforceFreshRequest(request)"), source
assert "if (pending === pendingCapture)" in source, source
assert "status: proofAssessment.proofValid ? 'stopped' : 'stopped-not-proof'" in source, source
assert "proofAssessment," in source, source
assert "Debugger bridge watch evaluation requires allowWatchEval: true" in protocol, protocol
assert "export class AsyncKeyedQueue" in protocol, protocol
assert "export function decideOwnedStatusWritePath" in protocol, protocol
assert "export function invalidRequestStatusPath" in protocol, protocol
assert "maxRequestAgeMs must be an integer between 100 and 300000" in protocol, protocol
assert "export function assertWorkspacePath" in protocol, protocol
assert "export async function claimRequestId" in protocol, protocol
assert "export async function isRequestAlreadyClaimed" in protocol, protocol
PY

echo "debugger VS Code bridge smoke passed"
