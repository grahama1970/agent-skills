# Agent Debugger Bridge

Manifest-driven VS Code bridge for the `agent-debugger` skill.

The extension does not infer bugs or edit code. It reads an agent-generated
`debug_manifest.json`, sets source breakpoints, starts the named launch
configuration, records stopped-state observations, evaluates requested
expressions, and writes observations back to the project.

## Commands

- `Agent Debugger: Load Manifest`
- `Agent Debugger: Run Current Manifest`
- `Agent Debugger: Set Breakpoints`
- `Agent Debugger: Start`
- `Agent Debugger: Stop Managed Session`
- `Agent Debugger: Replay Managed Session`
- `Agent Debugger: Continue`
- `Agent Debugger: Step Over`
- `Agent Debugger: Step In`
- `Agent Debugger: Step Out`
- `Agent Debugger: Pause`
- `Agent Debugger: Evaluate Expression`
- `Agent Debugger: Process Command Queue`

## Install for development

```bash
cd vscode-extensions/agent-debugger-bridge
npm install
npm run compile
```

Open this folder in VS Code and press `F5` to launch an Extension Development Host.

## Run tests

```bash
cd vscode-extensions/agent-debugger-bridge
npm install
xvfb-run -a npm test
```

The e2e suite uses a mock debug adapter registered by this extension. That keeps
the bridge tests deterministic and does not require the Python extension in CI.

## v1 Scope

Supported:

- manifest loading;
- source breakpoints/logpoints from the manifest;
- named launch config start;
- managed session stop/replay;
- stopped event capture;
- stack trace request;
- expression evaluation in the paused stack frame;
- human-set breakpoint observation;
- JSONL command queue processing.

Not supported in v1:

- TypeScript or Rust targets;
- attach mode;
- native data breakpoints;
- reverse debugging;
- control of unrelated debug sessions or arbitrary processes.
