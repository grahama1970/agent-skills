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


def parse_reveal(raw: str) -> dict[str, int | str]:
    parts = raw.split(":")
    if len(parts) < 2:
        raise typer.BadParameter(f"--reveal must be file:line[:column[:endLine[:endColumn]]], got {raw!r}")
    file_part = ":".join(parts[:-1]) if len(parts) == 2 else ":".join(parts[:-4])
    nums = parts[-1:] if len(parts) == 2 else parts[-4:]
    if len(parts) == 3:
        file_part = ":".join(parts[:-2])
        nums = parts[-2:]
    elif len(parts) == 4:
        file_part = ":".join(parts[:-3])
        nums = parts[-3:]
    try:
        values = [int(value) for value in nums]
    except ValueError as exc:
        raise typer.BadParameter(f"invalid reveal location in {raw!r}") from exc
    reveal: dict[str, int | str] = {"file": file_part, "line": values[0]}
    if len(values) > 1:
        reveal["column"] = values[1]
    if len(values) > 2:
        reveal["endLine"] = values[2]
    if len(values) > 3:
        reveal["endColumn"] = values[3]
    return reveal


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
            "reveal",
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
    reveal: Annotated[
        str | None, typer.Option("--reveal", help="Editor reveal range as file:line[:column[:endLine[:endColumn]]].")
    ] = None,
    local: Annotated[list[str] | None, typer.Option("--local", help="Local variable names to capture.")] = None,
    watch: Annotated[list[str] | None, typer.Option("--watch", help="Watch expression to evaluate while stopped.")] = None,
    allow_watch_eval: Annotated[
        bool,
        typer.Option("--allow-watch-eval", help="Allow VS Code debug adapter watch expression evaluation."),
    ] = False,
    expand: Annotated[
        list[str] | None,
        typer.Option("--expand", help="Bounded typed expansion of a captured local: NAME or NAME:DEPTH. Repeat as needed."),
    ] = None,
    allow_risky_watches: Annotated[
        bool,
        typer.Option("--allow-risky-watches", help="Evaluate risky-classified watches too (audited in the status)."),
    ] = False,
    workspace_artifacts: Annotated[
        bool,
        typer.Option(
            "--workspace-artifacts",
            help="Write status under .vscode/debugger-bridge in the workspace (legacy; the "
                 "bridge requires the path to be git-ignored). Default: $XDG_RUNTIME_DIR.",
        ),
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
    # #1440: runtime-value-bearing status lives OUTSIDE the target repo by
    # default -- $XDG_RUNTIME_DIR/agent-skills-debugger/<workspace-hash>/ --
    # matching the extension's runtimeArtifactRoot derivation. Only the
    # request.json trigger stays in the workspace. --workspace-artifacts opts
    # into the legacy in-repo location (the bridge then requires it git-ignored).
    if workspace_artifacts:
        status_path = bridge_dir / status_name
    else:
        runtime_base = os.environ.get("XDG_RUNTIME_DIR", "").strip() or tempfile.gettempdir()
        key = hashlib.sha256(str(workspace.resolve()).encode()).hexdigest()[:16]
        runtime_dir = Path(runtime_base) / "agent-skills-debugger" / key
        runtime_dir.mkdir(parents=True, exist_ok=True)
        status_path = runtime_dir / status_name
    request = {
        "id": generated_request_id,
        "action": action,
        "workspace": str(workspace),
        "launchConfigName": launch_config_name,
        "breakpoints": [parse_breakpoint(item) for item in breakpoint or []],
        "removeBreakpoints": [parse_breakpoint(item) for item in remove_breakpoint or []],
        "runTo": parse_breakpoint(run_to) if run_to else None,
        "reveal": parse_reveal(reveal) if reveal else None,
        "locals": local or [],
        "watches": watch or [],
        "allowWatchEval": allow_watch_eval,
        "allowRiskyWatches": allow_risky_watches or None,
        "expand": (
            [{"name": item.split(":", 1)[0], "depth": int(item.split(":", 1)[1])} if ":" in item else item
             for item in expand] if expand else None
        ),
        "output": str(status_path),
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
    fd, temp_name = tempfile.mkstemp(prefix="status.", suffix=".json.tmp", dir=status_path.parent)
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
