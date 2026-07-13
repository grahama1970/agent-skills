#!/usr/bin/env bash
set -euo pipefail

# Bounded live canary for Surf tab maintenance.
# Refuses by default unless the Surf extension socket and a caller-supplied local app
# are reachable. It creates only disposable local-app tabs and project bindings, then
# removes only those resources.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SURF_RUN="${SURF_RUN_SH:-${SCRIPT_DIR}/../run.sh}"
TAB_MAINTENANCE="${SURF_TAB_MAINTENANCE_SH:-${SCRIPT_DIR}/tab-maintenance.sh}"
SOCKET="${SURF_EXTENSION_SOCKET:-/tmp/surf.sock}"
LOCAL_APP_URL="${SURF_LIVE_CANARY_LOCAL_APP_URL:-http://127.0.0.1:8765}"
WORK_DIR=""
TIMEOUT_SECONDS="${SURF_LIVE_CANARY_TIMEOUT:-15}"
KEEP_ARTIFACTS=0
JSON_ONLY=0
ALLOW_UNREACHABLE=0

usage() {
  cat <<'EOF'
Usage: live-tab-maintenance-canary.sh [options]

Creates disposable local-app browser tabs and temporary browser-oracle bindings,
then exercises tab-maintenance repair/guard paths:
  * one intended recoverable reload
  * draft-present guarded skip
  * ambiguous-URL guarded skip
  * active-generation guarded skip

Options:
  --local-app-url URL     Reachable local app base URL. Default: SURF_LIVE_CANARY_LOCAL_APP_URL or http://127.0.0.1:8765
  --surf-run PATH         Surf runtime. Default: SURF_RUN_SH or ../run.sh
  --work-dir DIR          Temporary artifact root. Default: mktemp under /tmp
  --timeout SECONDS       Per-command timeout. Default: SURF_LIVE_CANARY_TIMEOUT or 15
  --keep-artifacts        Do not remove temporary binding/receipt directories
  --allow-unreachable     Test-only override for socket/local-app preflight refusal
  --json                  Emit machine-readable summary only
  -h, --help              Show help

Exit: 0 PASS | 2 usage | 3 refused/skipped | 5 failed
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local-app-url) LOCAL_APP_URL="${2:-}"; shift 2 ;;
    --surf-run) SURF_RUN="${2:-}"; shift 2 ;;
    --work-dir) WORK_DIR="${2:-}"; shift 2 ;;
    --timeout) TIMEOUT_SECONDS="${2:-}"; shift 2 ;;
    --keep-artifacts) KEEP_ARTIFACTS=1; shift ;;
    --allow-unreachable) ALLOW_UNREACHABLE=1; shift ;;
    --json) JSON_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$LOCAL_APP_URL" ]]; then
  echo "REFUSE: empty local app URL" >&2
  exit 3
fi

python3 - "$SURF_RUN" "$TAB_MAINTENANCE" "$SOCKET" "$LOCAL_APP_URL" "$WORK_DIR" "$TIMEOUT_SECONDS" "$KEEP_ARTIFACTS" "$JSON_ONLY" "$ALLOW_UNREACHABLE" <<'PY'
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

surf_run, tab_maintenance, sock, local_app, work_dir_arg, timeout_s, keep_s, json_s, allow_s = sys.argv[1:]
timeout = float(timeout_s or 15)
keep = keep_s == "1"
json_only = json_s == "1"
allow_unreachable = allow_s == "1"
created_tabs: list[str] = []
created_paths: list[Path] = []
summary: dict = {"schema": "surf.live_tab_maintenance_canary.v1", "status": "failed"}


def emit(obj: dict):
    if json_only:
        print(json.dumps(obj, sort_keys=True))
    else:
        print(json.dumps(obj, indent=2, sort_keys=True))


def refuse(reason: str, detail: str = ""):
    summary.update({"status": "refused", "reason": reason, "detail": detail})
    emit(summary)
    raise SystemExit(3)


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed ({p.returncode}): {' '.join(args)}\nstderr={p.stderr.strip()}\nstdout={p.stdout.strip()}")
    return p


