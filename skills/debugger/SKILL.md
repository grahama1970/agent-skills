---
name: debugger
description: >
  Force the project-agent to use a real debugger instead of guessing: set
  breakpoints where the problem might be, stop execution at those breakpoints,
  inspect live variable state, and analyze the observed runtime state before
  patching. Use when a project agent is stuck, sees confusing or repeated
  failures, suspects state mutation, routing, async, serialization, cache,
  closure, test fixture, UI/backend mismatch, or any bug where logs/static
  reading would lead to speculation. Use before further patching after two
  failed attempts or whenever the user asks for debugger, breakpoints, debug
  mode, variable state, inspect locals, step through, VS Code debugger, or prove
  runtime behavior.
triggers:
  - debugger
  - use the debugger
  - project-agent debugger
  - debug mode
  - VS Code debugger
  - set breakpoints
  - stop at a breakpoint
  - hit a breakpoint
  - inspect variable state
  - inspect runtime state
  - inspect locals
  - step through the bug
  - stop guessing
  - prove runtime behavior
  - analyze variable states before patching
provides:
  - runtime-state-inspection
  - breakpoint-debugging
  - debugger-proof
composes: []
taxonomy:
  - validation
  - debugging
  - evidence
  - resilience
---

# Debugger

Use this skill to replace LLM inference with observed runtime state. It is primarily for the project-agent, not for the human: the agent must invoke it on itself when it is stuck, seeing confusing state, or at risk of patching from guesses.

The core functions of this skill are:

1. The project-agent must set breakpoints where the problem might be.
2. The project-agent must stop at a breakpoint and analyze live variable state before deciding what to patch.
3. When reporting debugger work to the human, the project-agent must provide a concrete breakpoint location the human can examine, with the expected relevant variable state at that pause.

If these functions are not demonstrated, the skill has not been used.

## When To Use And Why

Use `$debugger` when the next correct action depends on live runtime state, not on what the code appears to do. The purpose is to prevent the project-agent from patching by inference when a debugger can show the actual value, branch, frame, request, response, object mutation, or adapter payload.

Mandatory triggers:

- The human asks for `$debugger`, debugger, VS Code debugger, breakpoints, debug mode, stepping, locals, variable state, or proof of runtime behavior.
- The same defect, failed test, bad UI state, or confusing behavior survives two focused fix/verification attempts.
- A prior success claim is disproved by the human, a screenshot, a runtime artifact, or a visible UI state.
- The suspected bug involves state that changes at runtime: async order, routing, request parsing, branch selection, cache, mutation, serialization, fixture setup, closure state, subprocess output, model payloads, browser state, or UI/backend adapter state.
- The project-agent is about to patch code based on a guess about what a variable contains, which branch runs, which handler receives a request, or which object is passed across a boundary.
- Logs, static reading, DOM assertions, or test pass/fail status do not explain why the observed behavior is wrong.
- The human wants a collaborative breakpoint review: the agent pauses execution, reports the relevant variables, asks whether the state is semantically correct, then continues to the next breakpoint.

Use `$debugger` before patching in these cases because it gives positive evidence:

- the breakpoint was set and verified
- execution stopped at the expected source line
- the paused frame and thread are known
- relevant variables and watches were inspected while execution was stopped
- the agent can say which state is already wrong, which state is still correct, and what transition should be inspected next

Do not use `$debugger` as busywork for problems already explained by deterministic evidence, such as syntax errors, formatter failures, missing imports, type-checker diagnostics, or a test assertion that directly names the incorrect literal value and requires no hidden state. Fix those directly, then test.

When in doubt, ask this gate question:

```text
Would seeing the actual paused variable/frame/request state change the patch I am about to make?
```

If yes, use `$debugger`.

## Self-Contained Scope

This skill is project-agnostic and must remain self-contained in the `agent-skills` repo. Any project agent can use it against the current project by choosing breakpoints in that project's code and running the local reproduction command under the bundled harness or an equivalent platform debugger.

Do not move the reusable debugger workflow into a project repo. Project-specific debugger UI, adapters, or debug-session APIs may live in that project, but they are consumers of this skill. The skill remains the cross-project contract: stop, hypothesize, break, run, inspect real variables, then patch.

## Required Loop

1. Stop coding and state the bug or uncertainty as a runtime-state question.
2. Identify where the relevant state enters, changes, branches, or exits.
3. Set breakpoints at the smallest useful source locations around that transition.
4. Run the real failing command, request, test, UI action, or reproduction under a debugger.
5. Stop at the breakpoint; do not replace this with logs or a static explanation.
6. Inspect locals, selected globals, watched expressions, request/response objects, and return/error state from the paused frame.
7. Analyze the variable state: what is already wrong, what is still correct, and which next branch or mutation follows.
8. Escalate to the human only when the agent is blocked, the observed state requires human/domain judgment, or the agent cannot honestly determine whether the state is correct. When escalating, ask the human to examine the specific paused values, similar to `$interview`: "Does this paused variable state look correct?" or "Which value is wrong?"
9. Continue or step only as needed to observe the next state transition.
10. Give the human a concrete breakpoint to examine: file, line, source statement, and expected relevant variable state at that pause.
11. Report the exact breakpoint locations, inspected values, human confirmation or correction when requested, and what conclusion follows.
12. Patch only after the runtime state explains the failure.

