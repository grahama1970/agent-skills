#!/usr/bin/env python3
"""Reveal a file in the running VS Code at a line, function, or class.

This is the debugger's lightweight collaboration surface, separate from starting
a debug session: when the agent is stuck on a spot -- or the human wants to look
-- this jumps the human's editor straight to the code in question. The human can
then eyeball it and, if they want, ask the agent to start a debug session there
(scripts/vscode_bridge_session.py) and discuss the paused state.

Locating the code:
    --line N          go to line N
    --function NAME   first `def NAME` / `function NAME` / `fn NAME`
    --class NAME      first `class NAME`
    --symbol NAME     a function OR class named NAME

For Python files symbols are resolved with the ast (robust to formatting); for
other languages a line-based scan handles def/function/fn/class. `--print-only`
resolves and prints the location without opening anything (deterministic, needs
no display).

Reveal uses `code --reuse-window --goto <file>:<line>:1`. It is capability-gated:
without the `code` CLI or a display it prints REVEAL_UNAVAILABLE and exits 3
(so an eval marks the case BLOCKED, never a false PASS). On a successful reveal
it best-effort confirms via the window title and prints REVEALED, else OPENED.
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


def resolve_line(path: Path, *, line: int | None, function: str | None, klass: str | None, symbol: str | None) -> int | None:
    if line is not None:
        return line
    source = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        found = resolve_python_symbol(source, function=function, klass=klass, symbol=symbol)
        if found is not None:
            return found
    return resolve_text_symbol(source, function=function, klass=klass, symbol=symbol)


def window_title_has(basename: str) -> bool:
    wmctrl = shutil.which("wmctrl")
    if not wmctrl:
        return False
    try:
        out = subprocess.run([wmctrl, "-l"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(basename in row for row in out.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--line", type=int)
    parser.add_argument("--function")
    parser.add_argument("--class", dest="klass")
    parser.add_argument("--symbol")
    parser.add_argument("--print-only", action="store_true", help="Resolve and print the location; do not open anything.")
    args = parser.parse_args()

    path = args.file.resolve()
    if not path.is_file():
        print(f"NO_SUCH_FILE {path}", file=sys.stderr)
        return 1
    if not any((args.line, args.function, args.klass, args.symbol)):
        print("give one of --line/--function/--class/--symbol", file=sys.stderr)
        return 2

    line = resolve_line(path, line=args.line, function=args.function, klass=args.klass, symbol=args.symbol)
    if line is None:
        target = args.function or args.klass or args.symbol
        print(f"SYMBOL_NOT_FOUND {target!r} in {path}", file=sys.stderr)
        return 1

    label = args.function or args.klass or args.symbol or f"line {line}"
    if args.print_only:
        print(f"RESOLVED {path.name}:{line} ({label})")
        return 0

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
        subprocess.run([code, "--reuse-window", "--goto", f"{path}:{line}:1"], check=True, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"REVEAL_FAILED {exc}", file=sys.stderr)
        return 1

    confirmed = False
    for _ in range(6):
        if window_title_has(path.name):
            confirmed = True
            break
        time.sleep(0.5)
    if confirmed:
        print(f"REVEALED {path.name}:{line} ({label}) -- editor showing {path.name}")
    else:
        print(f"OPENED {path.name}:{line} ({label}) -- goto issued (title unconfirmed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