def surf(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run([surf_run, *args], check=check)


def norm(url: str) -> str:
    p = urlsplit(str(url or ""))
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


def tabs_from_list(stdout: str) -> list[dict]:
    try:
        data = json.loads(stdout)
        if isinstance(data, list):
            return [{"tab_id": str(t.get("tab_id", t.get("id", ""))), "title": str(t.get("title", "")), "url": str(t.get("url", ""))} for t in data]
        if isinstance(data, dict) and isinstance(data.get("tabs"), list):
            return [{"tab_id": str(t.get("tab_id", t.get("id", ""))), "title": str(t.get("title", "")), "url": str(t.get("url", ""))} for t in data["tabs"]]
    except Exception:
        pass
    out = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            out.append({"tab_id": parts[0], "title": parts[1], "url": parts[2]})
    return out


def list_tabs() -> list[dict]:
    p = surf("tab.list", "--json", check=False)
    if p.returncode == 0:
        tabs = tabs_from_list(p.stdout)
        if tabs:
            return tabs
    return tabs_from_list(surf("tab.list").stdout)


def find_unique_tab(url: str, before_ids: set[str]) -> str:
    wanted = norm(url)
    deadline = time.time() + timeout
    last = []
    while time.time() < deadline:
        last = [t for t in list_tabs() if norm(t.get("url", "")) == wanted and str(t.get("tab_id")) not in before_ids]
        if len(last) == 1 and last[0].get("tab_id"):
            return str(last[0]["tab_id"])
        time.sleep(0.25)
    raise RuntimeError(f"could not identify exactly one created tab for {url}; matches={last}")


def create_tab(url: str) -> str:
    before = {str(t.get("tab_id")) for t in list_tabs()}
    p = surf("tab.new", url, check=False)
    if p.returncode != 0:
        p = surf("tab.new", "--url", url, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"tab.new failed for {url}: {p.stderr.strip() or p.stdout.strip()}")
    tid = ""
    try:
        data = json.loads(p.stdout)
        tid = str(data.get("tab_id", data.get("id", ""))) if isinstance(data, dict) else ""
    except Exception:
        m = re.search(r"\b(\d{1,20})\b", p.stdout)
        tid = m.group(1) if m else ""
    if not tid:
        tid = find_unique_tab(url, before)
    created_tabs.append(tid)
    return tid


def write_binding(root: Path, project: str, tab_id: str, url: str):
    path = root / f"{project}.json"
    payload = {
        "backend": "webgpt",
        "canary_disposable": True,
        "conversation_url": url,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project": project,
        "tab_id": str(tab_id),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    created_paths.append(path)


def receipt_ok(path: Path, project: str, status: str, reason: str | None = None) -> dict:
    if not path.exists():
        raise AssertionError(f"missing receipt {path}")
    data = json.loads(path.read_text())
    if data.get("schema") != "surf.tab_maintenance_receipt.v1":
        raise AssertionError(f"bad receipt schema for {project}: {data}")
    if data.get("project") != project:
        raise AssertionError(f"bad receipt project for {project}: {data}")
    if data.get("status") != status:
        raise AssertionError(f"bad receipt status for {project}: expected {status}, got {data.get('status')}: {data}")
    if reason is not None and data.get("reason") != reason:
        raise AssertionError(f"bad receipt reason for {project}: expected {reason}, got {data.get('reason')}: {data}")
    if status in {"reloaded", "rebound"} and data.get("success") is not True:
        raise AssertionError(f"successful maintenance receipt not marked success: {data}")
    if status not in {"reloaded", "rebound"} and data.get("success") is True:
        raise AssertionError(f"guarded/non-repair receipt unexpectedly successful: {data}")
    return data


def local_url(token: str, scenario: str) -> str:
    sep = "&" if "?" in local_app else "?"
    return f"{local_app.rstrip('/')}/surf-tab-maintenance-canary{sep}token={token}&scenario={scenario}"


def cleanup(work: Path | None):
    for tid in reversed(created_tabs):
        if re.fullmatch(r"\d{1,20}", str(tid)):
            surf("tab.close", str(tid), check=False)
    for path in created_paths:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    if work and not keep:
        shutil.rmtree(work, ignore_errors=True)


if not allow_unreachable:
    if not socket.socket(socket.AF_UNIX).connect_ex(sock) == 0:
        refuse("extension_socket_unreachable", sock)
    try:
        with urllib.request.urlopen(local_app, timeout=min(timeout, 5.0)) as resp:
            if resp.status >= 400:
                refuse("local_app_unreachable", f"HTTP {resp.status} at {local_app}")
    except Exception as exc:
        refuse("local_app_unreachable", f"{local_app}: {exc}")

work = Path(work_dir_arg).expanduser() if work_dir_arg else Path(tempfile.mkdtemp(prefix="surf-live-tab-maint-canary-"))
root = work / "bindings"
receipts = work / "receipts"
root.mkdir(parents=True, exist_ok=True)
receipts.mkdir(parents=True, exist_ok=True)
created_root = not bool(work_dir_arg)

try:
    token = f"{os.getpid()}-{int(time.time())}"
    focus_before = surf("focus.state", "--json", check=False).stdout.strip() or "{}"

    projects = {
        "reload": f"canary-reload-{token}",
        "draft": f"canary-draft-{token}",
        "generation": f"canary-generation-{token}",
        "ambiguous": f"canary-ambiguous-{token}",
    }
    reload_url = local_url(token, "safe-reload")
    draft_url = local_url(token, "draft-present")
    generation_url = local_url(token, "active-generation")
    ambiguous_url = local_url(token, "ambiguous-url")

    reload_tab = create_tab(reload_url)
    draft_tab = create_tab(draft_url)
    generation_tab = create_tab(generation_url)
    ambiguous_tab_a = create_tab(ambiguous_url)
    ambiguous_tab_b = create_tab(ambiguous_url)

    write_binding(root, projects["reload"], reload_tab, reload_url)
    write_binding(root, projects["draft"], draft_tab, draft_url)
    write_binding(root, projects["generation"], generation_tab, generation_url)
    # Deliberately stale/non-live id plus two live matching URLs: maintenance must not choose.
    write_binding(root, projects["ambiguous"], "999999999", ambiguous_url)

    cmd = [
        tab_maintenance,
        "--repair",
        "--root", str(root),
        "--receipt-dir", str(receipts),
        "--surf-run", surf_run,
        "--timeout", str(int(timeout)),
    ]
    for p in projects.values():
        cmd.extend(["--project", p])
    cmd.extend(["--repair-trigger", f"{projects['reload']}:discarded"])
    cmd.extend(["--repair-trigger", f"{projects['draft']}:discarded"])
    cmd.extend(["--repair-trigger", f"{projects['generation']}:discarded"])
    cmd.extend(["--repair-trigger", f"{projects['ambiguous']}:discarded"])
    maint = run(cmd, check=False)

    got = {
        "reload": receipt_ok(receipts / f"{projects['reload']}.json", projects["reload"], "reloaded"),
        "draft": receipt_ok(receipts / f"{projects['draft']}.json", projects["draft"], "skipped_guarded", "guards_not_safe"),
        "generation": receipt_ok(receipts / f"{projects['generation']}.json", projects["generation"], "skipped_guarded", "guards_not_safe"),
        "ambiguous": receipt_ok(receipts / f"{projects['ambiguous']}.json", projects["ambiguous"], "skipped_guarded", "stored_tab_not_live"),
    }
    focus_after = surf("focus.state", "--json", check=False).stdout.strip() or "{}"
    summary.update({
        "status": "pass",
        "work_dir": str(work),
        "created_tab_ids": created_tabs,
        "focus_before": json.loads(focus_before) if focus_before.startswith("{") else focus_before,
        "focus_after": json.loads(focus_after) if focus_after.startswith("{") else focus_after,
        "maintenance_exit_code": maint.returncode,
        "receipts": got,
    })
    emit(summary)
    raise SystemExit(0)
except SystemExit:
    raise
except Exception as exc:
    summary.update({"status": "failed", "error": str(exc), "work_dir": str(work), "created_tab_ids": created_tabs})
    emit(summary)
    raise SystemExit(5)
finally:
    cleanup(work if created_root or not keep else None)
PY
