#!/usr/bin/env python3
"""List and explicitly close VS Code windows for debugger hygiene.

Default is read-only. Closing requires --execute plus a filter, so $debugger does
not close unrelated user windows or Remote SSH sessions by accident.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


def wmctrl_rows() -> list[dict[str, object]]:
    wmctrl = shutil.which("wmctrl")
    if not wmctrl:
        return []
    out = subprocess.run([wmctrl, "-lG"], capture_output=True, text=True, timeout=5).stdout
    rows = []
    for row in out.splitlines():
        parts = row.split(None, 7)
        if len(parts) < 8 or "Visual Studio Code" not in parts[7]:
            continue
        rows.append({
            "id": parts[0],
            "desktop": parts[1],
            "x": int(parts[2]),
            "y": int(parts[3]),
            "width": int(parts[4]),
            "height": int(parts[5]),
            "host": parts[6],
            "title": parts[7],
            "remote": "remote-ssh" in parts[7],
        })
    return rows


def matches(row: dict[str, object], title: str | None, workspace: str | None, include_remote: bool) -> bool:
    row_title = str(row["title"])
    if row.get("remote") and not include_remote:
        return False
    return bool((title and title in row_title) or (workspace and workspace in row_title))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    close = sub.add_parser("close")
    close.add_argument("--title-contains")
    close.add_argument("--workspace")
    close.add_argument("--include-remote", action="store_true")
    close.add_argument("--all", action="store_true", help="Allow closing more than one matched window.")
    close.add_argument("--execute", action="store_true", help="Actually close; omitted means dry-run.")
    args = parser.parse_args()

    rows = wmctrl_rows()
    if args.cmd == "list":
        print(json.dumps({"schema": "debugger.vscode_windows.v1", "windows": rows}, indent=2))
        return 0

    if not args.title_contains and not args.workspace:
        print("REFUSE_CLOSE_UNFILTERED", file=sys.stderr)
        return 2
    targets = [row for row in rows if matches(row, args.title_contains, args.workspace, args.include_remote)]
    if len(targets) > 1 and not args.all:
        print(f"REFUSE_CLOSE_MULTIPLE count={len(targets)}", file=sys.stderr)
        return 2
    if not args.execute:
        print(json.dumps({"schema": "debugger.vscode_window_close_plan.v1", "execute": False, "targets": targets}, indent=2))
        return 0
    if not os.environ.get("DISPLAY") or not shutil.which("wmctrl"):
        print("WINDOW_CONTROL_UNAVAILABLE", file=sys.stderr)
        return 3
    for row in targets:
        subprocess.run(["wmctrl", "-ic", str(row["id"])], check=True, capture_output=True, text=True, timeout=5)
    print(json.dumps({"schema": "debugger.vscode_window_close_plan.v1", "execute": True, "closed": targets}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
