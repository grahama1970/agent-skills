#!/usr/bin/env python3
"""Walk a human through code with the live debugger, one narrated breakpoint at a time.

This is the `/debugger walkthrough` runtime. The agent authors a
`debugger.walkthrough.v1` spec -- an ordered list of stops, each naming a
file+line (or function/class), what to SAY there, and which locals to show --
and this drives the real VS Code debugger to each stop in turn: it reveals the
file in the human's editor, runs the program to the breakpoint, reads the live
paused state, and prints the narration alongside the observed values. Use it to
showcase finished work (`mode: review`) or to take the human straight to where
the agent is stuck (`mode: blocked`).

It reuses the same live bridge as scripts/vscode_bridge_session.py and is
capability-gated the same way: when no trusted VS Code bridge answers it prints
BRIDGE_BLOCKED and exits 3 (an eval marks the case BLOCKED, never a false PASS).

Workspace: --workspace PATH, else $DEBUGGER_VSCODE_WORKSPACE. The spec's file
paths are workspace-relative and the workspace must be open+trusted in VS Code
with the debugger-vscode-bridge extension active.

Output: a `── STOP i/N` block per stop with SAY and STATE lines, then
WALKTHROUGH-COMPLETE. With --transcript PATH it also writes a JSON transcript.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_NAME = "Debugger walkthrough ($debugger)"


def resolve_line(path: Path, *, line, function, klass) -> int | None:
    """Resolve a stop to a source line: explicit line, else a function/class def."""
    if line is not None:
        return int(line)
    source = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = None
        if tree is not None:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {function}:
                    return node.lineno
                if isinstance(node, ast.ClassDef) and node.name in {klass}:
                    return node.lineno
    patterns = []
    if function:
        patterns.append(re.compile(rf"\b(?:def|function|fn)\s+{re.escape(function)}\b"))
    if klass:
        patterns.append(re.compile(rf"\bclass\s+{re.escape(klass)}\b"))
    for index, text in enumerate(source.splitlines(), start=1):
        if any(p.search(text) for p in patterns):
            return index
    return None


def write_launch(workspace: Path, launch: dict, config_name: str) -> None:
    cmd = [
        "uv", "run", "--project", str(SKILL), "python",
        str(SKILL / "scripts" / "write_vscode_launch.py"),
        "--workspace", str(workspace), "--name", config_name,
        "--python", launch.get("python", "/usr/bin/python3"),
        "--module", launch["module"],
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def reveal(workspace: Path, file: str, line: int) -> None:
    """Best-effort: jump the human's editor to the stop before we run to it."""
    try:
        subprocess.run(
            ["uv", "run", "--project", str(SKILL), "python",
             str(SKILL / "scripts" / "open_in_vscode.py"), str(workspace / file), "--line", str(line)],
            check=False, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def issue_stop(workspace: Path, config_name: str, file: str, line: int, locals_: list[str], timeout_ms: int) -> str:
    cmd = [
        "uv", "run", "--project", str(SKILL), "python",
        str(SKILL / "scripts" / "request_vscode_bridge.py"),
        "--workspace", str(workspace), "--action", "restart",
        "--launch-config-name", config_name,
        "--break", f"{workspace / file}:{line}",
        "--stop-timeout-ms", str(timeout_ms),
        "--expect-extension-host-kind", os.environ.get("DEBUGGER_VSCODE_HOST_KIND", "ui"),
    ]
    for name in locals_:
        cmd += ["--local", name]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads((workspace / ".vscode" / "debugger-bridge" / "request.json").read_text())["output"]


def poll_status(workspace: Path, output: str, deadline: float, probe_seconds: float = 20.0) -> dict | None:
    nonterminal = {"pending", "no-file", "starting", "launching", "running", "continuing"}
    status_path = workspace / output
    try:
        initial_stamp = json.loads(status_path.read_text()).get("updatedAt")
    except (OSError, json.JSONDecodeError):
        initial_stamp = None
    engaged = False
    probe_deadline = time.time() + probe_seconds
    while time.time() < deadline:
        try:
            status = json.loads(status_path.read_text())
        except (OSError, json.JSONDecodeError):
            status = {"status": "no-file"}
        state = status.get("status")
        if state not in nonterminal:
            return status
        if not engaged and (status.get("updatedAt") != initial_stamp or state != "pending"):
            engaged = True
        if not engaged and time.time() > probe_deadline:
            return None
        time.sleep(1.0)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--transcript", type=Path, default=None)
    parser.add_argument("--wait-seconds", type=float, default=45.0)
    args = parser.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    if spec.get("schema") != "debugger.walkthrough.v1":
        print("spec is not a debugger.walkthrough.v1 object", file=sys.stderr)
        return 2
    workspace = Path(args.workspace or os.environ.get("DEBUGGER_VSCODE_WORKSPACE") or "").resolve()
    if not workspace.is_dir():
        print(f"workspace not found: {workspace} (set --workspace or DEBUGGER_VSCODE_WORKSPACE)", file=sys.stderr)
        return 2

    config_name = spec["launch"].get("config_name", DEFAULT_CONFIG_NAME)
    write_launch(workspace, spec["launch"], config_name)
    stops = spec["stops"]
    print(f"WALKTHROUGH mode={spec['mode']} stops={len(stops)} :: {spec['title']}")

    transcript: list[dict] = []
    for index, stop in enumerate(stops, start=1):
        path = workspace / stop["file"]
        line = resolve_line(path, line=stop.get("line"), function=stop.get("function"), klass=stop.get("class"))
        if line is None:
            print(f"STOP-UNRESOLVED {stop['file']} {stop.get('function') or stop.get('class')}", file=sys.stderr)
            return 1
        # The debugger stop auto-reveals the paused line in the editor, so the
        # human sees the code at each stop without a separate reveal call.
        # The first request after a window opens can find the bridge still
        # warming up; give it one retry before declaring the capability absent.
        attempts = 2 if index == 1 else 1
        status = None
        for attempt in range(attempts):
            output = issue_stop(workspace, config_name, stop["file"], line, stop.get("locals", []), int(args.wait_seconds * 1000))
            status = poll_status(workspace, output, time.time() + args.wait_seconds)
            if status is not None:
                break
            if attempt + 1 < attempts:
                time.sleep(3.0)
        if status is None:
            print(
                "BRIDGE_BLOCKED no live VS Code bridge processed the request "
                f"(workspace {workspace} open+trusted with the extension?).",
                file=sys.stderr,
            )
            return 3
        if status.get("status") not in ("stopped", "stopped-not-proof"):
            print(f"STOP-FAILED {index} status={status.get('status')!r}: {status.get('error') or ''}", file=sys.stderr)
            return 1
        stopped = status.get("stoppedState", {}) or {}
        frame = stopped.get("frame", {}) or {}
        locals_map = stopped.get("locals", {}) or {}
        state_str = ", ".join(f"{k}={v}" for k, v in locals_map.items()) or "(no locals requested)"
        print(f"\n── STOP {index}/{len(stops)} · {stop['file']}:{frame.get('line')} in {frame.get('name')!r} ──")
        print(f"SAY: {stop['say']}")
        print(f"STATE: {state_str}")
        for name, want in (stop.get("expect") or {}).items():
            got = locals_map.get(name)
            if got != want:
                print(f"EXPECT-FAILED {name}={got!r} != {want!r}", file=sys.stderr)
                return 1
        transcript.append({
            "index": index,
            "file": stop["file"],
            "line": frame.get("line"),
            "function": frame.get("name"),
            "say": stop["say"],
            "locals": locals_map,
            "sessionId": stopped.get("sessionId"),
        })

    print(f"\nWALKTHROUGH-COMPLETE mode={spec['mode']} stops={len(stops)}")
    if args.transcript:
        args.transcript.write_text(
            json.dumps({"schema": "debugger.walkthrough_transcript.v1", "title": spec["title"],
                        "mode": spec["mode"], "stops": transcript}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"TRANSCRIPT {args.transcript}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
