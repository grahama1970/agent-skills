#!/usr/bin/env python3
"""Plain-text queue view of project-watchdog state. Works in any terminal.

Reads the same ui-data snapshot the React Flow control tower uses, plus the
newest tau-stream-monitor for the live seat. Pair with watch(1) for a live
pane: watch -n 15 -t queue-view.py
"""
import json, os, glob, time
from pathlib import Path

STATE = Path(os.environ.get("PROJECT_WATCHDOG_STATE_ROOT", Path.home() / ".local/state/project-watchdog"))
SNAP = Path(__file__).resolve().parents[1] / "ui" / "dist" / "project-watchdog-snapshot.json"

d = json.loads(SNAP.read_text())
print(f"PROJECT WATCHDOG QUEUE   snapshot {d.get('generated_at','?')[:19]}  global={d.get('global_state',{}).get('global',{}).get('state','?')}")
print("-" * 78)
for it in (d.get("items") or [])[:12]:
    st = it.get("status") or "?"
    mark = {"COMPLETED": "+", "NEEDS_ATTENTION": "!", "BLOCKED": "X", "DRY_RUN": "~"}.get(st, "?")
    issue = it.get("issue_number") or it.get("issue") or "-"
    print(f" {mark} {st:<16} #{str(issue):<6} {str(it.get('summary') or it.get('stop_reason') or '')[:52]}")
print("-" * 78)
mons = sorted(glob.glob(str(STATE / "receipts/*/tau-stream-monitor.json")), key=os.path.getmtime)
if mons:
    m = json.loads(open(mons[-1]).read())
    ev = m.get("latest_event") or {}
    live = "LIVE" if m.get("process_running") else "idle"
    print(f" {live}: {m.get('current_status')} node={ev.get('node_id') or '-'} elapsed={int(m.get('elapsed_seconds') or 0)}s run={Path(mons[-1]).parent.name[17:31]}")
print(f" refreshed {time.strftime('%H:%M:%SZ', time.gmtime())}")
