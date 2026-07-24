#!/usr/bin/env bash
# Report vendored surf-cli lock state and freshness vs source/dist.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/surf-cli-path.sh
source "${SKILL_DIR}/scripts/lib/surf-cli-path.sh"

LOCK_FILE="${SURF_CLI_PATH}/VENDOR.lock.json"
FORK_JSON="${SKILL_DIR}/vendor/fork.json"
JSON=false

for arg in "$@"; do
  [[ "$arg" == "--json" ]] && JSON=true
done

python3 - "$LOCK_FILE" "$FORK_JSON" "$SURF_CLI_PATH" "$JSON" << 'PY'
import hashlib, json, subprocess, sys
from pathlib import Path

lock_path, fork_json, vendor, json_out = sys.argv[1:5]
json_out = json_out == "true"
vendor = Path(vendor)

payload = {
    "vendor_path": str(vendor),
    "lock_present": Path(lock_path).exists(),
    "lock": None,
    "package_version": None,
    "upstream_ahead": None,
    "dist_fresh": None,
    "content_identity_matches": None,
}

pkg = vendor / "package.json"
if pkg.exists():
    payload["package_version"] = json.loads(pkg.read_text()).get("version")

if Path(lock_path).exists():
    payload["lock"] = json.loads(Path(lock_path).read_text())
    identity = payload["lock"].get("content_identity") or {}
    expected = identity.get("sha256")
    if expected:
        digest = hashlib.sha256()
        excludes = set(identity.get("excludes") or ["VENDOR.lock.json"])
        try:
            cfg = json.loads(Path(fork_json).read_text())
            excludes.update(cfg.get("rsync_excludes") or [])
        except Exception:
            pass

        def is_excluded(path):
            rel = path.relative_to(vendor).as_posix()
            for item in excludes:
                item = str(item).strip().rstrip("/")
                if not item:
                    continue
                if rel == item or rel.startswith(item + "/"):
                    return True
            return False

        files = sorted(
            path for path in vendor.rglob("*")
            if path.is_file()
            and not is_excluded(path)
        )
        for path in files:
            data = path.read_bytes()
            digest.update(path.relative_to(vendor).as_posix().encode())
            digest.update(b"\0")
            digest.update(str(len(data)).encode())
            digest.update(b"\0")
            digest.update(data)
        payload["content_identity"] = {
            "file_count": len(files),
            "sha256": digest.hexdigest(),
            "effective_excludes": sorted(excludes),
        }
        payload["content_identity_matches"] = digest.hexdigest() == expected

# dist freshness via extension-fresh logic
src_sw = vendor / "src/service-worker/index.ts"
dist_sw = vendor / "dist/service-worker/index.js"
if not dist_sw.exists():
    payload["dist_fresh"] = False
    payload["dist_reason"] = "missing dist bundle"
elif src_sw.exists() and src_sw.stat().st_mtime > dist_sw.stat().st_mtime:
    payload["dist_fresh"] = False
    payload["dist_reason"] = "source newer than dist"
else:
    payload["dist_fresh"] = True

# optional: compare lock commit to local dev fork
try:
    cfg = json.loads(Path(fork_json).read_text())
    local = cfg.get("local_dev_path")
    lock = payload.get("lock") or {}
    if local and Path(local).is_dir() and (Path(local) / ".git").is_dir():
        head = subprocess.check_output(["git", "-C", local, "rev-parse", "HEAD"], text=True).strip()
        payload["local_dev_head"] = head
        base_commit = lock.get("source_commit") or lock.get("upstream_base_commit")
        if base_commit:
            payload["upstream_ahead"] = head != base_commit
except Exception as exc:
    payload["local_dev_check_error"] = str(exc)

text = json.dumps(payload, indent=2)
if json_out:
    print(text)
else:
    print(f"vendor: {payload['vendor_path']}")
    if payload["lock"]:
        recorded = payload['lock'].get('recorded_at') or payload['lock'].get('synced_at')
        base = payload['lock'].get('source_commit') or payload['lock'].get('upstream_base_commit', '')
        print(f"  recorded: {recorded} @ {base[:12]}")
    else:
        print("  lock: missing (run: surf vendor.sync)")
    print(f"  package: {payload.get('package_version')}")
    print(f"  dist fresh: {payload.get('dist_fresh')} {payload.get('dist_reason','')}")
    print(f"  content identity: {payload.get('content_identity_matches')}")
    if payload.get("upstream_ahead") is True:
        print("  note: local dev fork is ahead of vendored lock — run surf vendor.sync --build --reload")
PY
