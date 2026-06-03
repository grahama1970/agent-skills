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
- file watcher for `.vscode/debugger-bridge/request.json`
- `vscode.debug.startDebugging(...)` for visible VS Code session start
- `vscode.debug.addBreakpoints(...)` for source breakpoints
- breakpoint replacement in requested files so stale bridge breakpoints do not accumulate
- dirty-source save before start/restart so VS Code does not leave breakpoints unverified because files are modified
- `restart` requests that stop the active session, replace breakpoints, and start the launch configuration again
- `workbench.action.debug.continue` for continuing an already stopped visible session
- debug adapter tracker for stopped events
- DAP `stackTrace`, `scopes`, `variables`, and `evaluate` requests for paused variable state

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
