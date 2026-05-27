# debugger — Stop Guessing, Inspect Runtime State

<p align="center">
  <img
    src="docs/assets/debugger-banner.png"
    alt="debugger skill banner showing a vintage industrial DEBUGGER machine catching bugs in a glass inspection chamber"
    width="100%"
  />
</p>

Agents can read code quickly, but reading code is not the same as knowing what
the program did. The mistake usually happens in the gap between those two
things: the agent believes a branch was taken, a request had a certain shape, a
cache was empty, or a variable still held the value the source code suggests.
Then it patches the imagined program instead of the running one.

`$debugger` exists to close that gap. It gives the agent a real breakpoint,
a real paused frame, and real variable state before it is allowed to patch from
a hunch.

Use it when the question is not "what does the code say?" but "what was true at
the moment the bug happened?"

Most LLM debugging today is reactive: read stderr, read stdout, skim logs,
patch, rerun, repeat. That works for simple errors, but it fails when the bug is
inside live state. A stack trace can tell you where execution ended; it usually
does not tell you which object was already wrong three frames earlier, which
branch silently skipped work, or what value crossed an adapter boundary.

`$debugger` fills that hole. It gives the project agent a way to inspect
variables while the program is paused, not after the process has already
collapsed into output text.

```text
bug survives reading or tests
    ↓
agent states the runtime-state question
    ↓
$debugger sets focused breakpoints
    ↓
execution stops in the real failing path
    ↓
locals, watches, frame, and breakpoint proof are captured
    ↓
agent patches only what the paused state justifies
```

## The Two Things This Skill Does

### 1. It makes the project agent prove runtime state before patching

The skill forces a simple discipline: stop execution where the relevant state
enters, changes, branches, or leaves; inspect that paused state; then explain
what the observation proves.

That matters when the failure involves:

- async order
- route or handler selection
- parser output
- fixture setup
- mutation or cache state
- request and response objects
- generated artifacts
- model payloads
- UI/backend adapter state

In those cases, logs and static reading are often just another way to guess.
A breakpoint says whether the value was actually there.

### 2. It makes debugger collaboration easy when the human is needed

The skill is primarily for the project agent. It should inspect and interpret
the paused state itself first. When the paused state needs human judgment, the
same proof gives the human a concrete place to look:

```text
file:line
source statement
breakpoint hit or not hit
paused frame
selected locals and watches
what the agent thinks those values prove
```

That handoff is useful when the paused state needs domain judgment. The agent
can ask a focused question such as "Does this parsed route look correct?" or
"Which field in this UI state object is wrong?" instead of asking the human to
read a whole dump.

The goal is not to make the human do the debugging. The goal is to make the
runtime state small enough and concrete enough that a human can correct the
agent's interpretation when product or domain judgment matters.

## When The Agent Should Use It On Its Own

Use `$debugger` when seeing the paused frame would change the next patch.

Good triggers:

- the human asks for a debugger, breakpoint, VS Code debugger, locals, variable
  state, or runtime proof
- the same defect survives two focused fix attempts
- a claimed fix is disproved by a screenshot, artifact, runtime result, or
  human counterexample
- the bug depends on hidden state rather than a visible syntax/type/lint error
- the agent is about to say "this probably contains..." or "that branch should
  run..."
- stdout and stderr show symptoms but not the variable, frame, or branch where
  the state first became wrong

Skip it for deterministic failures that already name the fix, such as missing
imports, formatter output, syntax errors, or a test assertion that directly
identifies the wrong literal value.

## When To Collaborate With The Human

Use a human checkpoint when the debugger has paused at a meaningful state, but
the correctness of that state is semantic rather than mechanical.

Good collaboration points:

- a parsed route, policy decision, entity, or evidence label looks plausible but
  may be semantically wrong
- a UI state object has many fields and the human can identify which one does
  not match the intended workflow
- a model payload or prompt variable needs product judgment
- a request or artifact shape is valid JSON but may be the wrong contract

The agent should show only the relevant paused values and ask one focused
question. For example:

```text
Paused at backend/routes.py:184, selected_handler="fallback".
Expected candidate handlers were ["project_chat", "artifact_chat"].
Does this fallback route look correct for this request?
```

## How Breakpoints Work

A breakpoint is a deliberate pause at a source line. When the program reaches
that line, the debugger stops the running process before the next statement
executes. While it is stopped, the agent can inspect:

- the current function and source line
- local variables in that frame
- selected globals or object fields
- watched expressions, when evaluation is safe
- the call stack that led to the pause
- whether the stopped location matches the requested breakpoint

That matters because the agent can distinguish:

- state was already wrong before this function
- state became wrong at this branch
- state is correct here, so the bug is downstream
- the suspected path was never reached

If the breakpoint does not hit, that is evidence too. It means the current
hypothesis about the execution path is wrong or the reproduction did not reach
the target state.

## Supported Code Languages

The debugger workflow is language-neutral. The project agent and human should
not need a different mental model for Python, TypeScript, Rust, or any other
runtime. The useful object is always the same: paused variable state at a
specific breakpoint.

Language only matters below the surface, where the skill chooses the adapter
that can stop that runtime and read its frame state.

Current first-class support:

- **Python:** bundled breakpoint harness for in-process Python commands and
  tests, plus VS Code/debugpy launch generation and DAP proof capture.
- **TypeScript, JavaScript, and Node:** VS Code JavaScript debugger launch
  generation for npm scripts, direct Node/TypeScript entrypoints, Playwright or
  build/test runners, browser-adjacent state, and VS Code extension-host code.
