#!/usr/bin/env bash
# Compare surf-cli source vs dist mtimes; fail closed when dist looks stale.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/surf-cli-path.sh
source "${SKILL_DIR}/scripts/lib/surf-cli-path.sh"
SURF_CLI="${SURF_CLI_PATH}"
JSON=false
for arg in "$@"; do
  [[ "$arg" == "--json" ]] && JSON=true
done

src_sw="$SURF_CLI/src/service-worker/index.ts"
dist_sw="$SURF_CLI/dist/service-worker/index.js"
src_host="$SURF_CLI/native/host.cjs"

python3 - "$SURF_CLI" "$src_sw" "$dist_sw" "$src_host" "$JSON" << 'PY'
import json, sys
from pathlib import Path

surf_cli, src_sw, dist_sw, src_host, json_out = sys.argv[1:6]
json_out = json_out == "true"
reasons = []
status = "fresh"

dist = Path(dist_sw)
src = Path(src_sw)
host = Path(src_host)

if not dist.exists():
    status = "stale"
    reasons.append("missing dist/service-worker/index.js")
else:
    if src.exists() and src.stat().st_mtime > dist.stat().st_mtime:
        status = "stale"
        reasons.append("source service-worker newer than dist bundle")
    if host.exists() and host.stat().st_mtime > dist.stat().st_mtime:
        status = "stale"
        reasons.append("native host newer than dist bundle")

payload = {
    "status": status,
    "surf_cli": surf_cli,
    "reasons": reasons,
    "src_sw_mtime": src.stat().st_mtime if src.exists() else None,
    "dist_sw_mtime": dist.stat().st_mtime if dist.exists() else None,
    "src_host_mtime": host.stat().st_mtime if host.exists() else None,
}

if json_out:
    print(json.dumps(payload, indent=2))
else:
    if reasons:
        print(f"STALE: {'; '.join(reasons)}")
    else:
        print("FRESH: dist matches source mtimes")

sys.exit(0 if status == "fresh" else 1)
PY
