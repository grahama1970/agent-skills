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
composes:
  - brave-search
  - dogpile
  - agentic-evals
taxonomy:
  - validation
  - debugging
  - evidence
  - resilience
disciplines:
  - developer-tooling
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

When in doubt, ask this gate question:

```text
Would seeing the actual paused variable/frame/request state change the patch I am about to make?
```

If yes, use `$debugger`.

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

This positive evidence matters because it prevents the agent from confidently
patching a wrong hypothesis. If the observed state contradicts the planned edit,
the edit must change or stop.

Do not use `$debugger` as busywork for problems already explained by deterministic evidence, such as syntax errors, formatter failures, missing imports, dependency resolution, environment setup, type-checker diagnostics, formatter output, or a test assertion that directly names the incorrect literal value and requires no hidden state. Fix those directly, then test.

## Route To The Right Evidence Layer First (operator 2026-08-04)

A breakpoint is one evidence source, not the only one, and it is the WRONG one
for most stuck states in this repo. Before setting a breakpoint, run this
triage. It is a lookup, not a judgement call: the project agent does not get to
decide which layer to read.

| The stuck state | Read this FIRST | Not this |
| --- | --- | --- |
| A `/tau` DAG was rejected before dispatch | The `tau.dag_error.v1` payload: `verdict`, `failure_code`, `severity`, every `evidence.errors[]` entry, and `recommended_action{type,next_agent,reason}` | A breakpoint in the compiler; Tau already named the cause and the next step |
| A `/tau` node was blocked at runtime | `receipt.alerts[]` — each carries `code`, `message`, and an `evidence` object naming node and handler | Inferring the failure from exit codes |
| An `/ask` browser lane failed | `lane-diagnostics.json` in the lane artifact dir: the fixed check series plus its derived `diagnosis` | Guessing whether the tab died, drifted, or was rate-limited |
| A browser page's live state is in question | `surf js --tab-id <id> --no-activate` | Attaching a breakpoint debugger to a lane blocked on Chrome — it gets zero hits |
| A seam artifact is malformed | The `SeamViolation` error list, which carries the pydantic errors verbatim | Reading the producer's source to imagine what it emitted |
| Your own Python does something you cannot explain from its receipts | **This skill.** Set the breakpoint | — |

Only the last row is a debugger problem. The rows above it are already answered
in writing by a tool that fails closed; a breakpoint there is slower, and it
replaces an authoritative answer with a reconstruction of one.

The rule this encodes: **`/debugger` is for state nothing wrote down.** When a
contract validator, a receipt, or a diagnostic probe has already recorded the
answer, reading it is the debugging step. Reach for a breakpoint when the
failing transition happens inside your own process and left no artifact behind.

### The escalation ladder

The table above is a DISPATCH, not a sequence: exactly one row owns any given
symptom, and the project agent reads that row's evidence first. Running
`surf js` against a Tau contract rejection is wasted motion — Tau already wrote
the cause and the next step into the payload. Escalate only when the owning
layer did not resolve it.

```text
0. DISPATCH  - the symptom selects ONE row above. Read that evidence.
               Most stuck states end here: the artifact names the cause.
1. BREAKPOINT - the artifact did not explain it, or no artifact exists.
               $debugger: break at the failing transition, inspect the frame.
2. RESEARCH  - the observed state is real but its MEANING is unknown
               (a provider changed, an API contract is unfamiliar, an error
               string is undocumented). $brave-search or $dogpile, then retry
               ONCE with what the search returned.
3. STOP      - report NEEDS_ATTENTION with the evidence from every rung run.
```

Rung 2 is mandatory, not optional, after two failed focused attempts — the
same bar `$tau` enforces on its own subagents. Do not take a third attempt
from the same stale context: a retry with no new input is spray-and-pray, and
the search exists to supply the new input.

Each rung must produce an artifact before the next one starts. "I looked at the
receipt" without quoting the field, or "I searched" without the query and what
it returned, does not advance the ladder — it just relabels a guess.