- **Rust:** VS Code CodeLLDB-compatible launch generation for cargo tests,
  cargo-launched binaries, and already compiled Rust programs.

Current generic support:

- **Other runtimes:** use the platform debugger directly and preserve the same
  proof artifact: debugger used, breakpoint file/line, hit or miss, paused
  frame, selected locals or watches, and what the observed state proves.

For Rust, the adapter is usually CodeLLDB, `lldb-dap`, or another
LLDB/GDB-backed Rust debugger. That adapter detail should not change the
human-facing proof: the agent still reports the breakpoint, hit/miss status,
paused frame, selected variables, and what the values prove.

The skill includes real runtime E2E sanity checks for all three common project
languages:

- Python: VS Code/debugpy breakpoint proof captures paused locals.
- TypeScript: Node inspector breakpoint proof captures paused locals in a
  `.ts` source file.
- Rust: `rust-gdb` breakpoint proof captures paused Rust locals in a compiled
  debug binary.

## Try This First

Choose the runtime that matches the failing path. All examples assume:

```bash
export SKILL_DIR="${SKILL_DIR:-$(pwd)}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/debugger/.venv}"
```

For Python tests or commands that can run in-process:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/capture_breakpoints.py" \
  --break path/to/file.py:123 \
  --local some_var \
  --watch 'some_obj.field' \
  --allow-watch-eval \
  --out /tmp/debugger-proof.json \
  -- python -m pytest path/to/test.py::test_name -q
```

For VS Code, first write a launch configuration, then use either direct DAP
proof or the bundled VS Code bridge:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_launch.py" \
  --workspace /path/to/project \
  --name "Debug failing pytest with $debugger" \
  --python '${workspaceFolder}/.venv/bin/python3' \
  --module pytest \
  --arg -q \
  --arg path/to/test.py::test_name
```

For TypeScript, Node, or VS Code extension work:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/write_vscode_typescript_launch.py" \
  --workspace /path/to/project \
  --name "Debug TypeScript test with $debugger" \
  --kind npm \
  --runtime-arg run \
  --runtime-arg test \
  --runtime-arg -- \
  --arg path/to/test.spec.ts
```

For Rust cargo tests or binaries:

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
  --arg --nocapture \
  --env RUST_BACKTRACE=1
```

## VS Code Bridge

The companion extension lets a request from the integrated terminal start or
continue a visible VS Code debug session. Install or update it with:

```bash
"$SKILL_DIR/scripts/install_vscode_bridge.sh"
```

Then publish a request:

```bash
uv run --project "$SKILL_DIR" \
  python "$SKILL_DIR/scripts/request_vscode_bridge.py" \
  --workspace /path/to/project \
  --action restart \
  --launch-config-name "Debug failing pytest with $debugger" \
  --break path/to/file.py:123 \
  --local some_var
```

Plainly: the terminal writer creates a request file, the VS Code extension reads
that file inside the trusted workspace, starts or continues the debug session,
queries the stopped adapter for selected locals/watches, and writes a status
artifact back. The bridge does not scrape the Variables pane. It captures
equivalent runtime state through the Debug Adapter Protocol while the visible
session is stopped.

The full operational contract lives in [SKILL.md](SKILL.md); implementation
notes for the bridge live in [references/vscode-bridge.md](references/vscode-bridge.md).

## Proof Standard

A debugger result should say:

```text
Debugger proof:
- Repro: <command/request/test>
- Debugger: <VS Code DAP/debugpy/browser DevTools/pdb/other>
- Breakpoint: <file>:<line> <source line>
- Hit: <yes/no, stopped reason if available>
- Observed: <variable>=<value>, <watch>=<value>
- Human breakpoint: <file>:<line>, expected <variable>=<value>
- Human check: <confirmed/corrected/not-needed>
- Conclusion: <what this proves>
- Next edit: <smallest change justified by the observed state>
```

If the breakpoint did not hit, that is evidence too. Move the breakpoint or
revise the hypothesis; do not pretend the debugger proved the bug location.

## Reusing Prior Debugger Lessons

Prior debugger lessons can help choose breakpoints, but they are not proof for
the current run. The reusable flow is:

```text
fresh debugger proof
    ↓
debugger.proof.v1 validation
    ↓
redacted debugger.lesson.v1 distillation
    ↓
optional memory recall as advisory context
    ↓
new breakpoint proof before patching this bug
```

Use `scripts/distill_debugger_lesson.py` before storing a lesson. It preserves
the useful shape of the paused state while removing raw locals, watch values,
tokens, credentials, and machine-local absolute paths.

Use `scripts/recall_debugger_lessons.py` to normalize memory recall. Its output
is intentionally marked `memory_recall_advisory`, with
`can_satisfy_debugger_proof: false`.

## Verification

Run these from this directory:

```bash
./sanity-proof-schema.sh
./sanity-lesson-distillation.sh
./sanity-memory-recall.sh
./sanity.sh
./sanity-typescript.sh
./sanity-rust.sh
./sanity-e2e-typescript.sh
./sanity-e2e-rust.sh
./sanity-bridge.sh
./sanity-e2e.sh
```

Current bridge safety status:

- covered by deterministic protocol tests: atomic status ownership across
  terminal writer and bridge writer, malformed request quarantine,
  retry-after-pending-race behavior, and custom-output error routing
- residual limitations: compound VS Code session attribution, stronger
  manual-interference docs, and broader symlink/path containment checks for
  future adapters

Do not claim a stronger bridge-proof status than the executed checks and
artifacts support.