Do not satisfy this skill with a source-code explanation, log skim, print-only trace, or generic test rerun. Those can support the investigation, but the core proof is paused runtime state.

## VS Code Debugger Requirement

When the user asks for the VS Code debugger, use VS Code's debugger path or Debug Adapter Protocol path, not only `pdb`, print statements, or the bundled Python harness.

The project-agent must automatically create or update the target project's `.vscode/launch.json` with a runnable configuration for the reproduction. Do not leave VS Code activation as prose instructions only. The human should be able to open the project in VS Code, select the generated configuration, set or inspect the listed breakpoint, and press Start Debugging.

### Visible VS Code GUI Boundary

Be precise about what is being controlled:

- A standalone terminal CLI can generate `.vscode/launch.json`, open files or workspaces in VS Code, and drive an external DAP/debugpy session, but it is not a supported remote-control API for the visible VS Code workbench debugger.
- A VS Code extension can start a visible VS Code debug session with VS Code's `vscode.debug.startDebugging(...)` API, add/remove breakpoints through `vscode.debug.addBreakpoints(...)`, observe debug lifecycle events, and send requests to the active debug adapter.
- Neither a standalone CLI nor a VS Code extension should claim to read the Variables pane UI directly. Variable state should be captured through DAP requests such as `threads`, `stackTrace`, `scopes`, `variables`, and `evaluate`, or through a DAP tracker/proxy.

Therefore, this skill has two honest modes:

1. **Automated DAP proof mode:** create/update `launch.json`, run the reproduction under a DAP/debugpy controller, stop at breakpoints, inspect variables, and write a proof artifact. This is self-contained in `agent-skills`.
2. **Visible VS Code GUI mode:** create/update `launch.json` and use the bundled companion VS Code extension bridge or a DAP proxy to start/control the visible VS Code session. Without that bridge, report that visible GUI control is not available instead of claiming it.

### Bundled VS Code Extension Bridge

The bundled bridge lives at:

```text
/home/graham/workspace/experiments/agent-skills/skills/debugger/vscode-bridge
```

It runs inside the VS Code extension host and provides the missing boundary that a terminal process cannot cross directly:

- command `debuggerBridge.processRequestFile`
- command `debuggerBridge.startLaunchConfig`
- file watcher for `.vscode/debugger-bridge/request.json`
- `vscode.debug.startDebugging(...)` for visible VS Code session start
- `vscode.debug.addBreakpoints(...)` for source breakpoints
- breakpoint replacement in requested files so stale bridge breakpoints do not accumulate
- dirty-source save before start/restart so VS Code does not leave the breakpoint unverified because the file is modified
- `restart` requests that stop the active session, replace breakpoints, and start the launch configuration again
- `workbench.action.debug.continue` for continuing an already stopped visible session
- debug adapter tracker for stopped events
- DAP `stackTrace`, `scopes`, `variables`, and `evaluate` requests for paused variable state

The bridge is intentionally fail-closed:

- it does not auto-process stale request files on VS Code startup
- every request must include a fresh `createdAt` and unique request id
- duplicate or stale request ids are rejected
- the workspace must be trusted before the bridge starts, restarts, continues, or evaluates debugger state
- the request writer records `status: pending` and a request hash before atomically replacing `request.json`
- the bridge captures only explicitly requested locals
- watch expressions are opt-in per request and should be used only when the expression is known to be side-effect safe
- visible bridge status must not be treated as adapter breakpoint verification unless it includes adapter proof; bridge status can prove the session stopped at the requested source line, while direct DAP proof can additionally show the adapter `setBreakpoints` response

Install or update it with:

```bash
/home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/install_vscode_bridge.sh
```

If VS Code was already open before installation, reload the VS Code window so the extension activates.

To request a visible VS Code debug session from a VS Code integrated terminal, write the bridge request file:

```bash
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/request_vscode_bridge.py \
  --workspace /path/to/project \
  --launch-config-name "Debug failing pytest with $debugger" \
  --break path/to/file.py:123 \
  --local some_var \
  --watch 'some_obj.field' \
  --allow-watch-eval
```

The extension writes status/proof to:

```text
.vscode/debugger-bridge/status.json
```

The bridge does not scrape the Variables pane UI. It captures the same class of runtime state through DAP while the visible VS Code debug session is stopped.

