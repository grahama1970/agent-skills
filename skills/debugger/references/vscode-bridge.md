# VS Code Bridge Notes

The VS Code bridge is the optional visible-debugger path for `$debugger`. It is
used when the human or project-agent needs the real VS Code workbench debugger
instead of only a terminal DAP proof run.

## What It Does

The terminal-side writer creates `.vscode/debugger-bridge/request.json` in the
target workspace. The companion VS Code extension runs inside the trusted VS
Code extension host, watches that request file, starts or continues the selected
debug configuration, requests paused frame state through the Debug Adapter
Protocol, and writes a status/proof JSON artifact back under
`.vscode/debugger-bridge/`.

It does not scrape the Variables pane UI. Variable state is captured through
DAP requests such as `stackTrace`, `scopes`, `variables`, and, only when
explicitly allowed, `evaluate`.

## Extension Capabilities

- command `debuggerBridge.processRequestFile`
- command `debuggerBridge.startLaunchConfig`
- extension host authority declared as `"extensionKind": ["workspace"]`, so
  Remote SSH opens the bridge in the remote workspace extension host while the
  human-visible workbench remains in the local VS Code client
- file watcher for `.vscode/debugger-bridge/request.json`
- `vscode.debug.startDebugging(...)` for visible VS Code session start
- `vscode.debug.addBreakpoints(...)` for source breakpoints
- breakpoint replacement in requested files so stale bridge breakpoints do not accumulate
- dirty-source save before start/restart so VS Code does not leave breakpoints unverified because files are modified
- `restart` requests that stop the active session, replace breakpoints, and start the launch configuration again
- debug adapter tracker for stopped events
- DAP `stackTrace`, `scopes`, `variables`, and `evaluate` requests for paused variable state
- session-bound DAP actions for `inspect`, `continue`, `stepOver`, `stepIn`,
  `stepOut`, `pause`, `runTo`, `removeBreakpoints`, `selectFrame`,
  `selectThread`, and `terminate`
- `debugger.session.v1` state in session-control statuses, including VS Code
  debug session ID/type/name, stop sequence, selected thread/frame,
  requested/verified breakpoints, last command ID/hash, and event log reference
- stale-command rejection through `sessionId` plus `expectedStopSequence`
- append-only session event snapshots written beside bridge status artifacts
- authority receipts on bridge/session outputs: local UI kind, `remoteName`,
  extension host kind, workspace URI scheme/authority/path, and request/status
  artifact locations

## Session Control

After a start/restart/process request stops at a breakpoint, read the returned
`sessionState.vscodeSessionId`, `sessionState.stopSequence`, and selected
thread/frame. Reuse those fields for follow-up requests:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/request_vscode_bridge.py" \
  --workspace /path/to/project \
  --action inspect \
  --session-id "$VSCODE_SESSION_ID" \
  --expected-stop-sequence "$STOP_SEQUENCE" \
  --thread-id "$THREAD_ID" \
  --local req
```

Stepping and runtime control use the same binding:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/request_vscode_bridge.py" \
  --workspace /path/to/project \
  --action stepOver \
  --session-id "$VSCODE_SESSION_ID" \
  --expected-stop-sequence "$STOP_SEQUENCE" \
  --thread-id "$THREAD_ID"
```

The bridge rejects a stale `expectedStopSequence` instead of acting on a newer
pause. Named-local reads remain separate from watch evaluation; watch
expressions still require `--allow-watch-eval`.

## Remote SSH Authority

The bridge is a workspace extension. In a Remote SSH workspace the extension
must run in the remote extension host, not only in the local UI host. Request
writers can fail closed by including:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/request_vscode_bridge.py" \
  --workspace /remote/repo \
  --action restart \
  --launch-config-name "Debug with $debugger" \
  --break path/to/file.py:12 \
  --local value \
  --expect-remote-name ssh-remote \
  --expect-extension-host-kind workspace
```

When the active bridge authority does not match the requested authority, the
extension writes an error with `debugger_bridge_authority_mismatch` and no
debug session is started. That is the expected failure for a request emitted
from a remote project while VS Code only has a local/UI-host bridge installed.

Install/update the VSIX with an authority report:

```bash
"$SKILL_DIR/scripts/install_vscode_bridge.sh" \
  --report-json /tmp/debugger-vscode-bridge-install.json
```

Inside a Remote SSH integrated terminal, add `--require-remote-ssh` to make the
installer refuse local-only installation.

The live Remote SSH gate is:

```bash
bash "$SKILL_DIR/sanity-bridge-remote-ssh.sh" --allow-live --out /tmp/debugger-remote-ssh-proof
```

If the current shell is not in a Remote SSH workspace, the gate writes a typed
`remote_ssh_extension_host_unavailable` blocked receipt instead of using a
local simulation.

## Breakpoint Location Evidence

Bridge statuses distinguish:

- requested source breakpoint path/line;
- VS Code `SourceBreakpoint` path/line/enabled state;
- adapter verification status when available;
- actual stopped frame path/line/function;
- current source hash and symbol range when a breakpoint relocates from a
  `def` or `class` declaration to the first executable line.

A relocated breakpoint is accepted only when the actual stopped frame is in the
same current source file and inside the requested symbol range. The receipt
records `breakpointEvidence[].accepted`, `relocated`, `sourceSymbolRange`, and
the reason for acceptance or rejection.

For Docker/debugpy attach, keep host and container paths explicit in
`pathMappings`. A bridge receipt may prove the visible VS Code session stopped,
but a wrong `pathMappings` recipe must fail closed when the stopped frame cannot
be tied back to the requested current source range.

## Status Ownership

The request writer records `status: pending` and the request hash before
atomically replacing `request.json`. Bridge-side owned status writes use a
status-file lock and atomic replace. If a newer request owns the shared status
file, an older write is archived as a superseded status instead of overwriting
the current request.

Malformed ownerless request diagnostics are quarantined to invalid-request
status files. Parseable requests with custom `output` paths route errors to the
requested output path when that path is contained by the workspace.

## Current Limitations

- Visible bridge status can prove that the session stopped at the requested
  source line, but adapter breakpoint verification still requires adapter proof
  when the adapter exposes it.
- Compound VS Code session attribution remains a residual hardening area.
- Manual interference during a visible debug session can still confuse human
  interpretation; preserve the emitted status artifact and report any manual
  steps.
- Future adapters should keep extending symlink and path-containment checks
  before claiming stronger bridge-proof safety.
