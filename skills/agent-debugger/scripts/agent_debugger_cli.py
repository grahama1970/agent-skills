#!/usr/bin/env python3
"""Agent Debugger CLI.

Python-first debugger workflow:
- init-python creates a harness, manifest, and VS Code launch config.
- run-headless uses debugpy's DAP adapter directly and writes observations.
"""

from __future__ import annotations

import json
import re
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer

APP = typer.Typer(add_completion=False, help="Agent debugger for Python targets.")


@dataclass(frozen=True)
class BreakpointSpec:
    file: str
    line: int
    expressions: List[str]
    reason: str


class DapClient:
    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.timeout = timeout
        self.seq = 1
        self.responses: Dict[int, Dict[str, Any]] = {}

    def close(self) -> None:
        self.sock.close()

    def request(self, command: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        seq = self.seq
        self.seq += 1
        msg: Dict[str, Any] = {"seq": seq, "type": "request", "command": command}
        if arguments is not None:
            msg["arguments"] = arguments
        self._send(msg)
        return self.wait_response(seq)

    def wait_response(self, request_seq: int) -> Dict[str, Any]:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if request_seq in self.responses:
                return self.responses.pop(request_seq)
            msg = self.read_message()
            if msg.get("type") == "response":
                self.responses[int(msg["request_seq"])] = msg
        raise TimeoutError(f"Timed out waiting for DAP response {request_seq}")

    def wait_event(self, event: str) -> Dict[str, Any]:
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            msg = self.read_message()
            if msg.get("type") == "response":
                self.responses[int(msg["request_seq"])] = msg
                continue
            if msg.get("type") == "event" and msg.get("event") == event:
                return msg
        raise TimeoutError(f"Timed out waiting for DAP event {event}")

    def read_message(self) -> Dict[str, Any]:
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self.sock.recv(1)
            if not chunk:
                raise EOFError("debug adapter closed while reading header")
            header += chunk
        length = None
        for line in header.decode("ascii", errors="replace").split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
                break
        if length is None:
            raise ValueError("DAP message missing Content-Length")
        body = b""
        while len(body) < length:
            chunk = self.sock.recv(length - len(body))
            if not chunk:
                raise EOFError("debug adapter closed while reading body")
            body += chunk
        return json.loads(body.decode("utf-8"))

    def _send(self, msg: Dict[str, Any]) -> None:
        body = json.dumps(msg, separators=(",", ":")).encode("utf-8")
        self.sock.sendall(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._") or "debug-task"


def _json_list(raw: str, field: str) -> List[str]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{field} must be a JSON string list: {exc}") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise typer.BadParameter(f"{field} must be a JSON string list")
    return list(value)


def _parse_breakpoint(raw: str) -> BreakpointSpec:
    parts = raw.split(":", 2)
    if len(parts) < 2:
        raise typer.BadParameter("breakpoint must be file:line or file:line:expr,expr")
    line = int(parts[1])
    expressions = [item.strip() for item in parts[2].split(",") if item.strip()] if len(parts) == 3 else []
    return BreakpointSpec(parts[0], line, expressions, f"Inspect runtime state at {parts[0]}:{line}")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _inside(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    if path != root.resolve() and root.resolve() not in path.parents:
        raise typer.BadParameter(f"path escapes workspace: {rel}")
    return path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _connect(port: int, timeout: float) -> DapClient:
    deadline = time.time() + timeout
    last: Optional[BaseException] = None
    while time.time() < deadline:
        try:
            return DapClient("127.0.0.1", port, timeout)
        except OSError as exc:
            last = exc
            time.sleep(0.05)
    raise TimeoutError(f"could not connect to debugpy adapter: {last}")


def _load_launch(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": "0.2.0", "configurations": []}
    return json.loads(path.read_text(encoding="utf-8"))


@APP.command("init-python")
def init_python(
    task: str = typer.Option(..., "--task"),
    target: Path = typer.Option(..., "--target"),
    target_args_json: str = typer.Option("[]", "--target-args-json"),
    breakpoints_json: str = typer.Option("[]", "--breakpoints-json"),
    root: Path = typer.Option(Path("."), "--root"),
    plan_root: str = typer.Option(".plan-iterate", "--plan-root"),
    launch_name: Optional[str] = typer.Option(None, "--launch-name"),
) -> None:
    workspace = root.resolve()
    target_rel = target.as_posix()
    target_path = _inside(workspace, target_rel)
    if not target_path.exists() or target_path.suffix != ".py":
        raise typer.BadParameter(f"v1 target must be an existing .py file: {target_rel}")

    task_slug = _slug(task)
    target_args = _json_list(target_args_json, "target_args_json")
    bp_specs = [_parse_breakpoint(item) for item in _json_list(breakpoints_json, "breakpoints_json")]
    debug_dir = workspace / plan_root / task_slug / "debug"
    harness_path = debug_dir / f"harness_{task_slug.replace('-', '_').replace('.', '_')}.py"
    launch_config_name = launch_name or f"Agent Debugger: {task_slug}"

    harness = f'''#!/usr/bin/env python3
from __future__ import annotations
import os
import runpy
import sys
from pathlib import Path
WORKSPACE = Path(__file__).resolve().parents[3]
os.chdir(WORKSPACE)
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))
sys.argv = {repr([target_rel, *target_args])}
runpy.run_path(str(WORKSPACE / {target_rel!r}), run_name="__main__")
'''
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(harness, encoding="utf-8")
    harness_path.chmod(0o755)

    commands_path = debug_dir / "debug_commands.jsonl"
    observations_path = debug_dir / "debug_observations.jsonl"
    state_path = debug_dir / "debug_session_state.json"
    manifest_path = debug_dir / "debug_manifest.json"
    for path in (commands_path, observations_path):
        path.write_text("", encoding="utf-8")
    _write_json(state_path, {"schema": "agent_debugger_session_state.v1", "status": "not_started", "updated_at": datetime.now(timezone.utc).isoformat()})

    manifest = {
        "schema": "agent_debugger_manifest.v1",
        "version": 1,
        "language": "python",
        "task": task_slug,
        "launch_config_name": launch_config_name,
        "harness": _relative(harness_path, workspace),
        "target": target_rel,
        "target_args": target_args,
        "breakpoints": [{"file": bp.file, "line": bp.line, "reason": bp.reason, "expressions": bp.expressions, "stop": True, "source": "agent"} for bp in bp_specs],
        "commands_path": _relative(commands_path, workspace),
        "observations_path": _relative(observations_path, workspace),
        "session_state_path": _relative(state_path, workspace),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lifecycle": {"replay_semantics": "stop_and_restart_same_launch_config", "managed_session_only": True},
    }
    _write_json(manifest_path, manifest)

    vscode_dir = workspace / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    launch_path = vscode_dir / "launch.json"
    launch = _load_launch(launch_path)
    launch.setdefault("version", "0.2.0")
    launch.setdefault("configurations", [])
    launch["configurations"] = [item for item in launch["configurations"] if item.get("name") != launch_config_name]
    launch["configurations"].append({"name": launch_config_name, "type": "debugpy", "request": "launch", "program": "${workspaceFolder}/" + _relative(harness_path, workspace), "cwd": "${workspaceFolder}", "console": "integratedTerminal", "justMyCode": False})
    _write_json(launch_path, launch)

    (debug_dir / "notes.md").write_text("# Agent Debugger Session\n\n" f"Task: `{task_slug}`\n\n" f"Target: `{target_rel} {shlex.join(target_args)}`\n", encoding="utf-8")
    typer.echo(json.dumps({"status": "created", "manifest": _relative(manifest_path, workspace), "harness": _relative(harness_path, workspace), "breakpoint_count": len(bp_specs)}, indent=2, sort_keys=True))


@APP.command("run-headless")
def run_headless(
    manifest: Path = typer.Option(..., "--manifest"),
    root: Path = typer.Option(Path("."), "--root"),
    timeout: float = typer.Option(20.0, "--timeout"),
) -> None:
    workspace = root.resolve()
    manifest_path = manifest if manifest.is_absolute() else workspace / manifest
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema") != "agent_debugger_manifest.v1" or data.get("language") != "python":
        raise typer.BadParameter("run-headless supports agent_debugger_manifest.v1 Python manifests only")

    harness_path = _inside(workspace, data["harness"])
    observations_path = _inside(workspace, data["observations_path"])
    state_path = _inside(workspace, data["session_state_path"])
    observations_path.write_text("", encoding="utf-8")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "debugpy.adapter", "--host", "127.0.0.1", "--port", str(port)], cwd=str(workspace), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    client: Optional[DapClient] = None
    try:
        client = _connect(port, timeout)
        client.request("initialize", {"adapterID": "debugpy", "pathFormat": "path", "linesStartAt1": True, "columnsStartAt1": True})
        client.request("launch", {"program": str(harness_path), "cwd": str(workspace), "console": "internalConsole", "justMyCode": False, "subProcess": False})
        client.wait_event("initialized")
        by_file: Dict[str, List[Dict[str, Any]]] = {}
        for bp in data.get("breakpoints", []):
            by_file.setdefault(bp["file"], []).append(bp)
        for rel_file, bps in by_file.items():
            client.request("setBreakpoints", {"source": {"path": str(_inside(workspace, rel_file))}, "breakpoints": [{"line": int(bp["line"])} for bp in bps]})
        client.request("configurationDone", {})
        _write_json(state_path, {"schema": "agent_debugger_session_state.v1", "status": "running", "updated_at": datetime.now(timezone.utc).isoformat()})
        hits = 0
        expected_hits = max(1, len(data.get("breakpoints", [])))
        while hits < expected_hits:
            event = client.wait_event("stopped")
            thread_id = int(event.get("body", {}).get("threadId", 1))
            trace = client.request("stackTrace", {"threadId": thread_id, "startFrame": 0, "levels": 1})
            frame = trace.get("body", {}).get("stackFrames", [])[0]
            frame_id = int(frame["id"])
            source_path = Path(frame.get("source", {}).get("path", "")).resolve()
            try:
                rel_source = source_path.relative_to(workspace).as_posix()
            except ValueError:
                rel_source = str(source_path)
            line = int(frame.get("line", 0))
            match = next((bp for bp in data.get("breakpoints", []) if bp.get("file") == rel_source and int(bp.get("line", -1)) == line), None)
            evaluated: Dict[str, Any] = {}
            for expr in (match or {}).get("expressions", []):
                evaluated[expr] = client.request("evaluate", {"expression": expr, "frameId": frame_id, "context": "watch"}).get("body", {}).get("result")
            _append_jsonl(observations_path, {"schema": "agent_debugger_observation.v1", "ts": datetime.now(timezone.utc).isoformat(), "type": "breakpoint_hit", "source": "debugpy", "task": data.get("task"), "data": {"file": rel_source, "line": line, "name": frame.get("name"), "expressions": evaluated, "reason": (match or {}).get("reason")}})
            hits += 1
            client.request("continue", {"threadId": thread_id})
        _write_json(state_path, {"schema": "agent_debugger_session_state.v1", "status": "completed", "updated_at": datetime.now(timezone.utc).isoformat(), "breakpoint_hits": hits})
        typer.echo(json.dumps({"status": "completed", "breakpoint_hits": hits, "observations": _relative(observations_path, workspace)}, indent=2, sort_keys=True))
    finally:
        if client:
            client.close()
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    APP()
