#!/usr/bin/env python3
"""Write a request for the Debugger VS Code Bridge extension."""

from __future__ import annotations

import json
import hashlib
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import typer


def parse_breakpoint(raw: str) -> dict[str, int | str]:
    file_part, sep, line_part = raw.rpartition(":")
    if not sep:
        raise typer.BadParameter(f"--break must be file:line, got {raw!r}")
    try:
        line = int(line_part)
    except ValueError as exc:
        raise typer.BadParameter(f"invalid breakpoint line in {raw!r}") from exc
    return {"file": file_part, "line": line}


def canonical_request_hash(request: dict[str, object]) -> str:
    payload = {key: value for key, value in request.items() if key != "requestHash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def safe_file_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "_.-" else "_" for char in value)


def default_expected_remote_name() -> str | None:
    explicit = os.environ.get("VSCODE_REMOTE_NAME")
    if explicit:
        return explicit
    if os.environ.get("SSH_CONNECTION") and os.environ.get("VSCODE_IPC_HOOK_CLI"):
        return "ssh-remote"
    return None


def main(
    workspace: Annotated[Path, typer.Option("--workspace", help="Open VS Code workspace folder.")] = Path.cwd(),
    action: Annotated[
        Literal[
            "start",
            "restart",
            "process",
            "inspect",
            "stepOver",
            "stepIn",
            "stepOut",
            "continue",
            "pause",
            "runTo",
            "addBreakpoints",
            "removeBreakpoints",
            "selectFrame",
            "selectThread",
            "terminate",
        ],
        typer.Option("--action", help="Bridge action."),
    ] = "start",
    launch_config_name: Annotated[
        str, typer.Option("--launch-config-name", help="Name from .vscode/launch.json.")
    ] = "Debug with $debugger",
    breakpoint: Annotated[
        list[str] | None, typer.Option("--break", help="Breakpoint as file:line. Repeat as needed.")
    ] = None,
    remove_breakpoint: Annotated[
        list[str] | None, typer.Option("--remove-break", help="Breakpoint to remove as file:line. Repeat as needed.")
    ] = None,
    run_to: Annotated[
        str | None, typer.Option("--run-to", help="Temporary run-to breakpoint as file:line.")
    ] = None,
    local: Annotated[list[str] | None, typer.Option("--local", help="Local variable names to capture.")] = None,
    watch: Annotated[list[str] | None, typer.Option("--watch", help="Watch expression to evaluate while stopped.")] = None,
    allow_watch_eval: Annotated[
        bool,
        typer.Option("--allow-watch-eval", help="Allow VS Code debug adapter watch expression evaluation."),
    ] = False,
    stop_timeout_ms: Annotated[int, typer.Option("--stop-timeout-ms", help="Stop wait timeout.")] = 30000,
    replace_breakpoints: Annotated[
        bool, typer.Option("--replace-breakpoints/--keep-breakpoints", help="Replace existing breakpoints in requested files.")
    ] = True,
    save_before_start: Annotated[
        bool, typer.Option("--save-before-start/--no-save-before-start", help="Ask VS Code to save dirty breakpoint files first.")
    ] = True,
    request_id: Annotated[str | None, typer.Option("--id", help="Request id. Defaults to timestamp.")] = None,
    max_request_age_ms: Annotated[
        int, typer.Option("--max-request-age-ms", help="Maximum request age accepted by the VS Code bridge.")
    ] = 120000,
    session_id: Annotated[str | None, typer.Option("--session-id", help="Existing VS Code debug session id.")] = None,
    expected_stop_sequence: Annotated[
        int | None, typer.Option("--expected-stop-sequence", help="Reject if the bridge session stop sequence has changed.")
    ] = None,
    thread_id: Annotated[int | None, typer.Option("--thread-id", help="DAP thread id for session control.")] = None,
    frame_id: Annotated[int | None, typer.Option("--frame-id", help="DAP frame id for inspection/selection.")] = None,
    stack_depth: Annotated[int, typer.Option("--stack-depth", help="Bounded stack frames to capture for inspection.")] = 1,
    expect_remote_name: Annotated[
        str | None,
        typer.Option(
            "--expect-remote-name",
            help="Require the bridge to run under this VS Code remoteName; use empty string for local.",
        ),
    ] = None,
    expect_workspace_uri_scheme: Annotated[
        str | None,
        typer.Option("--expect-workspace-uri-scheme", help="Require this VS Code workspace URI scheme."),
    ] = None,
    expect_workspace_uri_authority: Annotated[
        str | None,
        typer.Option("--expect-workspace-uri-authority", help="Require this VS Code workspace URI authority."),
    ] = None,
    expect_extension_host_kind: Annotated[
        Literal["ui", "workspace"] | None,
        typer.Option("--expect-extension-host-kind", help="Require the bridge extension host kind."),
    ] = "workspace",
) -> None:
    workspace = workspace.resolve()
    bridge_dir = workspace / ".vscode" / "debugger-bridge"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    request_path = bridge_dir / "request.json"
    generated_request_id = request_id or f"debugger-{uuid.uuid4()}"
    status_name = f"status.{safe_file_name(generated_request_id)}.json"
    status_path = bridge_dir / status_name
    request = {
        "id": generated_request_id,
        "action": action,
        "workspace": str(workspace),
        "launchConfigName": launch_config_name,
        "breakpoints": [parse_breakpoint(item) for item in breakpoint or []],
        "removeBreakpoints": [parse_breakpoint(item) for item in remove_breakpoint or []],
        "runTo": parse_breakpoint(run_to) if run_to else None,
        "locals": local or [],
        "watches": watch or [],
        "allowWatchEval": allow_watch_eval,
        "output": f".vscode/debugger-bridge/{status_name}",
        "stopTimeoutMs": stop_timeout_ms,
        "replaceBreakpoints": replace_breakpoints,
        "saveBeforeStart": save_before_start,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "maxRequestAgeMs": max_request_age_ms,
        "sessionId": session_id,
        "expectedStopSequence": expected_stop_sequence,
        "threadId": thread_id,
        "frameId": frame_id,
        "stackDepth": stack_depth,
        "expectedRemoteName": expect_remote_name if expect_remote_name is not None else default_expected_remote_name(),
        "expectedWorkspaceUriScheme": expect_workspace_uri_scheme,
        "expectedWorkspaceUriAuthority": expect_workspace_uri_authority,
        "expectedExtensionHostKind": expect_extension_host_kind,
    }
    request = {key: value for key, value in request.items() if value is not None}
    request["requestHash"] = canonical_request_hash(request)
    status = json.dumps(
        {
            "id": request["id"],
            "status": "pending",
            "requestHash": request["requestHash"],
            "updatedAt": request["createdAt"],
        },
        indent=2,
        sort_keys=True,
    ) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix="status.", suffix=".json.tmp", dir=bridge_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(status)
        handle.flush()
        os.fsync(handle.fileno())
    Path(temp_name).replace(status_path)
    encoded = json.dumps(request, indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix="request.", suffix=".json.tmp", dir=bridge_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    Path(temp_name).replace(request_path)
    print(request_path)
    print(status_path)


if __name__ == "__main__":
    typer.run(main)