Use the bundled writer:

```bash
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_launch.py \
  --workspace /path/to/project \
  --name "Debug failing pytest with $debugger" \
  --python '${workspaceFolder}/backend/.venv/bin/python3' \
  --module pytest \
  --arg -q \
  --arg path/to/test.py::test_name \
  --env 'PYTHONPATH=${workspaceFolder}/backend/src'
```

A valid VS Code debugger proof includes:

- the VS Code debug adapter or extension used
- the generated `.vscode/launch.json` configuration path and name
- the `setBreakpoints` request or visible breakpoint configuration
- proof the breakpoint was verified when the adapter exposes it, or an explicit `adapterBreakpointVerification: unavailable-vscode-api` limitation plus proof the stopped frame matches the requested source line
- proof execution stopped with reason `breakpoint`
- the paused source file, line, and frame
- inspected variables from the paused frame
- analysis of what those variables prove

The project-agent may drive the VS Code debugger through DAP in a terminal when a GUI is not required. The proof still must show that the breakpoint was set, hit, and used to inspect live runtime state.

## Language-Neutral Debugging Contract

The project-agent and human should not need a different debugging workflow for
Python, TypeScript, Rust, or any other implementation language. The useful
object is always the paused variable state at a particular breakpoint.

Language only determines the adapter used to stop execution and read frame
state:

- Python uses the bundled Python harness, VS Code debugpy, or another Python
  debugger.
- TypeScript, JavaScript, and Node use the VS Code JavaScript debugger through
  generated launch configurations.
- Rust uses CodeLLDB/lldb-compatible VS Code launch configurations through the
  bundled Rust writer, or an equivalent Rust-capable DAP/debugger.

The reported proof must have the same shape for every language: debugger used,
breakpoint file and line, hit or miss, paused frame, selected locals or watches,
human-examinable breakpoint handoff, and what the observed state proves.

## TypeScript And Node Debugging

Use TypeScript debugging when the runtime-state question crosses JavaScript, TypeScript, Node, browser, or VS Code extension code. This includes React state, server-side Node handlers, build/test runners, Playwright helpers, VS Code extension host behavior, source-map mismatches, async callback order, and any bug where compiled JavaScript does not obviously match the TypeScript source.

For TypeScript/Node targets, generate a VS Code JavaScript debugger configuration instead of forcing the Python harness:

```bash
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_typescript_launch.py \
  --workspace /path/to/project \
  --name "Debug TypeScript test with $debugger" \
  --kind npm \
  --runtime-arg run \
  --runtime-arg test \
  --runtime-arg -- \
  --arg path/to/test.spec.ts \
  --out-file '${workspaceFolder}/dist/**/*.js' \
  --out-file '${workspaceFolder}/out/**/*.js'
```

For a direct Node/TypeScript entrypoint:

```bash
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_typescript_launch.py \
  --workspace /path/to/project \
  --kind node \
  --program '${workspaceFolder}/src/index.ts' \
  --runtime-executable node \
  --runtime-arg --loader \
  --runtime-arg ts-node/esm
```

For VS Code extension debugging, use an extension host configuration:

```bash
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_typescript_launch.py \
  --workspace /path/to/project \
  --kind extensionHost \
  --arg '--extensionDevelopmentPath=${workspaceFolder}'
```

The evidence standard is the same as Python: breakpoint location, source-mapped frame, stopped reason, selected locals, watches when safe, and analysis of what the paused state proves. For TypeScript, also report the generated JavaScript/debugger mapping when source maps affect breakpoint placement.

## Rust Debugging

Use Rust debugging when the runtime-state question crosses Rust code, cargo
tests, native binaries, FFI boundaries, async Rust tasks, parser/extractor
state, or any bug where ownership, mutation, enum variant selection, error
propagation, or compiled native behavior matters.

For Rust targets, generate a VS Code CodeLLDB-compatible launch configuration
instead of forcing the Python harness or TypeScript writer:

```bash
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_rust_launch.py \
  --workspace /path/to/project \
  --name "Debug Rust test with $debugger" \
  --kind cargo-test \
  --cargo-arg test \
  --cargo-arg --no-run \
  --cargo-arg exact_case \
  --cargo-arg -- \
  --cargo-arg --exact \
  --filter-name crate_or_test_target \
  --filter-kind test \
  --arg --nocapture \
  --env RUST_BACKTRACE=1
```

For a Rust binary launched through cargo:

```bash
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_rust_launch.py \
  --workspace /path/to/project \
  --kind cargo-run \
  --cargo-arg run \
  --cargo-arg --bin \
  --cargo-arg my_binary \
  --arg --sample-input
```

For an already compiled binary:

```bash
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/write_vscode_rust_launch.py \
  --workspace /path/to/project \
  --kind program \
  --program '${workspaceFolder}/target/debug/my_binary'
```

