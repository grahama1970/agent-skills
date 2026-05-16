---
name: agent-debugger
description: >
  Agent-invoked and human-collaborative Python debugger workflow for VS Code:
  create harnesses, launch.json entries, manifests, breakpoints, and runtime
  observation loops when an agent is stuck or a human asks to inspect failing
  code with breakpoints.
triggers:
  - agent debugger
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

Use this skill when an agent is stuck, or when a human asks to debug Python code
in VS Code, and runtime state must be inspected before patching.

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
harness, VS Code launch configuration, and debug manifest. The harness must run
the real target code and must not copy the logic being debugged.

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

## Supported VS Code Bridge Features

The companion `vscode-extensions/agent-debugger-bridge` extension is the only
component that talks to VS Code. It supports only documented VS Code extension
and Debug Adapter Protocol actions used in v1:

- source breakpoints and logpoints;
- starting a named `.vscode/launch.json` configuration;
- stopping only the managed debug session;
- replay as stop-and-start of the same launch configuration;
- observing debug-session lifecycle and breakpoint changes;
- capturing stopped events through a debug adapter tracker;
- requesting `stackTrace` and `evaluate` while paused;
- requesting `continue`, `next`, `stepIn`, `stepOut`, and `pause`, with adapter
  failures recorded instead of hidden.

Do not claim support for native data breakpoints, reverse debugging, arbitrary
session control, or attach-mode debugging in v1.

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
reason each breakpoint exists.

## Workflow

1. Human or agent names the Python script to debug.
2. Agent creates a Python harness and `.vscode/launch.json` entry.
3. Agent chooses hypothesis-driven breakpoints and expressions.
4. VS Code bridge loads `debug_manifest.json` and sets breakpoints/logpoints.
5. Human or agent starts/replays the managed debug session.
6. Bridge records breakpoint hits, stack frame, and evaluated expressions.
7. Human and agent discuss observations breakpoint by breakpoint.
8. Agent patches only after the failure path is understood, or asks for another
   runtime observation.

## Python CLI

From the target project root:

```bash
skills/agent-debugger/run.sh init-python \
  --task qra-null-key \
  --target scripts/rebuild_qra.py \
  --target-args-json '["--control", "AC-1"]' \
  --breakpoint src/sparta/qra_loader.py:402:control_id,bind_vars,query_text,result
```

Use `--breakpoints-json '["file.py:10:x", "file.py:20:y"]'` when more than
one breakpoint is needed.

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
- exact VS Code command to run;
- breakpoint map with reason for each breakpoint;
- expressions to inspect;
- expected vs suspicious values;
- whether the harness is temporary, evidence-only, or should become a regression
  test.

## Safety Rules

- Do not add temporary debug variables or branches to production scripts.
- Do not hardcode local machine paths in production code.
- Do not remove human breakpoints.
- Do not stop unrelated debug sessions.
- Do not turn missing runtime evidence into a confident patch.
- If the bridge cannot evaluate an expression, record the failure as an
  observation and ask for a narrower expression.
