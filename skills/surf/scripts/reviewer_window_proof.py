#!/usr/bin/env python3
"""Live reviewer-window hygiene proof (#1222).

open-bind a non-webgpt seat -> assert windowed + unfocused + moved to the
reviewer desktop (wmctrl readback, not the fuzzy title annotation) -> close
the window (post-ingestion behavior) -> assert the tab is gone. Prints
marker lines the agentic-eval fixture asserts on; exits nonzero on any
violation. Cleans up its window even on failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
ORACLE = SKILLS / "browser-oracle" / "run.sh"
SURF = SKILLS / "surf" / "run.sh"
REVIEWER_DESKTOP = "1"  # wmctrl index for KDE "Desktop 2"


def run(cmd: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(Path(cmd[0]).parent))


def surf_tabs() -> list[dict]:
    proc = run([str(SURF), "tab.list", "--json"])
    data = json.loads(proc.stdout or "[]")
    return data.get("tabs", data) if isinstance(data, dict) else data


def main() -> int:
    ok = True
    proc = run([str(ORACLE), "open-bind", "eval-reviewer-window", "--backend", "webkimi", "--url", "https://kimi.com/", "--json"])
    if proc.returncode != 0:
        print(f"OPEN_BIND_FAILED: {proc.stderr[:200]}")
        return 1
    payload = json.loads(proc.stdout)
    tab_id = payload["tab_id"]
    cmd = payload.get("open_command") or []
    move = payload.get("kde_move") or {}

    print("WINDOWED" if "window.new" in cmd else "TABBED")
    print("UNFOCUSED" if "--unfocused" in cmd else "FOCUS_STEAL")
    print(f"MOVE:{move.get('status')}:{move.get('desktop_index')}")
    ok &= "window.new" in cmd and "--unfocused" in cmd and move.get("status") == "moved"

    x11_window = str(move.get("window") or "")
    if x11_window:
        listing = subprocess.run(["wmctrl", "-lx"], capture_output=True, text=True, timeout=5)
        for line in listing.stdout.splitlines():
            if x11_window.lower() in line.lower():
                desktop = line.split()[1]
                print(f"WMCTRL_DESKTOP:{desktop}")
                ok &= desktop == REVIEWER_DESKTOP
                break

    # Post-ingestion behavior: close the provisioned window, verify gone.
    window_id = next((str(t["windowId"]) for t in surf_tabs() if t.get("id") == tab_id), "")
    if window_id:
        run([str(SURF), "window.close", window_id, "--json"])
    time.sleep(2)
    still_there = any(t.get("id") == tab_id for t in surf_tabs())
    print("WINDOW_LEAKED" if still_there else "CLOSED_AFTER_INGEST")
    ok &= not still_there
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
