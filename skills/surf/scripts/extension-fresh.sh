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
import json, re, subprocess, sys
from pathlib import Path

surf_cli, src_sw, dist_sw, src_host, json_out = sys.argv[1:6]
json_out = json_out == "true"
reasons = []
status = "fresh"

dist = Path(dist_sw)
src = Path(src_sw)
host = Path(src_host)


def installed_host_path() -> Path | None:
    home = Path.home()
    candidates = [
        home / ".config/google-chrome/NativeMessagingHosts/surf.browser.host.json",
        home / ".config/google-chrome-beta/NativeMessagingHosts/surf.browser.host.json",
        home / ".config/chromium/NativeMessagingHosts/surf.browser.host.json",
    ]
    for manifest in candidates:
        if not manifest.exists():
            continue
        try:
            wrapper = Path(json.loads(manifest.read_text()).get("path", "")).expanduser()
            text = wrapper.read_text(encoding="utf-8", errors="replace")
            matches = re.findall(r'[^\s"\']+/native/host\.cjs', text)
            if matches:
                return Path(matches[-1]).resolve()
        except Exception:
            continue
    return None


def host_processes(path: Path | None) -> list[dict]:
    if path is None:
        return []
    try:
        proc = subprocess.run(
            ["pgrep", "-af", str(path)], text=True, capture_output=True, check=False
        )
    except OSError:
        return []
    rows = []
    for line in proc.stdout.splitlines() if proc.returncode == 0 else []:
        pid, _, cmd = line.strip().partition(" ")
        if (
            not pid.isdigit()
            or str(path) not in cmd
            or not re.search(r"(^|[ /])node(?:js)?(?:[ /]|$)", cmd)
        ):
            continue
        rows.append({"pid": int(pid), "cmd": cmd, "host_path": str(path)})
    return rows

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

current_host = host.resolve() if host.exists() else host
installed_host = installed_host_path()
installed_host_path_mismatch = bool(
    installed_host is not None and installed_host != current_host
)
current_processes = host_processes(current_host)
installed_processes = (
    host_processes(installed_host) if installed_host_path_mismatch else current_processes
)
if installed_host_path_mismatch and installed_processes:
    status = "stale"
    reasons.append("native host path mismatch: installed host is running from a different checkout")

payload = {
    "status": status,
    "surf_cli": surf_cli,
    "reasons": reasons,
    "src_sw_mtime": src.stat().st_mtime if src.exists() else None,
    "dist_sw_mtime": dist.stat().st_mtime if dist.exists() else None,
    "src_host_mtime": host.stat().st_mtime if host.exists() else None,
    "current_host_path": str(current_host),
    "installed_host_path": str(installed_host) if installed_host else None,
    "installed_host_path_mismatch": installed_host_path_mismatch,
    "host_processes": current_processes,
    "installed_host_processes": installed_processes,
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
