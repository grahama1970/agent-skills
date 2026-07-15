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
LOCAL_APP_URL="${SURF_LIVE_CANARY_LOCAL_APP_URL:-auto}"
WORK_DIR=""
OUTPUT_DIR=""
TIMEOUT_SECONDS="${SURF_LIVE_CANARY_TIMEOUT:-15}"
KEEP_ARTIFACTS=0
JSON_ONLY=0
ALLOW_UNREACHABLE=0
PRESERVE_TABS=0

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
  --local-app-url URL     Reachable local app base URL. Default: an owned disposable loopback server
  --surf-run PATH         Surf runtime. Default: SURF_RUN_SH or ../run.sh
  --work-dir DIR          Temporary artifact root. Default: mktemp under /tmp
  --output-dir DIR        Durable artifact root containing result.json
  --timeout SECONDS       Per-command timeout. Default: SURF_LIVE_CANARY_TIMEOUT or 15
  --keep-artifacts        Do not remove temporary binding/receipt directories
  --preserve-tabs         Assert pre-existing tabs are preserved; disposable canary tabs are still closed
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
    --output-dir) OUTPUT_DIR="${2:-}"; WORK_DIR="${2:-}"; KEEP_ARTIFACTS=1; shift 2 ;;
    --timeout) TIMEOUT_SECONDS="${2:-}"; shift 2 ;;
    --keep-artifacts) KEEP_ARTIFACTS=1; shift ;;
    --preserve-tabs) PRESERVE_TABS=1; shift ;;
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

python3 - "$SURF_RUN" "$TAB_MAINTENANCE" "$SOCKET" "$LOCAL_APP_URL" "$WORK_DIR" "$OUTPUT_DIR" "$TIMEOUT_SECONDS" "$KEEP_ARTIFACTS" "$JSON_ONLY" "$ALLOW_UNREACHABLE" "$PRESERVE_TABS" <<'PY'
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

surf_run, tab_maintenance, sock, local_app, work_dir_arg, output_dir_arg, timeout_s, keep_s, json_s, allow_s, preserve_tabs_s = sys.argv[1:]
timeout = float(timeout_s or 15)
keep = keep_s == "1"
json_only = json_s == "1"
allow_unreachable = allow_s == "1"
preserve_tabs = preserve_tabs_s == "1"
created_tabs: list[str] = []
created_paths: list[Path] = []
summary: dict = {"schema": "surf.live_tab_maintenance_canary.v1", "status": "failed"}
owned_server: ThreadingHTTPServer | None = None


def emit(obj: dict):
    if output_dir_arg:
        output_dir = Path(output_dir_arg).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        result_path = output_dir / "result.json"
        tmp = result_path.with_name(f".{result_path.name}.tmp.{os.getpid()}")
        tmp.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
        tmp.replace(result_path)
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


def focus_identity(state: dict) -> dict:
    return {
        "focusedWindowId": state.get("focusedWindowId"),
        "activeTabId": state.get("activeTabId"),
        "activeTabUrl": norm(state.get("activeTabUrl", "")),
    }


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
    p = surf("tab.new", url, "--background", check=False)
    if p.returncode != 0:
        p = surf("tab.new", "--url", url, "--background", check=False)
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