The evidence standard is the same as Python and TypeScript: breakpoint location,
stopped reason, selected locals, watches when safe, and analysis of what the
paused state proves. For Rust, also report the Rust debugger adapter used, such
as CodeLLDB, `lldb-dap`, or `rust-gdb`, and any limitation in local/watch
evaluation for optimized or inlined code.

## Trigger Bar

Use this skill immediately when:

- the same defect survives two implementation or verification attempts
- the failure involves hidden runtime state, async order, route choice, parser output, generated artifacts, cache, environment, closure, or fixture mutation
- tests pass but the visible behavior is wrong
- the user challenges a claimed fix or asks what variables actually contain
- a proposed fix depends on what a variable, frame, request, response, or model payload looks like at runtime

## Breakpoint Selection

Prefer breakpoints where state enters, changes, and exits:

- entrypoint: request handler, CLI main, test target, event callback, route function
- branch: condition that chooses the wrong route or skips expected work
- mutation: assignment, append, merge, serialization, cache write, store update
- boundary: API/client call, subprocess call, DB query, file read/write, model invocation
- render/adapter: data normalized for UI, artifact schema, template props

Set two or three focused breakpoints rather than scattering probes. If the first breakpoint shows the state is already wrong, move upstream.

## Python Harness

For Python targets, prefer the bundled harness when it fits:

```bash
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
uv run --project /home/graham/workspace/experiments/agent-skills/skills/debugger \
  python /home/graham/workspace/experiments/agent-skills/skills/debugger/scripts/capture_breakpoints.py \
  --break path/to/file.py:123 \
  --local some_var \
  --watch 'some_var' \
  --watch 'obj.field' \
  --allow-watch-eval \
  --out /tmp/debugger-proof.json \
  -- python -m pytest path/to/test.py::test_name -q
```

The script runs the command in-process under Python's debugger core, captures each breakpoint hit, selected locals, watched expression results when `--allow-watch-eval` is explicitly set, and exit/error status. It is for Python commands that can run in the current interpreter. For live servers, subprocesses, browser runtimes, TypeScript, or non-Python targets, use the platform debugger directly and preserve equivalent proof artifacts.

## Live Process Debugging

When the bug occurs only in a running service:

1. Start the service in debug mode or with a debugger attach hook.
2. Trigger the real request or UI action that reproduces the bug.
3. Pause at the route/handler/adapter frame.
4. Inspect the request, computed state, artifacts, response, and any global store involved.
5. Capture a proof artifact: debugger console transcript, JSON dump from the paused frame, screenshot of the debugger UI, or structured harness output.

For UI bugs, debugger evidence does not replace screenshot proof. Use debugger state to explain why the UI is wrong, then verify the rendered UI visually.

## Evidence Standard

A valid debugger result includes:

- command or reproduction used
- debugger used, such as VS Code debugpy/DAP, browser DevTools, `pdb`, or another platform debugger
- breakpoint file and line
- source line at each hit
- locals or watched expressions relevant to the hypothesis
- human-examinable breakpoint handoff: file, line, source statement, and expected variable state
- whether the breakpoint was actually hit
- analysis: what state was observed, what it proves, and what edit or non-edit follows
- human examination result when the variable state requires domain judgment

If the breakpoint is not hit, report that as evidence and adjust the hypothesis. Do not claim the debugger proved the bug location.

## Human Escalation Checkpoint

This skill is not a default request to make the human debug. The project-agent should inspect and analyze the paused state itself first.

Use a human checkpoint only when the variable state is not purely mechanical or when the project-agent is blocked and might otherwise hide that blockage behind speculation. Examples:

- a parsed route, extracted entity, or policy decision looks plausible but may be semantically wrong
- a UI state object has many fields and the human needs to identify the wrong one
- a model payload, prompt, or response shape needs product judgment
- the agent cannot tell whether observed runtime state matches the user's intent

Ask one focused question and show the relevant paused values. Do not ask the human to read a whole dump. Continue debugging after the human identifies whether the state is correct, wrong, or missing.

## Reporting Format

Use this compact format in the final answer or debug note:

```text
Debugger proof:
- Repro: <command/request/test>
- Breakpoint: <file>:<line> <source line>
- Observed: <variable>=<value>, <watch>=<value>
- Human breakpoint: <file>:<line>, expected <variable>=<value>
- Conclusion: <what this proves>
- Next edit: <smallest change justified by the observed state>
```

## Guardrails

- Do not mutate user data while debugging unless the reproduction explicitly requires it.
- Do not dump secrets, tokens, or full private payloads into chat. Redact values while preserving shape and key state.
- Do not continue patching from intuition when debugger state contradicts the hypothesis.
- Do not use this skill as busywork for obvious syntax errors or deterministic lint failures; fix those directly.
