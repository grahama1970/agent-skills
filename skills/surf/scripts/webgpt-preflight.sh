#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/webgpt_resolve.sh
source "${SCRIPT_DIR}/lib/webgpt_resolve.sh"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_SH="${SURF_RUN_SH:-${SKILL_DIR}/run.sh}"

usage() {
  cat <<'EOF'
Usage:
  surf webgpt.preflight [options]

Validates extension socket, focus.state, and WebGPT tab targeting before submit.

Options:
  --tab-id ID
  --url URL
  --no-activate
  --allow-foreground-controlled
  --json
  -h, --help
EOF
}

tab_id=""
target_url=""
no_activate=0
allow_foreground=0
json_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tab-id) tab_id="${2:-}"; shift 2 ;;
    --url) target_url="${2:-}"; shift 2 ;;
    --no-activate) no_activate=1; shift ;;
    --allow-foreground-controlled) allow_foreground=1; shift ;;
    --json) json_only=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

export RUN_SH tab_id target_url no_activate allow_foreground json_only
exec python3 - "$@" <<'PY'
import json
import os
import subprocess
import sys

run_sh = os.environ["RUN_SH"]
tab_id = os.environ.get("tab_id", "")
target_url = os.environ.get("target_url", "")
no_activate = os.environ.get("no_activate") == "1"
allow_foreground = os.environ.get("allow_foreground") == "1"
json_only = os.environ.get("json_only") == "1"
lib = os.path.join(os.path.dirname(__file__), "lib")

def surf(*args):
    return subprocess.run([run_sh, *args], capture_output=True, text=True)

checks = []
failures = []

def add(name, ok, detail=""):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        failures.append(name)

sock_ok = os.path.exists("/tmp/surf.sock") or bool(os.environ.get("SURF_RUN_SH"))
add("surf_extension_socket", sock_ok, "ok" if sock_ok else "/tmp/surf.sock missing")

focus = surf("focus.state", "--json")
focus_json = focus.stdout.strip() if focus.returncode == 0 else ""
add("focus_state", bool(focus_json), "ok" if focus_json else "focus.state unavailable")
active_tab = ""
if focus_json:
    try:
        active_tab = str(json.loads(focus_json).get("activeTabId") or "")
    except json.JSONDecodeError:
        pass

tabs = surf("tab.list")
tab_list = tabs.stdout if tabs.returncode == 0 else ""
requested_tab_id = None

if tab_id:
    digits = "".join(c for c in tab_id if c.isdigit())[:20]
    if not digits:
        add("tab_id_valid", False, "invalid --tab-id")
    else:
        requested_tab_id = digits
        add("tab_id_valid", True, digits)
        open_ok = any(
            len(p := line.split("\t", 2)) >= 3
            and p[0] == digits
            and "chatgpt.com" in p[2]
            for line in tab_list.splitlines()
        )
        add("tab_open_chatgpt", open_ok, "ok" if open_ok else f"no open chatgpt tab {digits}")
elif target_url:
    proc = subprocess.run(
        [sys.executable, os.path.join(lib, "resolve_webgpt_tab.py"), "resolve-url", "--url", target_url],
        input=tab_list,
        capture_output=True,
        text=True,
    )
    try:
        resolved = json.loads(proc.stdout)
    except json.JSONDecodeError:
        resolved = {"ok": False, "error": "resolver_failed"}
    if resolved.get("ok"):
        requested_tab_id = resolved["tab_id"]
        add("url_resolve", True, f"tab_id={requested_tab_id}")
    else:
        err = resolved.get("error") or "no_open_tab_for_url"
        add("url_resolve", False, err)
        if err == "ambiguous_url":
            add("url_ambiguous", False, json.dumps(resolved.get("candidates") or []))
else:
    add("explicit_target", False, "pass --tab-id or --url")

if no_activate and requested_tab_id and not allow_foreground:
    if active_tab == requested_tab_id:
        add(
            "not_foreground_controlled",
            False,
            "controlled tab is active; switch tabs or --allow-foreground-controlled",
        )
    else:
        add(
            "not_foreground_controlled",
            True,
            f"active_tab={active_tab} controlled={requested_tab_id}",
        )

status = "pass" if not failures else "fail"
result = {
    "status": status,
    "failures": failures,
    "requested_tab_id": requested_tab_id,
    "requested_url": target_url or None,
    "active_tab_id": active_tab or None,
    "checks": checks,
}
text = json.dumps(result, indent=2) + "\n"
sys.stdout.write(text)
if not json_only:
    sys.stderr.write(f"webgpt.preflight: {status}\n")
raise SystemExit(0 if status == "pass" else 5)
PY
