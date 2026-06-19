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
native_dir="$SURF_CLI/native"

python3 - "$SURF_CLI" "$src_sw" "$dist_sw" "$native_dir" "$JSON" << 'PY'
import json, os, re, subprocess, sys, time
from pathlib import Path

surf_cli, src_sw, dist_sw, native_dir, json_out = sys.argv[1:6]
json_out = json_out == "true"
reasons = []
status = "fresh"

dist = Path(dist_sw)
src = Path(src_sw)
native = Path(native_dir)
native_sources = sorted(
    p
    for p in native.glob("*.cjs")
    if p.is_file()
)

def newest_mtime(paths):
    mtimes = [p.stat().st_mtime for p in paths if p.exists()]
    return max(mtimes) if mtimes else None

def surf_host_processes():
    return host_processes_for(f"{surf_cli}/native/host.cjs")

def host_processes_for(pattern):
    try:
        proc = subprocess.run(
            ["pgrep", "-af", pattern],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=1)
        if not parts:
            continue
        if parts[0].isdigit():
            rows.append({"pid": int(parts[0]), "cmd": parts[1] if len(parts) > 1 else ""})
    return rows

def native_manifest_paths():
    home = Path.home()
    rels = [
        ".config/google-chrome/NativeMessagingHosts/surf.browser.host.json",
        ".config/chromium/NativeMessagingHosts/surf.browser.host.json",
        ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts/surf.browser.host.json",
        ".config/microsoft-edge/NativeMessagingHosts/surf.browser.host.json",
    ]
    return [home / rel for rel in rels if (home / rel).exists()]

def wrapper_host_path(wrapper_path):
    if not wrapper_path:
        return None
    try:
        text = Path(wrapper_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    matches = re.findall(r'["\']([^"\']*/native/host\.cjs)["\']', text)
    return matches[-1] if matches else None

def installed_native_hosts():
    installed = []
    for manifest_path in native_manifest_paths():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            installed.append({"manifest": str(manifest_path), "error": f"manifest_parse_failed: {exc}"})
            continue
        wrapper = manifest.get("path")
        host_path = wrapper_host_path(wrapper)
        installed.append({
            "manifest": str(manifest_path),
            "wrapper": wrapper,
            "host_path": host_path,
            "allowed_origins": manifest.get("allowed_origins") or [],
        })
    return installed

def process_start_epoch(pid):
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return time.mktime(time.strptime(text, "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        return None

if not dist.exists():
    status = "stale"
    reasons.append("missing dist/service-worker/index.js")
else:
    if src.exists() and src.stat().st_mtime > dist.stat().st_mtime:
        status = "stale"
        reasons.append("source service-worker newer than dist bundle")

native_newest_mtime = newest_mtime(native_sources)
host_processes = surf_host_processes()
for row in host_processes:
    row["start_epoch"] = process_start_epoch(row["pid"])
installed_hosts = installed_native_hosts()
installed_host_paths = sorted({h.get("host_path") for h in installed_hosts if h.get("host_path")})
installed_host_processes = []
for host_path in installed_host_paths:
    for row in host_processes_for(host_path):
        row["start_epoch"] = process_start_epoch(row["pid"])
        row["host_path"] = host_path
        installed_host_processes.append(row)

native_restart_required = False
if native_newest_mtime:
    if not host_processes:
        native_restart_required = True
        if installed_host_processes:
            reasons.append("native host path mismatch: installed host is running from a different checkout")
        else:
            reasons.append("native host process not running")
    elif any((row.get("start_epoch") or 0) < native_newest_mtime for row in host_processes):
        native_restart_required = True
        reasons.append("running native host older than native source")

if native_restart_required:
    status = "stale"

payload = {
    "status": status,
    "surf_cli": surf_cli,
    "reasons": reasons,
    "extension_dist_fresh": not any("service-worker" in r or "dist/" in r for r in reasons),
    "native_host_fresh": not native_restart_required,
    "src_sw_mtime": src.stat().st_mtime if src.exists() else None,
    "dist_sw_mtime": dist.stat().st_mtime if dist.exists() else None,
    "native_newest_mtime": native_newest_mtime,
    "native_sources": [str(p) for p in native_sources],
    "host_processes": host_processes,
    "installed_native_hosts": installed_hosts,
    "installed_host_processes": installed_host_processes,
    "installed_host_path_mismatch": bool(installed_host_processes and not host_processes),
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
