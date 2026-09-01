#!/usr/bin/env python3
"""Reveal a file in the running VS Code at a line, function, or class.

This is the debugger's lightweight collaboration surface, separate from starting
a debug session: when the agent is stuck on a spot -- or the human wants to look
-- this jumps the human's editor straight to the code in question. The human can
then eyeball it and, if they want, ask the agent to start a debug session there
(scripts/vscode_bridge_session.py) and discuss the paused state.

Locating the code:
    --line N              go to line N
    --function NAME       first `def NAME` / `function NAME` / `fn NAME`
    --class NAME          first `class NAME`
    --symbol NAME         a function OR class named NAME
    --json-field NAME     first JSON object key named NAME; dotted paths use the
                          final key (for example cases[].trials[].stderr -> stderr)

For Python files symbols are resolved with the ast (robust to formatting); for
other languages a line-based scan handles def/function/fn/class. JSON fields use
a textual key locator so malformed eval reports can still be opened at the raw
field. `--print-only` resolves and prints the location without opening anything
(deterministic, needs no display).

Reveal uses `code --reuse-window --goto <file>:<line>:<col>`. VS Code places the
cursor on the requested line/column and highlights the active line. It is
capability-gated: without the `code` CLI or a display it prints REVEAL_UNAVAILABLE
and exits 3 (so an eval marks the case BLOCKED, never a false PASS). On a
successful reveal it raises VS Code frontmost on the requested monitor/layout,
best-effort confirms via the window title, and prints REVEALED, else OPENED.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple


class Location(NamedTuple):
    line: int
    col: int
    end_line: int
    end_col: int


def resolve_python_symbol(source: str, *, function: str | None, klass: str | None, symbol: str | None) -> int | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    wanted_func = {n for n in (function, symbol) if n}
    wanted_class = {n for n in (klass, symbol) if n}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted_func:
            return node.lineno
        if isinstance(node, ast.ClassDef) and node.name in wanted_class:
            return node.lineno
    return None


def resolve_text_symbol(source: str, *, function: str | None, klass: str | None, symbol: str | None) -> int | None:
    patterns: list[re.Pattern[str]] = []
    for name in {n for n in (function, symbol) if n}:
        patterns.append(re.compile(rf"\b(?:def|function|fn)\s+{re.escape(name)}\b"))
    for name in {n for n in (klass, symbol) if n}:
        patterns.append(re.compile(rf"\bclass\s+{re.escape(name)}\b"))
    for index, line in enumerate(source.splitlines(), start=1):
        if any(p.search(line) for p in patterns):
            return index
    return None


def json_field_key(field: str) -> str:
    return field.split(".")[-1].replace("[]", "")


def resolve_json_field(source: str, field: str) -> Location | None:
    key = json_field_key(field)
    pattern = re.compile(rf'"{re.escape(key)}"\s*:')
    for index, row in enumerate(source.splitlines(), start=1):
        match = pattern.search(row)
        if match:
            return Location(index, match.start() + 1, index, match.start() + len(key) + 3)
    return None


def resolve_location(
    path: Path,
    *,
    line: int | None,
    function: str | None,
    klass: str | None,
    symbol: str | None,
    json_field: str | None,
) -> Location | None:
    if line is not None:
        return Location(line, 1, line, 1)
    source = path.read_text(encoding="utf-8", errors="replace")
    if json_field:
        return resolve_json_field(source, json_field)
    if path.suffix == ".py":
        found = resolve_python_symbol(source, function=function, klass=klass, symbol=symbol)
        if found is not None:
            return Location(found, 1, found, 1)
    found = resolve_text_symbol(source, function=function, klass=klass, symbol=symbol)
    return Location(found, 1, found, 1) if found is not None else None


def bridge_reveal(
    path: Path,
    location: Location,
    workspace: Path | None,
    wait_seconds: int,
    monitor: str,
    layout: str,
    place_window: bool,
    frontmost: bool,
) -> int:
    root = workspace or Path.cwd()
    request_script = Path(__file__).with_name("request_vscode_bridge.py")
    target_desktop = current_desktop() if (place_window or frontmost) else None
    if place_window or frontmost:
        adjust_vscode_window(
            path,
            root,
            monitor=monitor,
            layout=layout,
            place_window=place_window,
            frontmost=False,
            target_desktop=target_desktop,
        )
    reveal = f"{path}:{location.line}:{location.col}:{location.end_line}:{location.end_col}"
    proc = subprocess.run(
        [
            sys.executable,
            str(request_script),
            "--workspace",
            str(root),
            "--action",
            "reveal",
            "--reveal",
            reveal,
            "--expect-extension-host-kind",
            os.environ.get("DEBUGGER_VSCODE_HOST_KIND", "ui"),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if proc.returncode != 0:
        print(proc.stderr.strip() or proc.stdout.strip(), file=sys.stderr)
        return proc.returncode
    status_path = proc.stdout.strip().splitlines()[-1]
    status = "pending"
    data = {}
    for _ in range(max(wait_seconds, 1) * 2):
        try:
            import json

            data = json.loads(Path(status_path).read_text())
            status = str(data.get("status"))
            if status != "pending":
                break
        except Exception:
            pass
        time.sleep(0.5)
    if status == "revealed" and data.get("reveal", {}).get("selected") is True:
        suffix = adjust_vscode_window(
            path,
            root,
            monitor=monitor,
            layout=layout,
            place_window=place_window,
            frontmost=frontmost,
            target_desktop=target_desktop,
        )
        print(
            f"SELECTED {path.name}:{location.line}:{location.col}-{location.end_line}:{location.end_col} -- "
            f"VS Code API selection active; {suffix}"
        )
        return 0
    print(
        f"BRIDGE_BLOCKED reveal did not complete (status={status}; status_path={status_path})",
        file=sys.stderr,
    )
    return 3


def vscode_windows() -> list[tuple[str, str]]:
    wmctrl = shutil.which("wmctrl")
    if not wmctrl:
        return []
    try:
        out = subprocess.run([wmctrl, "-l"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    windows = []
    for row in out.splitlines():
        parts = row.split(None, 3)
        if len(parts) == 4 and "Visual Studio Code" in parts[3]:
            windows.append((parts[0], parts[3]))
    return windows


def window_title_has(basename: str) -> bool:
    return any(basename in title for _, title in vscode_windows())


def current_desktop() -> int | None:
    xdotool = shutil.which("xdotool")
    if not xdotool:
        return None
    try:
        out = subprocess.run([xdotool, "get_desktop"], capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def monitor_geometry(which: str, layout: str) -> tuple[int, int, int, int] | None:
    xrandr = shutil.which("xrandr")
    if not xrandr:
        return None
    try:
        out = subprocess.run([xrandr, "--listmonitors"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    monitors: list[tuple[int, int, int, int]] = []
    for row in out.splitlines():
        match = re.search(r"\s(\d+)/(?:\d+)x(\d+)/(?:\d+)\+(-?\d+)\+(-?\d+)\s", row)
        if match:
            width, height, x, y = map(int, match.groups())
            monitors.append((x, y, width, height))
    if not monitors:
        return None
    x, y, width, height = (max if which == "right" else min)(monitors, key=lambda item: item[0])
    if layout == "half-vertical":
        return x, y, width // 2, height
    return x, y, width // 2, height // 2


def adjust_vscode_window(
    path: Path,
    workspace: Path | None = None,
    *,
    monitor: str = "right",
    layout: str = "half-vertical",
    place_window: bool = False,
    frontmost: bool = False,
    target_desktop: int | None = None,
) -> str:
    if not place_window and not frontmost and target_desktop is None:
        return "window unchanged"
    wmctrl = shutil.which("wmctrl")
    if not wmctrl or not os.environ.get("DISPLAY"):
        return "window control not confirmed"
    workspace_name = workspace.name if workspace else None
    for window_id, title in vscode_windows():
        if path.name in title or (workspace_name and workspace_name in title):
            try:
                parts: list[str] = []
                if target_desktop is not None:
                    subprocess.run([wmctrl, "-ir", window_id, "-t", str(target_desktop)], check=True, capture_output=True, text=True, timeout=5)
                    parts.append(f"desktop {target_desktop}")
                if place_window:
                    box = monitor_geometry(monitor, layout)
                    if box:
                        x, y, width, height = box
                        subprocess.run([wmctrl, "-ir", window_id, "-b", "remove,maximized_vert,maximized_horz"], check=False, capture_output=True, text=True, timeout=5)
                        subprocess.run([wmctrl, "-ir", window_id, "-e", f"0,{x},{y},{width},{height}"], check=True, capture_output=True, text=True, timeout=5)
                        parts.append(f"geometry {x},{y} {width}x{height}")
                    else:
                        parts.append("geometry not confirmed")
                if frontmost:
                    subprocess.run([wmctrl, "-ia", window_id], check=True, capture_output=True, text=True, timeout=5)
                    parts.insert(0, "frontmost")
                return "; ".join(parts)
            except (OSError, subprocess.SubprocessError):
                return "window control not confirmed"
    return "window control not confirmed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--line", type=int)
    parser.add_argument("--function")
    parser.add_argument("--class", dest="klass")
    parser.add_argument("--symbol")
    parser.add_argument("--json-field", help="Reveal the first JSON object key matching this field name or dotted path.")
    parser.add_argument("--bridge", action="store_true", help="Use the VS Code bridge API for exact selected-range reveal.")
    parser.add_argument("--workspace", type=Path, help="Open trusted VS Code workspace for --bridge; defaults to cwd.")
    parser.add_argument("--wait-seconds", type=int, default=10, help="Seconds to wait for the bridge reveal status.")
    parser.add_argument("--monitor", choices=["left", "right"], default=os.environ.get("DEBUGGER_VSCODE_MONITOR", "right"), help="Monitor to use when --place-window is set.")
    parser.add_argument("--window-layout", choices=["quarter", "half-vertical"], default=os.environ.get("DEBUGGER_VSCODE_WINDOW_LAYOUT", "half-vertical"), help="Window size to use when --place-window is set.")
    parser.add_argument("--place-window", action="store_true", help="Move/resize VS Code. Default leaves the user's window geometry alone.")
    parser.add_argument("--frontmost", action="store_true", help="Activate VS Code after reveal. Default avoids stealing focus.")
    parser.add_argument("--print-only", action="store_true", help="Resolve and print the location; do not open anything.")
    args = parser.parse_args()

    path = args.file.resolve()
    if not path.is_file():
        print(f"NO_SUCH_FILE {path}", file=sys.stderr)
        return 1
    if not any((args.line, args.function, args.klass, args.symbol, args.json_field)):
        print("give one of --line/--function/--class/--symbol/--json-field", file=sys.stderr)
        return 2

    location = resolve_location(
        path,
        line=args.line,
        function=args.function,
        klass=args.klass,
        symbol=args.symbol,
        json_field=args.json_field,
    )
    if location is None:
        target = args.function or args.klass or args.symbol or args.json_field
        kind = "JSON_FIELD_NOT_FOUND" if args.json_field else "SYMBOL_NOT_FOUND"
        print(f"{kind} {target!r} in {path}", file=sys.stderr)
        return 1

    line, col, end_line, end_col = location
    label = args.function or args.klass or args.symbol or (f"json field {args.json_field}" if args.json_field else f"line {line}")
    if args.print_only:
        print(f"RESOLVED {path.name}:{line}:{col}-{end_line}:{end_col} ({label})")
        return 0

    if args.bridge:
        return bridge_reveal(
            path,
            location,
            args.workspace,
            args.wait_seconds,
            args.monitor,
            args.window_layout,
            args.place_window,
            args.frontmost,
        )

    code = shutil.which("code")
    if not code or not os.environ.get("DISPLAY"):
        print(f"RESOLVED {path.name}:{line} ({label})")
        print(
            f"REVEAL_UNAVAILABLE no `code` CLI or DISPLAY; cannot open the editor "
            f"(resolved {path}:{line}).",
            file=sys.stderr,
        )
        return 3

    try:
        subprocess.run([code, "--reuse-window", "--goto", f"{path}:{line}:{col}"], check=True, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"REVEAL_FAILED {exc}", file=sys.stderr)
        return 1

    confirmed = False
    for _ in range(6):
        if window_title_has(path.name):
            confirmed = True
            break
        time.sleep(0.5)
    suffix = adjust_vscode_window(
        path,
        args.workspace,
        monitor=args.monitor,
        layout=args.window_layout,
        place_window=args.place_window,
        frontmost=args.frontmost,
        target_desktop=current_desktop() if args.frontmost else None,
    )
    if confirmed:
        print(f"REVEALED {path.name}:{line}:{col}-{end_line}:{end_col} ({label}) -- editor showing {path.name}; {suffix}")
    else:
        print(f"OPENED {path.name}:{line}:{col}-{end_line}:{end_col} ({label}) -- goto issued (title unconfirmed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