### The ladder is enforced in code, not by this document

Write a `debugger.ladder.v1` receipt as you climb, and validate it:

```bash
skills/debugger/scripts/validate_debugger_ladder.py ladder-receipt.json --expect-valid
```

The validator refuses the receipt when a rung is skipped or reordered, when a
non-final rung claims to have resolved the problem, when a cited artifact does
not exist on disk, when a dispatch rung names no field it read, when a
breakpoint rung cites no `debugger.proof.v1`, when a research rung records no
query or no result URL, or when `attempts >= 2` with no research rung.

The existence check is the load-bearing one: an agent can assert it read a
receipt, but it cannot conjure the file it claims to have read.

Schema: `schemas/debugger.ladder.v1.schema.json`. Gate: `./sanity-ladder.sh`.
The validator has no third-party dependencies and needs no Tau checkout, which
is what keeps this skill self-contained.

### Running the ladder as a Tau DAG

`templates/debugger-ladder.dag.yaml` expresses the ladder as a
`tau.dag_contract.v1` (validated against Tau's own `validate_dag_contract`).
Use it when the stuck work is ALREADY running under Tau and you want the rungs
scheduled, receipted, and resumable, with `ladder-gate` on every path to a
terminal node.

The DAG is orchestration, not enforcement — it calls the validator above rather
than reimplementing it. Note that Tau already ships
`brave_search_required_after_two_attempts` as a `fail_closed_on` invariant,
which is Tau's own name for the research rung; the ladder-specific invariants
stay in the validator, because Tau rejects invented invariant codes before
dispatch.

## Self-Contained Scope

This skill is project-agnostic and must remain self-contained in the `agent-skills` repo. Any project agent can use it against the current project by choosing breakpoints in that project's code and running the local reproduction command under the bundled harness or an equivalent platform debugger.

Do not move the reusable debugger workflow into a project repo. Project-specific debugger UI, adapters, or debug-session APIs may live in that project, but they are consumers of this skill. The skill remains the cross-project contract: stop, hypothesize, break, run, inspect real variables, then patch.

All command examples assume:

```bash
export SKILL_DIR="${SKILL_DIR:-/path/to/agent-skills/skills/debugger}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
```

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

The bundled bridge lives at `$SKILL_DIR/vscode-bridge`. It runs inside the VS
Code extension host and provides the missing boundary that a terminal process
cannot cross directly.

Plainly: the terminal writer creates `.vscode/debugger-bridge/request.json`,
the extension reads that request inside the trusted workspace, starts or
continues the visible debug session, queries the stopped adapter for selected
locals/watches, and writes a status/proof artifact back.

The bridge is session-oriented. A start/restart/process request returns
`debugger.session.v1` state with the VS Code debug session ID, selected
thread/frame, current stop sequence, requested/verified breakpoints, and an
event log reference. Follow-up `inspect`, `continue`, `stepOver`, `stepIn`,
`stepOut`, `pause`, `runTo`, `removeBreakpoints`, `selectFrame`,
`selectThread`, and `terminate` requests must bind `sessionId` and
`expectedStopSequence` so a stale agent command cannot control a newer pause.
`inspect` reads the already-paused selected frame without continuing execution.

The bridge is intentionally fail-closed:

- it does not auto-process stale request files on VS Code startup
- every request must include a fresh `createdAt` and unique request id
- duplicate or stale request ids are rejected
- the workspace must be trusted before the bridge starts, restarts, continues, or evaluates debugger state
- the request writer records `status: pending` and a request hash before atomically replacing `request.json`
- the bridge captures only explicitly requested locals
- watch expressions are opt-in per request and should be used only when the expression is known to be side-effect safe
- visible bridge status must not be treated as adapter breakpoint verification unless it includes adapter proof; bridge status can prove the session stopped at the requested source line, while direct DAP proof can additionally show the adapter `setBreakpoints` response

Detailed bridge commands, watcher behavior, status ownership rules, and known
limitations live in `references/vscode-bridge.md`.

Install or update it with:

```bash
"$SKILL_DIR/scripts/install_vscode_bridge.sh"
```

If VS Code was already open before installation, reload the VS Code window so the extension activates.

To request a visible VS Code debug session from a VS Code integrated terminal, write the bridge request file:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/request_vscode_bridge.py" \
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
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_launch.py" \
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
- for Remote SSH workspaces, proof that the bridge extension ran in the
  workspace extension host with the expected `remoteName` and that request,
  status, and session artifacts were written in the remote workspace
- when a breakpoint is requested on a declaration line, receipt evidence for
  requested path/line, VS Code breakpoint state, actual stopped frame, and the
  current source hash/symbol range that justifies any relocated executable line
- proof execution stopped with reason `breakpoint`
- the paused source file, line, and frame
- inspected variables from the paused frame
- analysis of what those variables prove

Run the Remote SSH bridge authority gate when debugging from Graham's normal
local-client/remote-Ubuntu workflow:

```bash
bash "$SKILL_DIR/sanity-bridge-remote-ssh.sh" --allow-live --out /tmp/debugger-remote-ssh-proof
```

If the shell is not inside a Remote SSH workspace, that command must write a
typed blocked receipt instead of treating local VS Code as equivalent.

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
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_typescript_launch.py" \
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
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_typescript_launch.py" \
  --workspace /path/to/project \
  --kind node \
  --program '${workspaceFolder}/src/index.ts' \
  --runtime-executable node \
  --runtime-arg --loader \
  --runtime-arg ts-node/esm
```

For VS Code extension debugging, use an extension host configuration:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_typescript_launch.py" \
  --workspace /path/to/project \
  --kind extensionHost \
  --arg '--extensionDevelopmentPath=${workspaceFolder}'
```

The evidence standard is the same as Python: breakpoint location, source-mapped frame, stopped reason, selected locals, watches when safe, and analysis of what the paused state proves. For TypeScript, also report the generated JavaScript/debugger mapping when source maps affect breakpoint placement.

The TypeScript E2E sanity check must prove a real paused runtime state, not only
launch configuration generation. `./sanity-e2e-typescript.sh` uses the Node
inspector against a `.ts` file, stops at a breakpoint, and captures selected
locals from the paused frame.

## Rust Debugging

Use Rust debugging when the runtime-state question crosses Rust code, cargo
tests, native binaries, FFI boundaries, async Rust tasks, parser/extractor
state, or any bug where ownership, mutation, enum variant selection, error
propagation, or compiled native behavior matters.

For Rust targets, generate a VS Code CodeLLDB-compatible launch configuration
instead of forcing the Python harness or TypeScript writer:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_rust_launch.py" \
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
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_rust_launch.py" \
  --workspace /path/to/project \
  --kind cargo-run \
  --cargo-arg run \
  --cargo-arg --bin \
  --cargo-arg my_binary \
  --arg --sample-input
```

For an already compiled binary:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_rust_launch.py" \
  --workspace /path/to/project \
  --kind program \
  --program '${workspaceFolder}/target/debug/my_binary'
```

The evidence standard is the same as Python and TypeScript: breakpoint location,
stopped reason, selected locals, watches when safe, and analysis of what the
paused state proves. For Rust, also report the Rust debugger adapter used, such
as CodeLLDB, `lldb-dap`, or `rust-gdb`, and any limitation in local/watch
evaluation for optimized or inlined code.

The Rust E2E sanity check must prove a real paused runtime state, not only
launch configuration generation. `./sanity-e2e-rust.sh` compiles a Rust debug
binary, runs it under `rust-gdb`, stops at a source breakpoint, and verifies
selected Rust locals from the paused frame.

## Trigger Bar

Use this skill immediately when:

- the same defect survives two implementation or verification attempts
- the failure involves hidden runtime state, async order, route choice, parser output, generated artifacts, cache, environment, closure, or fixture mutation
- tests pass but the visible behavior is wrong
- the user challenges a claimed fix or asks what variables actually contain
- a proposed fix depends on what a variable, frame, request, response, or model payload looks like at runtime

## Walkthrough Mode (review or blocked)

Triggered by `/debugger walkthrough`, "walk me through this code", or "use
`/debugger` to walk me through where you are blocked". Instead of proving one
stop, you drive the live debugger through an ordered tour of the code and narrate
each stop to the human, with the real paused variable state visible.

1. Author a `debugger.walkthrough.v1` spec (schema:
   `schemas/debugger.walkthrough.v1.schema.json`): a `title`, a `mode`
   (`review` to showcase finished work, `blocked` to take the human to where you
   are stuck), a `launch` block, and an ordered `stops` list. Each stop names a
   `file` and a `line` (or `function`/`class`), the `say` narration, and the
   `locals` to show. See `scenarios/variable_state/walkthrough.review.json`.
2. Run it against the human's open, trusted VS Code workspace:

   ```bash
   DEBUGGER_VSCODE_WORKSPACE=<workspace> \
     uv run --project skills/debugger python skills/debugger/scripts/vscode_walkthrough.py \
     --spec <spec.json> --transcript <out.json>
   ```

   The debugger pauses at each stop (auto-revealing the line in the editor),
   prints `SAY:` narration and the observed `STATE:`, and ends with
   `WALKTHROUGH-COMPLETE`. It is capability-gated: `BRIDGE_BLOCKED` / exit 3 when
   no trusted VS Code bridge answers, so it never fakes a tour.

   Add `--speak` to narrate each stop aloud in the Embry voice through the
   chatterbox agent server (fail-soft: silent if the server is down). Configure
   with `DEBUGGER_SPEAK_URL` and `DEBUGGER_SPEAK_OUT_MAP` (container->host output
   path). This turns the walkthrough into a spoken code tour.
3. Author the stops to tell a story: for `review`, walk the key state
   transitions of what you built; for `blocked`, set breakpoints around where the
   observed state diverges from what you expected and narrate the divergence at
   that exact frame.

Gate: `fixtures/walkthrough.json` (agentic eval).

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
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/capture_breakpoints.py" \
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

## If The Debugger Itself Fails

If the harness crashes, the DAP adapter will not start, the bridge extension is
not installed or active, a breakpoint cannot be set, or the requested local
state cannot be inspected, report that failure as the current blocker. Include
the command, adapter, breakpoint request, error text, and any partial artifact.

Do not silently downgrade the result into a static-code explanation. You may
fall back to static analysis or logs only after saying that debugger proof was
not established and why. The next patch must be labeled as based on fallback
evidence, not debugger proof.

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

## Proof Artifacts, Lessons, And Memory Recall

Fresh debugger proof is the only evidence class that can satisfy this skill for
a current bug. A reusable lesson or a memory recall result may guide breakpoint
selection, but it cannot replace stopping the current program and inspecting the
current paused state.

Canonical proof artifacts use `debugger.proof.v1` and can be normalized with:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/validate_debugger_proof.py" \
  /tmp/debugger-proof.json \
  --expect-valid \
  --canonical-out /tmp/debugger-proof.canonical.json
```

When storing a lesson from debugger proof, distill it through the redaction gate:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/distill_debugger_lesson.py" \
  /tmp/debugger-proof.canonical.json \
  --out /tmp/debugger-lesson.json
```

The lesson artifact is advisory. It preserves the debugger adapter, breakpoint
shape, stopped frame, variable names/types, conclusion, and limitations, but it
does not store raw paused locals, watch values, secrets, tokens, credentials, or
machine-local absolute paths.

Memory recall is also advisory-only. Query memory before scanning or patching
when prior lessons may exist, then normalize the recall result explicitly:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/recall_debugger_lessons.py" \
  --query "route handler selected_handler mismatch" \
  --live \
  --out /tmp/debugger-memory-advisory.json
```

The normalized recall artifact must say `fresh_debugger_proof: false` and
`can_satisfy_debugger_proof: false`. If it suggests a likely bug pattern, use
that only to choose the next breakpoint or local/watch list.

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