if local_app == "auto":
    class CanaryHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            scenario = dict(parse_qsl(urlsplit(self.path).query)).get("scenario", "")
            body = "<h1>Surf recovery canary</h1>"
            if scenario == "draft-present":
                body += '<textarea aria-label="Canary draft">unsent canary draft</textarea>'
            elif scenario == "active-generation":
                body += '<button aria-label="Stop generating" style="width:120px;height:32px">Stop</button>'
            payload = f"<!doctype html><title>{scenario or 'canary'}</title>{body}".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format, *_args):
            return

    owned_server = ThreadingHTTPServer(("127.0.0.1", 0), CanaryHandler)
    Thread(target=owned_server.serve_forever, daemon=True).start()
    local_app = f"http://127.0.0.1:{owned_server.server_port}"

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
    tabs_before = list_tabs()
    focus_before_raw = surf("focus.state", "--json", check=False).stdout.strip() or "{}"
    focus_before = json.loads(focus_before_raw)
    if not isinstance(focus_before, dict):
        raise RuntimeError("focus.state did not return a JSON object")

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
    (work / "maintenance.stdout.txt").write_text(maint.stdout)
    (work / "maintenance.stderr.txt").write_text(maint.stderr)

    got = {
        "reload": receipt_ok(receipts / f"{projects['reload']}.json", projects["reload"], "reloaded"),
        "draft": receipt_ok(receipts / f"{projects['draft']}.json", projects["draft"], "skipped_guarded", "guards_not_safe"),
        "generation": receipt_ok(receipts / f"{projects['generation']}.json", projects["generation"], "skipped_guarded", "guards_not_safe"),
        "ambiguous": receipt_ok(receipts / f"{projects['ambiguous']}.json", projects["ambiguous"], "skipped_guarded", "stored_tab_not_live"),
    }
    exact_ids = {
        "reload": reload_tab,
        "draft": draft_tab,
        "generation": generation_tab,
    }
    for scenario, expected_id in exact_ids.items():
        item = got[scenario]
        if str(item.get("requested_tab_id")) != expected_id or str(item.get("resolved_tab_id")) != expected_id:
            raise AssertionError(f"{scenario} receipt lost exact tab identity: {item}")
    if len(got["ambiguous"].get("before_observation", {}).get("url_matches", [])) != 2:
        raise AssertionError(f"ambiguous receipt lacks two exact URL matches: {got['ambiguous']}")

    tabs_after_maintenance = list_tabs()
    scenario_urls = {reload_tab: reload_url, draft_tab: draft_url, generation_tab: generation_url,
                     ambiguous_tab_a: ambiguous_url, ambiguous_tab_b: ambiguous_url}
    observed_urls = {str(t.get("tab_id")): norm(t.get("url", "")) for t in tabs_after_maintenance}
    if any(observed_urls.get(tab_id) != norm(url) for tab_id, url in scenario_urls.items()):
        raise AssertionError("a canary tab navigated away from its exact scenario URL")

    cleanup(None)
    tabs_final = list_tabs()
    focus_after_raw = surf("focus.state", "--json", check=False).stdout.strip() or "{}"
    focus_after = json.loads(focus_after_raw)
    if not isinstance(focus_after, dict):
        raise RuntimeError("focus.state did not return a JSON object after maintenance")
    before_identity = {str(t.get("tab_id")): norm(t.get("url", "")) for t in tabs_before}
    final_identity = {str(t.get("tab_id")): norm(t.get("url", "")) for t in tabs_final}
    leaked_canary_tabs = sorted(set(created_tabs) & set(final_identity))
    changed_preexisting_tabs = sorted(
        tab_id for tab_id, url in before_identity.items()
        if tab_id in final_identity and final_identity[tab_id] != url
    )
    concurrent_tab_delta = {
        "added": sorted(set(final_identity) - set(before_identity)),
        "removed": sorted(set(before_identity) - set(final_identity)),
        "changed_url": changed_preexisting_tabs,
    }
    # Attribute mutations only to exact canary-owned IDs. Other project agents may
    # legitimately add or close unrelated tabs while this concurrent canary runs.
    unintended_mutations = len(leaked_canary_tabs)
    intended_reloads = sum(1 for item in got.values() if item.get("status") == "reloaded")
    guarded_skips = sum(1 for item in got.values() if item.get("status") == "skipped_guarded")
    focus_changed = focus_identity(focus_before) != focus_identity(focus_after)
    if maint.returncode != 0 or intended_reloads != 1 or guarded_skips != 3 or unintended_mutations or focus_changed:
        raise AssertionError(
            "live maintenance counters did not meet the bounded canary contract: "
            f"maintenance_exit={maint.returncode} reloads={intended_reloads} "
            f"skips={guarded_skips} leaked_canary_tabs={leaked_canary_tabs} "
            f"focus_changed={focus_changed}"
        )
    summary.update({
        "status": "pass",
        "mocked": allow_unreachable,
        "live": not allow_unreachable,
        "intended_reloads": intended_reloads,
        "unintended_mutations": unintended_mutations,
        "guarded_skips": guarded_skips,
        "focus_changed": focus_changed,
        "focus_identity_before": focus_identity(focus_before),
        "focus_identity_after": focus_identity(focus_after),
        "preserved_preexisting_tabs": preserve_tabs,
        "work_dir": str(work),
        "created_tab_ids": created_tabs,
        "focus_before": focus_before,
        "focus_after": focus_after,
        "tabs_before": tabs_before,
        "tabs_after_maintenance": tabs_after_maintenance,
        "tabs_final": tabs_final,
        "leaked_canary_tabs": leaked_canary_tabs,
        "concurrent_tab_delta": concurrent_tab_delta,
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
    if owned_server is not None:
        owned_server.shutdown()
        owned_server.server_close()
PY
