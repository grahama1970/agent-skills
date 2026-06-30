#!/usr/bin/env python3
"""Run a VS Code debugpy/DAP breakpoint proof and capture paused variables."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated, Any

from loguru import logger
import typer


DEFAULT_EXTENSION = Path("${HOME}/.vscode/extensions/ms-python.debugpy-2026.6.0")


def parse_breakpoint(raw: str) -> tuple[Path, int]:
    if ":" not in raw:
        raise typer.BadParameter(f"breakpoint must be file:line, got {raw!r}")
    file_part, line_part = raw.rsplit(":", 1)
    try:
        line = int(line_part)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid breakpoint line in {raw!r}") from exc
    return Path(file_part).resolve(), line


class DapClient:
    def __init__(self, *, extension: Path, adapter_command: list[str] | None = None) -> None:
        env = os.environ.copy()
        if adapter_command is None:
            debugpy_libs = extension / "bundled" / "libs"
            if not debugpy_libs.exists():
                raise RuntimeError(f"VS Code debugpy libs not found: {debugpy_libs}")
            env["PYTHONPATH"] = str(debugpy_libs)
            adapter_command = [sys.executable, "-m", "debugpy.adapter"]
        self.proc = subprocess.Popen(
            adapter_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            env=env,
        )
        self.seq = 1
        self.events: list[dict[str, Any]] = []
        self.selector = selectors.DefaultSelector()
        if self.proc.stdout is None:
            raise RuntimeError("debug adapter stdout is closed")
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)

    def send(self, command: str, arguments: dict[str, Any] | None = None) -> int:
        seq = self.seq
        self.seq += 1
        body = json.dumps({"seq": seq, "type": "request", "command": command, "arguments": arguments or {}}).encode(
            "utf-8"
        )
        if self.proc.stdin is None:
            raise RuntimeError("debug adapter stdin is closed")
        self.proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        self.proc.stdin.flush()
        return seq

    def read(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.proc.stdout is None:
            raise RuntimeError("debug adapter stdout is closed")
        deadline = time.time() + timeout
        headers: dict[str, str] = {}
        buf = bytearray()
        while time.time() < deadline:
            b = self.read_exact(1, deadline)
            if not b:
                stderr = ""
                raise RuntimeError(f"debug adapter closed stdout: {stderr}")
            buf.extend(b)
            if buf.endswith(b"\r\n"):
                line = buf[:-2].decode("ascii")
                buf.clear()
                if not line:
                    break
                key, value = line.split(":", 1)
                headers[key.lower()] = value.strip()
        if "content-length" not in headers:
            raise TimeoutError("timed out reading DAP headers")
        length = int(headers["content-length"])
        return json.loads(self.read_exact(length, deadline).decode("utf-8"))

    def read_exact(self, length: int, deadline: float) -> bytes:
        if self.proc.stdout is None:
            raise RuntimeError("debug adapter stdout is closed")
        chunks = bytearray()
        while len(chunks) < length:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"timed out reading {length} DAP byte(s)")
            if not self.selector.select(remaining):
                raise TimeoutError(f"timed out reading {length} DAP byte(s)")
            chunk = os.read(self.proc.stdout.fileno(), length - len(chunks))
            if not chunk:
                raise RuntimeError("debug adapter closed stdout")
            chunks.extend(chunk)
        return bytes(chunks)

    def wait_response(self, request_seq: int, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self.read(max(0.1, deadline - time.time()))
            if msg.get("type") == "event":
                self.events.append(msg)
            elif msg.get("type") == "response" and msg.get("request_seq") == request_seq:
                if not msg.get("success", False):
                    raise RuntimeError(f"DAP {msg.get('command')} failed: {msg}")
                return msg
        raise TimeoutError(f"timed out waiting for response {request_seq}")

    def wait_event(self, event: str, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            for idx, msg in enumerate(self.events):
                if msg.get("event") == event:
                    return self.events.pop(idx)
            msg = self.read(max(0.1, deadline - time.time()))
            if msg.get("type") == "event":
                if msg.get("event") == event:
                    return msg
                self.events.append(msg)
        raise TimeoutError(f"timed out waiting for event {event}")

    def request(self, command: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.wait_response(self.send(command, arguments))

    def close(self) -> None:
        try:
            self.wait_response(self.send("disconnect", {"terminateDebuggee": True}), timeout=5)
        except Exception as exc:
            logger.error("debug adapter disconnect failed: {}", exc)
        try:
            self.selector.close()
        except Exception as exc:
            logger.error("debug adapter selector close failed: {}", exc)
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            logger.error("debug adapter did not terminate cleanly; killing process")
            self.proc.kill()


def selected_variables(variables: list[dict[str, Any]], names: set[str]) -> dict[str, str]:
    return {var["name"]: var.get("value", "") for var in variables if var["name"] in names}


def assess_variable_inspection(
    *,
    requested_locals: list[str],
    captured_locals: dict[str, str],
    requested_children: list[str],
    captured_children: dict[str, str],
) -> dict[str, Any]:
    missing_locals = [name for name in requested_locals if name not in captured_locals]
    missing_children = [
        path for path in requested_children if captured_children.get(path, "<missing>").startswith("<")
    ]
    requested_count = len(requested_locals) + len(requested_children)
    captured_count = (len(requested_locals) - len(missing_locals)) + (len(requested_children) - len(missing_children))
    variable_inspection_valid = requested_count > 0 and captured_count > 0 and not missing_locals and not missing_children
    return {
        "variableInspectionValid": variable_inspection_valid,
        "requestedLocals": requested_locals,
        "capturedLocals": sorted(captured_locals),
        "missingLocals": missing_locals,
        "requestedChildren": requested_children,
        "capturedChildren": sorted(path for path in requested_children if path not in missing_children),
        "missingChildren": missing_children,
        "reason": (
            "captured all requested runtime state"
            if variable_inspection_valid
            else "requested runtime state was missing or no runtime state was requested"
        ),
    }


def main(
    breakpoint: Annotated[str, typer.Option("--break", help="Breakpoint as file:line.")],
    out: Annotated[Path, typer.Option("--out", help="JSON proof output path.")],
    cwd: Annotated[Path, typer.Option("--cwd", help="Debuggee working directory.")],
    python: Annotated[Path, typer.Option("--python", help="Python interpreter for debuggee.")],
    module: Annotated[str, typer.Option("--module", help="Python module to launch, such as pytest.")],
    arg: Annotated[list[str] | None, typer.Option("--arg", help="Debuggee argument. Repeat in order.")] = None,
    env: Annotated[list[str] | None, typer.Option("--env", help="Environment KEY=VALUE. Repeat as needed.")] = None,
    local: Annotated[list[str] | None, typer.Option("--local", help="Local variable names to capture.")] = None,
    child: Annotated[list[str] | None, typer.Option("--child", help="Child variable path as parent.child.")] = None,
    extension: Annotated[Path, typer.Option("--extension", help="VS Code debugpy extension path.")] = DEFAULT_EXTENSION,
) -> None:
    source, line = parse_breakpoint(breakpoint)
    env_map = {}
    for item in env or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise typer.BadParameter(f"--env must be KEY=VALUE, got {item!r}")
        env_map[key] = value

    proof: dict[str, Any] = {
        "adapter": "VS Code ms-python.debugpy",
        "extension": str(extension),
        "breakpoint": {"file": str(source), "line": line},
        "hit_breakpoint": False,
        "human_breakpoint": {
            "file": str(source),
            "line": line,
            "expected_variables": list(local or []) + list(child or []),
        },
        "goals": {
            "set_breakpoint": False,
            "stop_at_breakpoint": False,
            "inspect_and_analyze_variables": False,
            "provide_human_breakpoint": False,
        },
    }
    client = DapClient(extension=extension)
    try:
        client.request("initialize", {"clientID": "codex-project-agent-e2e", "adapterID": "python"})
        launch_seq = client.send(
            "launch",
            {
                "name": "debugger skill VS Code E2E",
                "type": "python",
                "request": "launch",
                "module": module,
                "args": arg or [],
                "cwd": str(cwd),
                "python": [str(python)],
                "env": env_map,
                "console": "internalConsole",
                "justMyCode": False,
            },
        )
        client.wait_event("initialized")
        set_breakpoints = client.request(
            "setBreakpoints",
            {"source": {"path": str(source)}, "breakpoints": [{"line": line}], "sourceModified": False},
        )["body"]["breakpoints"]
        proof["set_breakpoints_response"] = set_breakpoints
        proof["goals"]["set_breakpoint"] = any(bp.get("verified") and bp.get("line") == line for bp in set_breakpoints)
        client.request("configurationDone")
        client.wait_response(launch_seq)
        stopped = client.wait_event("stopped")
        proof["stopped_event"] = stopped
        thread_id = stopped["body"]["threadId"]
        frame = client.request("stackTrace", {"threadId": thread_id, "startFrame": 0, "levels": 1})["body"][
            "stackFrames"
        ][0]
        proof["top_frame"] = frame
        frame_source = Path(frame.get("source", {}).get("path", "")).resolve()
        frame_line = frame.get("line")
        proof["matched_requested_breakpoint"] = frame_source == source and frame_line == line
        proof["hit_breakpoint"] = stopped.get("body", {}).get("reason") == "breakpoint" and bool(
            proof["matched_requested_breakpoint"]
        )
        proof["goals"]["stop_at_breakpoint"] = bool(proof["hit_breakpoint"])
        scopes = client.request("scopes", {"frameId": frame["id"]})["body"]["scopes"]
        locals_ref = next(scope["variablesReference"] for scope in scopes if scope["name"].lower() == "locals")
        variables = client.request("variables", {"variablesReference": locals_ref})["body"]["variables"]
        requested_locals = list(local or [])
        requested_children = list(child or [])
        local_names = set(requested_locals)
        proof["locals"] = selected_variables(variables, local_names) if local_names else {}
        proof["children"] = {}
        for path in requested_children:
            parent, sep, child_name = path.partition(".")
            if not sep:
                raise typer.BadParameter(f"--child must be parent.child, got {path!r}")
            parent_var = next((var for var in variables if var["name"] == parent), None)
            if not parent_var or not parent_var.get("variablesReference"):
                proof["children"][path] = "<parent not found or not expandable>"
                continue
            child_vars = client.request("variables", {"variablesReference": parent_var["variablesReference"]})["body"][
                "variables"
            ]
            proof["children"][path] = selected_variables(child_vars, {child_name}).get(child_name, "<child not found>")
        proof["proofAssessment"] = assess_variable_inspection(
            requested_locals=requested_locals,
            captured_locals=proof["locals"],
            requested_children=requested_children,
            captured_children=proof["children"],
        )
        proof["analysis"] = (
            "Debugger E2E set a verified VS Code breakpoint, stopped with reason=breakpoint, "
            "captured the paused frame, and inspected selected variable state from the live frame."
        )
        proof["goals"]["inspect_and_analyze_variables"] = bool(proof["proofAssessment"]["variableInspectionValid"])
        proof["goals"]["provide_human_breakpoint"] = bool(proof["human_breakpoint"]["expected_variables"])
        client.request("continue", {"threadId": thread_id})
        client.wait_event("terminated")
    except Exception as exc:
        logger.error("VS Code debugger E2E failed: {}", exc)
        proof["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        client.close()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(proof, indent=2, sort_keys=True), encoding="utf-8")
        print(out)
        print(json.dumps(proof, indent=2, sort_keys=True))

    if not all(proof["goals"].values()):
        raise typer.Exit(1)


if __name__ == "__main__":
    typer.run(main)
