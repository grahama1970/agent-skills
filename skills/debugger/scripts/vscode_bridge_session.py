#!/usr/bin/env python3
"""Drive a live VS Code debug session through the bridge and read paused state.

This is the agent side of the agent-human collaboration the debugger skill
exists for: set a breakpoint at a bug, let VS Code run the real program to it,
read the paused frame, describe what is wrong from that state, then move to the
next breakpoint -- all against the visible VS Code the human is looking at.

It is capability-gated on purpose. A live run needs a VS Code window with the
`agent-skills.debugger-vscode-bridge` extension active on a TRUSTED workspace
folder that contains the target module. When that capability is absent (no such
window, or the folder is untrusted / not open), the bridge never processes the
request and this prints ``BRIDGE_BLOCKED`` and exits 3 -- so an eval marks the
case BLOCKED, never PASS and never a false FAIL. This mirrors the capability
model in #1441: a missing capability is BLOCKED, not a pass.

Workspace selection:
    --workspace PATH        drive this folder (must be open+trusted in VS Code)
    else $DEBUGGER_VSCODE_WORKSPACE
    else a fresh temp copy of scenarios/variable_state (which will be BLOCKED
    unless a human opens+trusts it and re-points the driver at it).

Each visited breakpoint prints a `PAUSE` line with the file/line/function and
the captured locals, and an `EXPLAIN` line stating the bug the paused state
reveals. On success it prints `SESSION-OK visited=<n>` and exits 0.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCENARIO = SKILL / "scenarios" / "variable_state"
CONFIG_NAME = "Debug variable_state leak ($debugger)"

# The collaboration script: visit the bug's symptom, then its root cause.
# Each step names the local to read and the assertion that the paused state
# actually exposes the bug, plus the human-readable explanation to emit.
STEPS = [
    {
        "file": "main.py",
        "line": 21,
        "locals": ["first", "second"],
        "assert_local": "second",
        "assert_value": "36",
        "explain": (
            "second=36 but the inputs [10, 20] should total 30. The aggregate is "
            "polluted -- report two carries values from report one."
        ),
    },
    {
        "file": "tally.py",
        "line": 12,
        "locals": ["seen", "value"],
        "assert_local": "seen",
        "explain": (
            "seen is a mutable DEFAULT argument, created once and shared by every "
            "call, so running_total accumulates across unrelated callers. That is "
            "the root cause of the polluted total."
        ),
    },
]


def prepare_workspace(explicit: str | None) -> tuple[Path, bool]:
    """Return (workspace, is_temp). Copies the target module when making a temp."""
    chosen = explicit or os.environ.get("DEBUGGER_VSCODE_WORKSPACE")
    if chosen:
        return Path(chosen).resolve(), False
    tmp = Path(tempfile.mkdtemp(prefix="dbg-vscode-session-"))
    for name in ("tally.py", "report.py", "main.py"):
        shutil.copy(SCENARIO / name, tmp / name)
    return tmp, True


def write_launch(workspace: Path) -> None:
    subprocess.run(
        [
            "uv", "run", "--project", str(SKILL), "python",
            str(SKILL / "scripts" / "write_vscode_launch.py"),
            "--workspace", str(workspace), "--name", CONFIG_NAME,
            "--python", "/usr/bin/python3", "--module", "main",
        ],
        check=True, capture_output=True, text=True,
    )


def issue_request(workspace: Path, step: dict, timeout_ms: int) -> tuple[str, str]:
    cmd = [
        "uv", "run", "--project", str(SKILL), "python",
        str(SKILL / "scripts" / "request_vscode_bridge.py"),
        "--workspace", str(workspace), "--action", "restart",
        "--launch-config-name", CONFIG_NAME,
        "--break", f"{workspace / step['file']}:{step['line']}",
        "--stop-timeout-ms", str(timeout_ms),
    ]
    for local in step["locals"]:
        cmd += ["--local", local]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    request = json.loads((workspace / ".vscode" / "debugger-bridge" / "request.json").read_text())
    return request["output"], request["id"]


def poll_status(workspace: Path, output: str, deadline: float, probe_seconds: float = 12.0) -> dict | None:
    """Poll until terminal, or None when the bridge never engages.

    The requester writes the initial `pending` status; a live extension rewrites
    it (its `updatedAt` changes) the moment it starts processing. If nothing
    touches the file within `probe_seconds`, no live bridge is watching this
    workspace -- fail fast as BLOCKED rather than burning the whole deadline.
    Once the extension has engaged, wait the full deadline for the stop.
    """
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
        if status.get("status") not in ("pending", "no-file"):
            return status
        if not engaged and status.get("updatedAt") != initial_stamp:
            engaged = True
        if not engaged and time.time() > probe_deadline:
            return None
        time.sleep(1.0)
    return None


def visit(workspace: Path, step: dict, wait_s: float) -> tuple[bool, str, str]:
    """Return (ok, sessionId, message) for one breakpoint visit."""
    timeout_ms = int(wait_s * 1000)
    output, _ = issue_request(workspace, step, timeout_ms)
    status = poll_status(workspace, output, time.time() + wait_s)
    if status is None:
        return False, "", "BRIDGE_BLOCKED"
    if status.get("status") not in ("stopped", "stopped-not-proof"):
        return False, "", f"UNEXPECTED status={status.get('status')!r}: {status.get('error') or ''}"
    stopped = status.get("stoppedState", {}) or {}
    frame = stopped.get("frame", {}) or {}
    locals_map = stopped.get("locals", {}) or {}
    session_id = str(stopped.get("sessionId", ""))
    src = (frame.get("source", {}) or {}).get("path", "")
    if Path(str(src)).name != step["file"]:
        return False, session_id, f"frame file {src!r} != expected {step['file']}"
    got = locals_map.get(step["assert_local"])
    if got is None:
        return False, session_id, f"local {step['assert_local']!r} not captured; locals={locals_map}"
    if "assert_value" in step and got != step["assert_value"]:
        return False, session_id, f"{step['assert_local']}={got!r} != expected {step['assert_value']!r}"
    print(f"PAUSE {step['file']}:{frame.get('line')} in {frame.get('name')!r} locals={locals_map}")
    print(f"EXPLAIN {step['explain']}")
    return True, session_id, "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--wait-seconds", type=float, default=45.0)
    args = parser.parse_args()

    workspace, is_temp = prepare_workspace(args.workspace)
    try:
        write_launch(workspace)
        sessions: list[str] = []
        for index, step in enumerate(STEPS):
            ok, session_id, message = visit(workspace, step, args.wait_seconds)
            if not ok:
                if message == "BRIDGE_BLOCKED":
                    print(
                        "BRIDGE_BLOCKED no live VS Code bridge processed the request "
                        f"(workspace {workspace} open+trusted with the extension?). "
                        "Open+trust the folder and set DEBUGGER_VSCODE_WORKSPACE to run live.",
                        file=sys.stderr,
                    )
                    return 3
                print(f"VISIT-FAILED step={index} {message}", file=sys.stderr)
                return 1
            sessions.append(session_id)
        print(f"SESSION-OK visited={len(STEPS)} sessions={sessions}")
        return 0
    finally:
        if is_temp:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
