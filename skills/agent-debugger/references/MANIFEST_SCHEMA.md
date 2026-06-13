# Agent Debugger Manifest Schema

The manifest is the workspace-local contract between the agent, human, and VS Code bridge.

Path convention:

```text
.plan-iterate/<task>/debug/debug_manifest.json
```

## Current Schema

```json
{
  "schema": "agent_debugger_manifest.v1",
  "version": 1,
  "language": "python",
  "task": "qra-null-key",
  "launch_config_name": "Agent Debugger: qra-null-key",
  "harness": ".plan-iterate/qra-null-key/debug/harness_qra_null_key.py",
  "target": "scripts/rebuild_qra.py",
  "target_args": ["--control", "AC-1"],
  "breakpoints": [
    {
      "file": "src/sparta/qra_loader.py",
      "line": 402,
      "reason": "Check whether control_id is null before query construction.",
      "expressions": ["control_id", "bind_vars", "query_text", "result"],
      "source": "agent",
      "stop": true
    }
  ],
  "commands_path": ".plan-iterate/qra-null-key/debug/debug_commands.jsonl",
  "observations_path": ".plan-iterate/qra-null-key/debug/debug_observations.jsonl",
  "session_state_path": ".plan-iterate/qra-null-key/debug/debug_session_state.json",
  "lifecycle": {
    "replay_semantics": "stop_and_restart_same_launch_config",
    "managed_session_only": true
  }
}
```

## Required Fields

| Field | Requirement |
|---|---|
| `schema` | `agent_debugger_manifest.v1` |
| `version` | `1` |
| `language` | `python` for v1 |
| `task` | stable task id used in `.plan-iterate/<task>/debug/` |
| `launch_config_name` | exact name in `.vscode/launch.json` |
| `harness` | workspace-relative path to generated harness |
| `breakpoints` | list of source breakpoints |
| `commands_path` | workspace-relative JSONL command queue |
| `observations_path` | workspace-relative JSONL observations file |
| `session_state_path` | workspace-relative current state JSON file |

All paths must be workspace-relative and must not escape the workspace.

## Breakpoints

```json
{
  "file": "target.py",
  "line": 12,
  "reason": "Why this breakpoint matters.",
  "expressions": ["value", "len(items)"],
  "source": "agent",
  "stop": true
}
```

`expressions` are evaluated only after the debug adapter reports a stopped event and a stack frame is available.
Failures are written as observations rather than hidden.

## Command Queue

`debug_commands.jsonl` accepts one JSON object per line:

```json
{"type":"evaluate","expression":"items","source":"agent"}
{"type":"continue","source":"agent"}
{"type":"replay","source":"agent"}
```

Supported v1 command types:

```text
load_manifest
set_breakpoints
start
stop
replay
continue
step_over
step_in
step_out
pause
evaluate
```

## Observations

`debug_observations.jsonl` stores append-only runtime facts:

```json
{"schema":"agent_debugger_observation.v1","type":"breakpoint_hit","data":{"file":"target.py","line":12,"expressions":{"value":"42"}}}
```

The agent should reason from observations, not from guessed runtime state.

## v1 Non-Claims

The manifest does not claim native data breakpoints, reverse debugging, attach mode, TypeScript targets, Rust targets, or arbitrary process control.
