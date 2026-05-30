#!/usr/bin/env bash
# Reload Surf extension via chrome.runtime.reload(), then wait for socket + ping.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/surf-cli-path.sh
source "${SKILL_DIR}/scripts/lib/surf-cli-path.sh"
LOCAL_CLI="${SURF_CLI_CLI}"
JSON=false
WAIT_SECS=30
for arg in "$@"; do
  case "$arg" in
    --json) JSON=true ;;
    --wait=*) WAIT_SECS="${arg#*=}" ;;
  esac
done

if [[ ! -f "$LOCAL_CLI" ]]; then
  echo "Error: surf-cli not found at $LOCAL_CLI" >&2
  exit 1
fi
if [[ ! -S /tmp/surf.sock ]]; then
  echo "Error: /tmp/surf.sock missing — is Chrome running with Surf loaded?" >&2
  exit 1
fi

if ! reload_out=$(node "$LOCAL_CLI" extension.reload ${JSON:+--json} 2>&1); then
  if echo "$reload_out" | grep -q "Unknown message type: EXTENSION_RELOAD"; then
    echo "Error: running extension is older than surf-cli dist (missing EXTENSION_RELOAD)." >&2
    echo "One-time bootstrap: chrome://extensions → Reload Surf (unpacked: ${SURF_CLI_PATH}/dist)" >&2
    exit 2
  fi
  echo "$reload_out" >&2
  exit 1
fi
echo "$reload_out" >&2

echo "Waiting for extension to reconnect (up to ${WAIT_SECS}s)..." >&2
deadline=$((SECONDS + WAIT_SECS))
while (( SECONDS < deadline )); do
  if [[ -S /tmp/surf.sock ]]; then
    if ping_out=$(node "$LOCAL_CLI" extension.ping --json 2>/dev/null); then
      if echo "$ping_out" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("success") else 1)' 2>/dev/null; then
        if $JSON; then
          echo "$ping_out" | python3 -c 'import json,sys; print(json.dumps({"status":"reloaded","ping":json.load(sys.stdin)}, indent=2))'
        else
          echo "OK: extension reloaded and ping succeeded"
        fi
        exit 0
      fi
    fi
  fi
  sleep 0.5
done

echo "Error: extension did not respond to ping within ${WAIT_SECS}s" >&2
echo "Human step: chrome://extensions → Reload Surf" >&2
exit 1
