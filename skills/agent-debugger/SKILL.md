---
name: agent-debugger
description: >
  Python-first agent debugger with two supported modes: agent-only headless
  debugpy/DAP runtime inspection, and optional human-agent collaboration through
  a VS Code bridge over the same manifest.
triggers:
  - agent debugger
  - debug this script
  - debug this script in vscode
  - create a debug harness
  - help me step through this failing script
  - agent code is failing and I need breakpoints
  - show me what this script is doing
  - create launch.json for debugging
  - run the debugger where you think the problem is
  - agent is stuck and needs runtime truth
provides:
  - agent-debugger
  - debugger-harness
  - headless-debugpy-runner
  - vscode-launch-config
  - debug-manifest
  - collaborative-debug-workflow
  - runtime-observation-request
composes:
  - best-practices-skills
taxonomy:
  - debugging
  - validation
  - human-in-the-loop
  - reproducibility
  - agent-reliability
---

# Agent Debugger

Use this skill when an agent is stuck, or when a human asks to debug Python code,
and runtime state must be inspected before patching.

This is a **Python-first** agent debugger. TypeScript targets, Rust targets,
attach-mode debugging, native data breakpoints, and reverse debugging are out of
scope for v1 until implemented and tested separately.

## Compliance with best-practices-skills

This skill follows `/best-practices-skills`.

- `SKILL.md` stays concise; longer details live in `references/`.
- Python CLIs use Typer only.
- The skill does not access ArangoDB directly.
- Future memory operations must go through `/memory` subcommands.
- Generated logs, fixtures, and observations are written into the target project,
  usually `.plan-iterate/<task>/debug/`, not into this skill folder.
- Non-trivial behavior is checked by `sanity.sh`.

## Core Rule

When runtime behavior is uncertain, do not guess harder. Create a debug session.

Production code stays clean. Debugging happens through a generated Python
harness, debug manifest, and runtime observation loop. The harness must run the
real target code and must not copy the logic being debugged.

## Two Supported Modes

### Mode 1: Agent-only headless mode

This is the default agent mode. It does **not** require VS Code.

The agent uses the generated manifest and runs debugpy/DAP headlessly:

```bash
skills/agent-debugger/run.sh run-headless \
  --manifest .plan-iterate/<task>/debug/debug_manifest.json
```

The headless runner must:

- launch the generated harness under debugpy/DAP;
- set manifest breakpoints;
- continue until breakpoints are hit;
- capture file, line, frame, and requested expression values;
- write `debug_observations.jsonl` and `debug_session_state.json`;
- avoid arbitrary process control and attach mode in v1.

Use this mode when the agent needs runtime truth without a human in the editor.

### Mode 2: Human-agent VS Code collaboration mode

This mode uses the same manifest, but the human can inspect and steer the debug
session in VS Code.

The VS Code bridge extension may:

- load `debug_manifest.json`;
- set agent-requested breakpoints/logpoints;
- record human-added breakpoints;
- start/stop/replay only the managed launch configuration;
- capture stopped events, stack frame, file/line, and expression values;
- write observations back for the agent to read and discuss.

Use this mode when the human and agent need to look at the same runtime state
breakpoint by breakpoint.

## Autonomous Agent Trigger

The agent may invoke this skill without waiting for the human when any of these
are true:

- the agent does not know what a variable contains at a critical line;
- a dictionary key may be missing, null, or mutated;
- an exception may be swallowed and silently defaulted;
- a database query may be using wrong parameters or fake fallback data;
- repeated patches have not explained the failure;
- the next edit would be based on inference rather than observed runtime state.

Convert uncertainty into a debugger question:

```text
Stop at file:line.
Evaluate these expressions.
Expected state is X.
Suspicious state is Y.
This observation will confirm or reject hypothesis Z.
```

## Generated Project Artifacts

For task `qra-null-key`, generate:

```text
.plan-iterate/qra-null-key/debug/
  harness_qra_null_key.py
  debug_manifest.json
  debug_commands.jsonl
  debug_observations.jsonl
  debug_session_state.json
  notes.md

.vscode/
  launch.json
```

The manifest is the contract between agent, human, and VS Code bridge. It names
the launch configuration, breakpoint locations, expressions to evaluate, and the
reason each breakpoint exists. The same manifest must work for headless mode and
VS Code collaboration mode.

## Workflow

1. Human or agent names the Python script to debug.
2. Agent creates a Python harness, manifest, and `.vscode/launch.json` entry.
3. Agent chooses hypothesis-driven breakpoints and expressions.
4. Agent runs headless mode, or human/agent opens VS Code collaboration mode.
5. Runtime observations are written to `debug_observations.jsonl`.
6. Human and/or agent discuss observations breakpoint by breakpoint.
7. Agent patches only after the failure path is understood, or asks for another
   runtime observation.

## Python CLI

From the target project root:

```bash
skills/agent-debugger/run.sh init-python \
  --task qra-null-key \
  --target scripts/rebuild_qra.py \
  --target-args-json '["--control", "AC-1"]' \
  --breakpoints-json '["src/sparta/qra_loader.py:402:control_id,bind_vars,query_text,result"]'
```

Then run agent-only mode:

```bash
skills/agent-debugger/run.sh run-headless \
  --manifest .plan-iterate/qra-null-key/debug/debug_manifest.json
```

Or open VS Code and run the bridge command:

```text
Agent Debugger: Run Current Manifest
```

Run local skill sanity after edits:

```bash
bash skills/agent-debugger/sanity.sh
```

See `references/INSTALL.md` for extension install notes and
`references/MANIFEST_SCHEMA.md` for the manifest contract.

## Agent Output Contract

When the agent creates a debug session, it must report:

- generated harness path;
- launch configuration name;
- manifest path;
- exact headless command;
- exact VS Code command when human collaboration is requested;
- breakpoint map with reason for each breakpoint;
- expressions to inspect;
- expected vs suspicious values;
- whether the harness is temporary, evidence-only, or should become a regression
  test.

## Safety Rules

- Do not add temporary debug variables or branches to production scripts.
- Do not hardcode local machine paths in production code.
- Do not expose debugpy beyond `127.0.0.1` in v1.
- Do not remove human breakpoints.
- Do not stop unrelated debug sessions.
- Do not turn missing runtime evidence into a confident patch.
- If the runner or bridge cannot evaluate an expression, record the failure as
  an observation and ask for a narrower expression.
