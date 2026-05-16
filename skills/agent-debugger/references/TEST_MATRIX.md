# Agent Debugger Test Matrix

## Skill sanity

Command:

```bash
bash skills/agent-debugger/sanity.sh
```

Covered behavior:

| Feature | Proof |
|---|---|
| Python target only | sanity target is a real `.py` script |
| Harness generation | verifies generated harness path exists |
| Manifest generation | validates `agent_debugger_manifest.v1` fields |
| Breakpoint expressions | validates expression list is preserved |
| VS Code launch config | validates `.vscode/launch.json` has `debugpy` launch entry |
| Real target execution | runs generated harness and checks target output |
| Production cleanliness | hashes target before/after and fails if changed |
| Storage policy | fails if heavy artifact dirs appear in skill folder |

## VS Code bridge e2e

Command:

```bash
cd vscode-extensions/agent-debugger-bridge
npm install
xvfb-run -a npm test
```

Covered behavior:

| Feature | Proof |
|---|---|
| Manifest loading | `agentDebugger.runCurrentManifest` loads explicit manifest |
| Agent breakpoints | bridge sets source breakpoints from manifest |
| Managed launch | bridge starts named launch config |
| Stopped event capture | mock adapter emits stopped event; bridge records `breakpoint_hit` |
| Stack frame capture | bridge records current file and line |
| Expression evaluation | bridge evaluates `value`, `len(items)`, and `payload.get("key")` |
| Session state | bridge writes paused state with file and line |
| Human breakpoint visibility | test manually adds a VS Code breakpoint and expects `human_breakpoints_added` |
| Command queue | test appends JSONL `evaluate` and `continue` commands |
| Lifecycle continue | bridge sends DAP continue and records termination |
| Replay | bridge records replay and starts the same launch config again |

## Non-claims deliberately untested in v1

- TypeScript target debugging.
- Rust target debugging.
- Attach-mode debugging.
- Native data breakpoints.
- Reverse debugging.
- Arbitrary process control.

These are intentionally absent from v1 and should not be described as supported.
