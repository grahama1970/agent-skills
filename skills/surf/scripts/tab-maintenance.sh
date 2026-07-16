#!/usr/bin/env bash
set -euo pipefail

# Host-side proactive maintenance coordinator for registered browser-oracle tabs.
# Defaults to dry-run and never creates or activates tabs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SURF_RUN="${SURF_RUN_SH:-${SCRIPT_DIR}/../run.sh}"
BACKEND="webgpt"
ROOT=""
RECEIPT_DIR="${SURF_TAB_MAINTENANCE_RECEIPT_DIR:-/tmp/surf-tab-maintenance-receipts}"
MODE="dry-run"
PROJECTS=()
GLOBAL_TRIGGER=""
TRIGGER_ARGS=()
TIMEOUT_SECONDS="${SURF_TAB_MAINTENANCE_TIMEOUT:-15}"

usage() {
  cat <<'EOF'
Usage: tab-maintenance.sh [--repair-safe|--repair|--dry-run] [--project NAME ...] [options]

Options:
  --backend NAME              Browser-oracle backend. Default: webgpt.
  --root DIR                  Project binding root. Default: backend env or ~/.pi/*-projects.
  --surf-run PATH             surf runtime. Default: SURF_RUN_SH or ../run.sh.
  --receipt-dir DIR           Directory for per-target receipts.
  --trigger TRIGGER           Specific repair trigger for every target.
  --repair-trigger P:T        Specific repair trigger for one project.
  --timeout SECONDS           Command timeout hint for tests/fakes.

Triggers that may reload: discarded, frozen, load_incomplete, recovery_state_failed.
The trigger "idle" is explicitly classified but is never a repair trigger.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repair|--repair-safe) MODE="repair"; shift ;;
    --dry-run) MODE="dry-run"; shift ;;
    --backend) BACKEND="${2:-}"; shift 2 ;;
    --root) ROOT="${2:-}"; shift 2 ;;
    --project) PROJECTS+=("${2:-}"); shift 2 ;;
    --surf-run) SURF_RUN="${2:-}"; shift 2 ;;
    --receipt-dir) RECEIPT_DIR="${2:-}"; shift 2 ;;
    --trigger) GLOBAL_TRIGGER="${2:-}"; shift 2 ;;
    --repair-trigger) TRIGGER_ARGS+=("${2:-}"); shift 2 ;;
    --timeout) TIMEOUT_SECONDS="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

export SURF_TAB_MAINTENANCE_SURF_RUN="$SURF_RUN"
export SURF_TAB_MAINTENANCE_BACKEND="$BACKEND"
export SURF_TAB_MAINTENANCE_ROOT="$ROOT"
export SURF_TAB_MAINTENANCE_RECEIPT_DIR="$RECEIPT_DIR"
export SURF_TAB_MAINTENANCE_MODE="$MODE"
export SURF_TAB_MAINTENANCE_GLOBAL_TRIGGER="$GLOBAL_TRIGGER"
export SURF_TAB_MAINTENANCE_TIMEOUT="$TIMEOUT_SECONDS"
export SURF_TAB_MAINTENANCE_SCRIPT_DIR="$SCRIPT_DIR"
export SURF_TAB_MAINTENANCE_PROJECTS_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${PROJECTS[@]}")"
export SURF_TAB_MAINTENANCE_TRIGGERS_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${TRIGGER_ARGS[@]}")"

python3 - <<'PY'
from __future__ import annotations

import json, os, re, subprocess, sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, os.environ["SURF_TAB_MAINTENANCE_SCRIPT_DIR"])
from tab_recovery_receipt import write_tab_recovery_receipt


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name).strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-._")
    if not cleaned:
        raise SystemExit("empty project name")
    return cleaned[:128]


def default_root(backend: str) -> Path:
    env = {
        "webgpt": "BROWSER_ORACLE_WEBGPT_PROJECT_ROOT",
        "webgemini": "BROWSER_ORACLE_WEBGEMINI_PROJECT_ROOT",
        "webkimi": "BROWSER_ORACLE_WEBKIMI_PROJECT_ROOT",
        "cursor-browser": "BROWSER_ORACLE_CURSOR_BROWSER_PROJECT_ROOT",
    }.get(backend, "BROWSER_ORACLE_WEBGPT_PROJECT_ROOT")
    if os.environ.get(env):
        return Path(os.environ[env]).expanduser()
    dirname = {
        "webgpt": "webgpt-projects",
        "webgemini": "webgemini-projects",
        "webkimi": "webkimi-projects",
        "cursor-browser": "cursor-browser-projects",
    }.get(backend, f"{backend}-projects")
    return Path.home() / ".pi" / dirname


def normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        p = urlsplit(raw)
        path = re.sub(r"/{2,}", "/", p.path or "/")
        if path != "/":
            path = path.rstrip("/")
        query = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))
    except Exception:
        return raw


def receipt(path: Path, **kw):
    status = kw.pop("status")
    project = kw.pop("project")
    write_tab_recovery_receipt(
        path,
        status=status,
        project=project,
        requested_tab_id=kw.pop("requested_tab_id", None),
        resolved_tab_id=kw.pop("resolved_tab_id", None),
        url_evidence=kw.pop("url_evidence", None),
        guard_values=kw.pop("guard_values", {}),
        repair_trigger=kw.pop("repair_trigger", None),
        action_started_at=kw.pop("action_started_at", None),
        action_finished_at=kw.pop("action_finished_at", None),
        before_observation=kw.pop("before_observation", None),
        after_observation=kw.pop("after_observation", None),
        extra_fields=kw,
    )
    payload = json.loads(path.read_text())
    print(json.dumps(payload, sort_keys=True))


def surf_cmd(*args):
    surf = os.environ["SURF_TAB_MAINTENANCE_SURF_RUN"]
    return subprocess.run([surf, *args], text=True, capture_output=True, timeout=float(os.environ.get("SURF_TAB_MAINTENANCE_TIMEOUT", "15") or 15))


def parse_tabs(stdout: str):
    tabs = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            tabs.append({"tab_id": parts[0], "title": parts[1], "url": parts[2]})
    return tabs


def guard_value_is_inactive(v):
    if isinstance(v, dict):
        value = v.get("value", v.get("active", v.get("isActive", v.get("ok"))))
        return value is False
    return v is False


def guard_value_is_known(v):
    if isinstance(v, dict):
        value = v.get("value", v.get("active", v.get("isActive", v.get("ok"))))
        return isinstance(value, bool)
    return isinstance(v, bool)


def guards_safe(state):
    guards = (state or {}).get("guards") or {}
    required = ["chatgptGeneration", "nonEmptyEditableDraft", "activeDownload"]
    if not all(k in guards for k in required):
        return False, {}, {"known": False, "reason": "missing required guard", "guards": guards}
    safety = {
        "chatgpt_generation_inactive": guard_value_is_inactive(guards["chatgptGeneration"]),
        "draft_empty": guard_value_is_inactive(guards["nonEmptyEditableDraft"]),
        "download_inactive": guard_value_is_inactive(guards["activeDownload"]),
    }
    if not all(safety.values()):
        known = all(guard_value_is_known(guards[key]) for key in required)
        reason = "hazard guard true" if known else "hazard guard active or unknown"
        return False, safety, {"known": known, "reason": reason, "guards": guards}
    return True, safety, {"known": True, "reason": "all hazard guards false", "guards": guards}


backend = os.environ["SURF_TAB_MAINTENANCE_BACKEND"]
root = Path(os.environ["SURF_TAB_MAINTENANCE_ROOT"]).expanduser() if os.environ["SURF_TAB_MAINTENANCE_ROOT"].strip() else default_root(backend)
receipt_dir = Path(os.environ["SURF_TAB_MAINTENANCE_RECEIPT_DIR"]).expanduser()
repair = os.environ["SURF_TAB_MAINTENANCE_MODE"] == "repair"
projects = json.loads(os.environ["SURF_TAB_MAINTENANCE_PROJECTS_JSON"])
trigger_map = {}
for item in json.loads(os.environ["SURF_TAB_MAINTENANCE_TRIGGERS_JSON"]):
    if ":" in item:
        p, t = item.split(":", 1)
        trigger_map[safe_name(p)] = t.strip()
global_trigger = os.environ.get("SURF_TAB_MAINTENANCE_GLOBAL_TRIGGER", "").strip()

if not projects:
    projects = [p.stem for p in sorted(root.glob("*.json"))]

# The scheduled run inventories browser tabs exactly once.
try:
    proc = surf_cmd("tab.list")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"tab.list exit {proc.returncode}")
    inventory = parse_tabs(proc.stdout)
    inventory_error = None
except Exception as exc:
    inventory, inventory_error = [], str(exc)

by_id = {str(t["tab_id"]): t for t in inventory}
by_norm_url = {}
for t in inventory:
    by_norm_url.setdefault(normalize_url(t.get("url", "")), []).append(t)

reload_triggers = {"discarded", "frozen", "load_incomplete", "recovery_state_failed"}
exit_code = 0
for project in projects:
    project = safe_name(project)
    path = root / f"{project}.json"
    trigger = trigger_map.get(project, global_trigger).strip()
    rpath = receipt_dir / f"{project}.json"
    base = {"project": project, "backend": backend, "mode": "repair" if repair else "dry-run", "repair_trigger": trigger or None, "inventory_count": len(inventory)}
    if inventory_error:
        receipt(rpath, **base, status="failed", success=False, reason="inventory_failed", error=inventory_error)
        exit_code = 1
        continue
    if not path.exists():
        receipt(rpath, **base, status="failed", success=False, reason="missing_binding", state_path=str(path))
        exit_code = 1
        continue
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict):
            raise ValueError("binding is not a JSON object")
    except Exception as exc:
        receipt(rpath, **base, status="failed", success=False, reason="invalid_binding", error=str(exc), state_path=str(path))
        exit_code = 1
        continue

    stored_tab = str(state.get("tab_id") or "")
    target_url = str(state.get("conversation_url") or "").strip()
    live = by_id.get(stored_tab)
    matches = by_norm_url.get(normalize_url(target_url), []) if target_url else []
    stale_unique = bool(target_url and (not live or normalize_url(live.get("url", "")) != normalize_url(target_url)) and len(matches) == 1)
    classification = "current" if live and normalize_url(live.get("url", "")) == normalize_url(target_url) else ("stale_url_unique" if stale_unique else "unmatched")
    before = {"binding": state, "live_tab": live, "url_matches": matches, "classification": classification}

    # Rebind is the only stale-URL repair and only when the exact stored target URL is unique.
    if stale_unique:
        if repair:
            previous = deepcopy(state)
            state["tab_id"] = str(matches[0]["tab_id"])
            state["conversation_url"] = matches[0]["url"]
            state["last_used_at"] = state["last_verified_at"] = now()
            tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
            tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
            tmp.replace(path)
            receipt(rpath, **base, status="rebound", requested_tab_id=stored_tab, resolved_tab_id=state["tab_id"], before_observation=before, after_observation={"binding": state}, previous_binding=previous, guard_values={"stored_url_match": True, "unique_live_match": True}, url_evidence={"stored_url": target_url, "matched_tab": matches[0]})
        else:
            receipt(rpath, **base, status="scanned", requested_tab_id=stored_tab, resolved_tab_id=matches[0]["tab_id"], before_observation=before, url_evidence={"stored_url": target_url, "matched_tab": matches[0]}, dry_run_would="rebind")
        continue

    # Idle alone is not a repair trigger; no trigger means read-only scan.
    if not trigger or trigger == "idle" or trigger not in reload_triggers:
        receipt(rpath, **base, status="scanned", requested_tab_id=stored_tab, resolved_tab_id=stored_tab if live else None, before_observation=before, reason="no_specific_repair_trigger" if not trigger or trigger == "idle" else "unsupported_repair_trigger")
        continue

    if not live:
        receipt(rpath, **base, status="skipped_guarded", requested_tab_id=stored_tab, resolved_tab_id=None, before_observation=before, reason="stored_tab_not_live")
        continue

    try:
        rp = surf_cmd("tab.recovery-state", "--tab-id", str(stored_tab), "--json")
        if rp.returncode != 0:
            raise RuntimeError(rp.stderr.strip() or f"recovery-state exit {rp.returncode}")
        recovery_state = json.loads(rp.stdout)
    except Exception as exc:
        receipt(rpath, **base, status="skipped_guarded", requested_tab_id=stored_tab, resolved_tab_id=stored_tab, before_observation=before, guard_values={"known": False, "reason": str(exc)}, reason="guard_inspection_failed")
        continue
    safe, guard_values, guard_observation = guards_safe(recovery_state)
    if not safe:
        receipt(rpath, **base, status="skipped_guarded", requested_tab_id=stored_tab, resolved_tab_id=stored_tab, before_observation=before, guard_values=guard_values, guard_observation=guard_observation, reason="guards_not_safe")
        continue
    if repair:
        rp = surf_cmd("tab.reload", "--tab-id", str(stored_tab))
        if rp.returncode == 0:
            receipt(rpath, **base, status="reloaded", requested_tab_id=stored_tab, resolved_tab_id=stored_tab, before_observation=before, after_observation={"reload": "requested"}, guard_values=guard_values, guard_observation=guard_observation)
        else:
            receipt(rpath, **base, status="failed", success=False, requested_tab_id=stored_tab, resolved_tab_id=stored_tab, before_observation=before, guard_values=guard_values, reason="reload_failed", error=rp.stderr.strip())
            exit_code = 1
    else:
        receipt(rpath, **base, status="scanned", requested_tab_id=stored_tab, resolved_tab_id=stored_tab, before_observation=before, guard_values=guard_values, dry_run_would="reload")

sys.exit(exit_code)
PY
