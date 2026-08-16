---
name: ask
description: >
  Use when the user asks to query project memory, ask an oracle, use supported
  browser-backed reviewers, run Tau roundtable/single-handler workflows,
  run persona/deep-review workflows,
  generate image prompts, check OS/project health through composed skills, or run
  an ask DAG. This skill is the executable /ask runtime; do not replace it with
  an informal subagent, plain web search, or hand-written review.
triggers:
  - $ask
  - /ask
  - ask oracle
  - deep review
  - parallel review
  - roundtable
  - persona review
  - CAE gap review
  - browser oracle
  - ask DAG
  - Tau DAG
  - reasoning effort
  - select reasoning level
  - compete
  - bakeoff
  - captcha security evaluation
provides:
  - >
    Executable ask runtime for memory-backed answers, oracle calls, reviews,
    supported browser-backed review, Tau single-handler and roundtable
    workflows, Tau compete/bakeoff workflows, persona workflows, image
    generation, ask/scillm-style DAG runs, and strict Tau DAG runs.
  - >
    Evidence artifacts for each run: request, status, events, and mode-specific
    review outputs.
composes:
  - memory
  - scillm
  - surf
  - captcha
  - subagent-runner
  - browser-oracle
  - create-report
  - tau
  - interview
  - best-practices-roundtable
  - best-practices-competition
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-tau-dag
taxonomy:
  - orchestration
  - retrieval
  - review
  - validation
  - browser
  - resilience
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - mcp__surf__*
  - mcp__browser_oracle__*
disciplines:
  - agentic-orchestration
  - research-retrieval
---

# ask

## Stop First

If the user names `$ask`, `/ask`, an ask mode, oracle, deep review,
parallel review, roundtable, argue, CAE gap review, or ask DAG, read this whole
file before acting. Then use the real runtime entrypoint unless the user
explicitly asks for a fallback or the runtime is unavailable and that fallback
is reported.

Do not substitute `spawn_agent`, a plain model call, a plain web search, a
manual summary, or an invented review for `$ask`.

## Runtime Entrypoint

Run commands from this directory. Pi skill-command syntax such as
`/skill:ask webgpt What is 2 + 2?` is a first-class shortcut: the leading
browser handler (`webgpt`, `webclaude`, `webkimi`, `webgemini`, or `webgrok`)
routes to a Tau `single-call` browser-handler DAG with `--execute --json`. Inline
Pi skill references such as `$ask webgpt What is 2 + 2?` and the spaced natural
language spelling `$ask web gpt What is 2 + 2?` must be treated the same way
(`web gpt` normalizes to `webgpt`). This is only a compatibility shortcut for Pi
users; it must not use the removed direct WebGPT oracle path.

`./run.sh tau-dag "<request>"` maps to the Typer `tau-dag run` subcommand
internally. `./run.sh team-plan "<request>" --team <preset>` renders a
role-based multi-agent plan and frozen Tau DAG preview; execution requires
explicit `--execute --live` (see README "Team Orchestration").

```bash
cd skills/ask
./run.sh --help
./run.sh webgpt What is 2 + 2?
./run.sh webgpt --compile-only What is 2 + 2?
./run.sh ask --help
./run.sh tau-dag run --help
```

Every nontrivial run must preserve the runtime artifacts. The standard artifact
set is:

- `<ask_id>.request.json`
- `<ask_id>.status.json`
- `<ask_id>.events.jsonl`
- mode-specific outputs such as `review.md`, `review.json`, DAG manifests, or
  browser evidence

Runtime artifacts default under `.ask_artifacts/runs/<ask_id>` or the provided
`--run-output-root`. For long, live, or generated runs prefer a storage-backed
root such as `/mnt/storage12tb/skills/ask/outputs/...`. Do not commit generated
ask artifacts.

## One Status Shape For Every Run

```bash
cd skills/ask
./run.sh status --run <run-dir> --projection          # human readable
./run.sh status --run <run-dir> --projection --json   # ask.run_projection.v1
```

One normalized read model over the run's own artifacts, so a roundtable, a
compete run, a browser lane and a scillm-only DAG all answer "what happened?"
the same way.

**Absence is reported, never dropped.** Every node in the frozen DAG appears
even when it produced nothing — that node is the failure worth seeing, not a
row to omit. Across the current 1695-run corpus the projection surfaces 1290
nodes that never created a worker directory and 37 that left output behind
with no receipt; all of them would otherwise be invisible.

Node `stage` is a ladder, not a boolean, because each rung names a different
real failure:

| stage | meaning |
| --- | --- |
| `COMPILED` | in the DAG, nothing else observed |
| `DISPATCHED` | a worker directory exists |
| `ACKNOWLEDGED` | terminal receipt, but not `ok` |
| `CANDIDATE` | output exists that nothing admitted as evidence |
| `SETTLED` | terminal receipt with admitted evidence |

A provider response, pane text, or a zero exit code is never completion
authority on its own: `CANDIDATE` exists precisely so an unadmitted answer
cannot read as success. Generation is read-only and deterministic, so it is
safe on a live run or in a watch loop.

Not yet unified: the legacy `status --run` path reads a different artifact
family and still has its own shape.

## Three Kinds Of Target

`/ask` addresses three peer target types. They differ in transport, not in
standing:

| Target | Example | Transport owner |
| --- | --- | --- |
| **Herdr session** — a live agent in a pane | `memory`, `w11:p13` | `$monitor-herdr` via `herdr pane run` |
| **Model call** — API/model handler | `gpt-5.5-high`, `claude-opus-5-high`, `deepseek-ai/DeepSeek-V3.2-TEE` | `$tau` (SciLLM is internal to Tau) |
| **Web model** — browser-backed reviewer (chat tab, NOT the agentic model; see the `webclaude` warning below) | `webgpt`, `webclaude`, `webkimi` | `$surf` + `$browser-oracle` |

A project agent should not care which side is browser, model, or live session
beyond naming the target.

## Talk To Another Agent's Session (Herdr)

Agents working in different Herdr sessions reach each other by name. Three
verbs, no ids to look up first:

```bash
cd skills/ask
./run.sh herdr list                 # every session you can talk to
./run.sh herdr who memory           # what does this name resolve to?
./run.sh herdr send memory "Please fix graph-memory-operator#105"
```

`NAME` is whatever you already know — a project directory (`memory`), a GitHub
repo (`graph-memory-operator`), or an exact pane id (`w11:p13`). The first two
disagree on this machine: `~/workspace/experiments/memory` *is*
`grahama1970/graph-memory-operator`. Both spellings resolve to the same panes,
so you never have to remember which name a project answers to.

**Ambiguity is refused, never guessed.** Names are not unique — `memory`
currently matches 5 live panes and `agent-skills` 44. `send` stops and prints
the candidates plus a ready-to-paste command:

```
'memory' matches 5 live panes:
  w11:p13 [codex/idle]    /home/graham/workspace/experiments/memory
  w7E:pK  [claude/idle]   /home/graham/workspace/experiments/memory
  w88:p1  [opencode/idle] /home/graham/workspace/experiments/memory
Pick one by pane id:
  ./run.sh herdr send w11:p13 "<message>"
```

When names collide, `send` runs `$interview` and asks which session, listing
**session, model, and directory** for every candidate — the three facts that
tell identical names apart. Answer the question and the message is delivered;
no second command needed.

Exit codes let a caller branch without parsing prose: `0` delivered, `2`
ambiguous, `1` nothing addressable matched. `--json` returns the candidates
instead of interviewing, so a machine caller drives its own disambiguation;
`--no-interview` fails closed on ambiguity.

Two panes are never chosen for you:

- **Dead panes.** No agent attached, or Herdr reports `blocked`/`unknown` —
  that is monitor-herdr's rule, reused here, and it means a human or a wedged
  agent owns the pane.
- **Busy panes.** An agent mid-task is excluded so a message cannot interrupt
  running work by accident. Pass `--busy` when interrupting is the intent.

Delivery goes through `herdr pane run`, the same transport `$monitor-herdr`
uses. A success receipt proves the prompt was *submitted*, not that the other
agent understood or acted on it — treat it as delivery proof only.

**`submitted: true` is herdr reporting on itself.** During development it
returned exit 0 for a pane whose content never showed the message, so confirm
delivery independently with `herdr pane read <pane_id>` when it matters.
`scripts/herdr_e2e_probe.sh` does exactly that and is wired into the agentic
evals as `herdr-live-delivery-readback-e2e`.

**Bidirectional round-trip** is proven separately by
`scripts/herdr_roundtrip_probe.sh` (eval case
`herdr-bidirectional-roundtrip-e2e`): it sends a nonce challenge and waits for
the agent's *reply*, requiring two or more occurrences — one for the echoed
prompt, one for the answer. Counting is harness-agnostic; reply markers are not
(codex renders `›` for input and `•` for output, other harnesses differ).
Round-trip needs a harness that echoes and answers in the pane, so it is
expected to work with pi/codex/claude-style TUIs and to skip elsewhere.

**Some panes report `idle` but are dead.** A blank readback is not about which
agent is running — it is about whether anything is still drawing to the
terminal. A live `opencode` pane spawns a separate TUI child
(`~/.cache/opencode/tui/tui-*`) that renders the screen; the panes that read
back as 0 bytes have the `opencode` process alive with **no TUI child**, so the
screen is genuinely empty and nothing can receive input. Herdr reports both
states as `agent_status: idle`, so status alone cannot tell them apart.

The rule that follows: **a pane whose screen cannot be read is not proven
addressable.** Both probes check readability before sending, which is also what
prevents a message being stranded in a wedged session — the failure mode that
produced `submitted: true` with nothing delivered.

### Never interrupt a pane mid-task

`send` refuses a pane that is still working, and `agent_status` cannot decide
that: Herdr reports `idle` between the turns of an active task, and its pane
record exposes no idle-age field (only agent, status, cwd, and ids). On
2026-08-09 eight probe messages landed in a pane running a ticket-closure job
for exactly that reason.

The signal that works is the screen itself. `is_quiescent()` samples the pane
twice a few seconds apart and treats any change as work in flight — an agent
mid-task redraws, a settled one does not. An unreadable pane counts as busy,
never as free. Pass `--interrupt` when interrupting is the intent.

A composer heuristic was tried and removed: matching the last `>`/`›` line
reads a harness's transcript of the previously submitted prompt as if it were
live input, and flags greyed placeholder hints like `Implement {feature}` as
real text. Delivery is verified after the fact instead of predicted before it.

Two conditions the probes report honestly rather than as `/ask` failures: a
target that received the message but is **out of provider credits** (skip, not
fail), and a `pane run` that types text which the harness leaves **unsent in
the composer** — observed once on a Claude Code pane, where `submitted: true`
was reported for a message still sitting at the prompt.

## Project-Agent Quickstart

Start here when the user asks for a single model call, roundtable, competition,
or creator-reviewer loop. Use one of these shapes; do not invent a custom
orchestration path.

| User intent | Command shape |
| --- | --- |
| One handler answers | `./run.sh tau-dag "<task>" --repo <repo> --target <target> --immutable-goal "<goal>" --handler <handler-or-model> --execute --json` |
| Roundtable | `./run.sh tau-dag "<shared task>" --repo <repo> --target <target> --immutable-goal "<goal>" --dag-template roundtable --handler <a> --handler <b> --topology concurrent --execute --json` |
| Competition | `./run.sh compete "<isolated task>" --repo <repo> --target <target> --immutable-goal "<goal>" --handler <a> --handler <b> --criterion <criterion> --execute --json` |
| Creator then reviewer | `./run.sh tau-dag "<creator task then reviewer verdict>" --repo <repo> --target <target> --immutable-goal "<goal>" --dag-template creator-reviewer --handler <creator> --handler <reviewer> --topology sequential --execute --json` |

Handlers are peers even when their transports differ. Browser handlers
(`webgpt`, `webclaude`, `webkimi`, `webgemini`, `webgrok`) run through `$surf`
and `$browser-oracle`. API/model handlers such as `gpt-5.5-high`,
`gpt-5.5-xhigh`, `claude-opus-5-high`, or
`chutes deepseek-ai/DeepSeek-V3.2-TEE` are routed by Tau. Project agents should
not care which side is browser or API beyond naming the handler.

### Reasoning / Effort Selection

For Tau handler DAGs, choose reasoning effort as part of the non-browser
handler selector unless the runtime exposes a future explicit effort flag. The
current supported Ask handler grammar is:

```text
<exact-model-id>-<effort>
```

Current Ask/Tau handler suffixes are `low`, `medium`, `med`, `high`, and
`xhigh`. `med` normalizes to `medium`. `xhigh` is preserved as the requested
selector, but the current SciLLM adapter dispatches it as `high` and records the
downgrade. Do not use `max` as an Ask handler suffix unless a future local
`./run.sh tau-dag run --help` shows an explicit supported flag and the emitted
receipts prove the applied effort.

Use exact dynamic model ids from the provider/SciLLM catalog as the model part.
For Claude, that means names such as `claude-opus-5`,
`claude-sonnet-4-6`, or `claude-fable-5`, with the effort suffix appended when
needed:

```bash
./run.sh tau-dag "Review this bundle" \
  --repo local/agent-skills \
  --target ask-review \
  --immutable-goal "Return a receipt-backed review with explicit blockers." \
  --handler claude-opus-5-high \
  --execute --json

./run.sh tau-dag "Compare these repair options" \
  --repo local/agent-skills \
  --target ask-roundtable \
  --immutable-goal "Each seat returns a usable position or a blocker." \
  --dag-template roundtable \
  --handler claude-sonnet-4-6-medium \
  --handler gpt-5.5-xhigh \
  --topology concurrent \
  --execute --json
```

Do not invent partial aliases such as `opus-5-high`, `sonnet-high`,
`claude high`, or `webclaude-high`. `webclaude` is a browser chat tab and has no
Ask-controlled reasoning effort. If the human asks for "Claude Opus 5 max" and
the current Ask runtime has no supported `max` selector, fail closed unless the
human explicitly accepts the highest supported Ask selector
(`claude-opus-5-xhigh`) and the report states that `xhigh` dispatches as `high`
in the current SciLLM adapter.

Every executed API/model lane must preserve the effort evidence in the emitted
Tau artifacts. Inspect the command spec and node receipt for:

- `requested_model`: the exact selector the caller requested, such as
  `claude-opus-5-xhigh`
- `model`: the resolved model id dispatched to SciLLM, such as `claude-opus-5`
- `requested_reasoning_effort`: the requested suffix, such as `xhigh`
- `reasoning_effort`: the effort actually dispatched, such as `high`
- `reasoning_downgrade_reason`: required when requested and dispatched effort
  differ

For non-Tau oracle synthesis (`./run.sh ask ... --oracle`), reasoning is chosen
with `--oracle-reasoning <low|medium|high|xhigh>` and defaults to `high`
(`xhigh` for deep review). This is a different path from Tau handler selection.

For executed roundtables and competitions with browser handlers, Ask defaults to
`--browser-tab-lifecycle auto`. Auto creates one Chrome window, creates one tab
per requested browser handler, binds temporary browser-oracle projects, runs
Tau, and closes only that Ask-created window. The project agent does not need to
pre-create tabs or pass `--handler-project` for normal web seats. Use
`--browser-tab-lifecycle fresh-keep` only when a human needs to inspect the tabs
after the run. Use `--browser-tab-lifecycle reuse-bound` only when the human
intentionally wants the same long-lived provider tabs to keep their conversation
context across the whole roundtable or competition; preflight every named tab
before submission and keep the same binding for every round.

### Live evals: the contract is honesty, not a fixed answer

```bash
skills/ask/run.sh live-seat-probe claude-opus-4-8-high
skills/ask/run.sh live-seat-probe claude-fable-low     # exercises self-recovery
skills/ask/run.sh live-seat-probe webgemini
```

Deterministic tests over local functions proved nothing about whether `/ask`
works: every real defect this session came from a live run, and none from a
test. These cases call real providers, so they are non-deterministic by design.

A live provider may answer, rate limit, or stall, and none of that is under our
control. Asserting a fixed answer would go red whenever a provider is merely
busy, and everyone would learn to ignore it. So the contract is:

> a seat either answers with real content, or names why it did not.

Both outcomes pass. Three things fail, whatever the provider was doing:

| violation | why it matters |
| --- | --- |
| `PASS` with zero response bytes | a green run that produced nothing |
| a non-PASS status with no `failure_code` | a dead end nobody can act on |
| a different model answered, unrecorded | a reply that looks fine and silently came from elsewhere |

The third caught a real bug minutes after the rate-limit fallback was added:
the receipt read `claude-fable-low PASS` while `claude-opus-4-8` had written the
answer. The substitution is now recorded in the node receipt:

```json
"rate_limit_fallback": {
  "from": "claude-fable-low", "to": "claude-opus-4-8-high",
  "reason": "provider_rate_limited"
}
```

A timeout is a named outcome, not a violation — that is exactly the
non-determinism these accept.

### Auditing a panel against the best-practices contracts

```bash
skills/ask/run.sh panel-audit <run-dir> --mode roundtable
skills/ask/run.sh panel-audit <run-dir> --mode compete
```

`best-practices-roundtable` and `best-practices-competition` state rules that
decide whether a panel's output means anything. They lived only in prose, so
"this run complied" was an assertion nobody could check. This reads a finished
run directory and answers from artifacts:

| check | rule |
| --- | --- |
| `equal_context` | every seat received the same task body |
| `seat_status` | every seat accounted for from its own artifacts |
| `no_silent_consensus` | no agreement claimed over a seat that never answered |
| `isolation` | no candidate was shown a rival's response |
| `competition_outcome` | two candidates **answered**, and no winner without evidence |

Equal context is measured on the task body, not raw bytes: `Handler:`,
`Model:`, `Seat:`, `node_id:` and `Browser model preference:` are per-seat
addressing and may differ. Everything else that differs is a tailored packet.

`competition_outcome` counts candidates that **answered**. A run that dispatched
two seats and received one is a single opinion; the live run on 2026-08-16 did
exactly that while its scorecard read `candidates: 2`, and stayed honest only
because it also reported `NEEDS_ATTENTION`.

### The preferred seat roster

Five browser providers plus the local Claude lane:

```
webgpt  webgrok  webkimi  webdeepseek  webgemini  claude-fable-low
```

with **`claude-opus-4-8-high`** as the fallback when Fable is rate limited.

Spread matters because providers rate-limit independently. Measured 2026-08-16:
`browser-availability` reported webgpt `limited: true` on both its tabs while
webgpt was, at that moment, the only browser seat that worked at all. A panel
drawn from one or two providers is one rate limit away from no panel.

`claude-fable-low` is the local Fable 5 lane at low reasoning effort; it needs
no browser, no tab, and no Chrome contention, and it carries a real reasoning
selector. Both ids resolve through the SciLLM route table:

```
claude-fable-low      -> claude-fable-5   effort=low
claude-opus-4-8-high  -> claude-opus-4-8  effort=high
```

**`webclaude` is not in the roster.** It is a claude.ai chat tab: no tools, no
repo access, no Ask-controlled reasoning effort, and one more seat competing for
the same Chrome. It stays reachable by explicit name and is always ordered last.
Live-web questions still lead with a browser seat, since a chat tab with search
is better at those than a local model without one.

The roster lives in `PREFERRED_PANEL_ROSTER` and is eval-gated, including a case
that fails if a roster seat has no launch URL.

### When a web seat is rate limited

Rate limits and unavailability are reported explicitly — `browser-availability`
names the provider, and `browser-provider-selection.json` records
`removed_handlers` with a `failure_code`. A limited provider is **removed** from
the roundtable, competition, or MVP rather than retried into a timeout.

The seat is then refilled by that provider's **local same-family equivalent**,
not by another copy of whatever is left:

| removed seat | local family |
| --- | --- |
| `webkimi` | `kimi` |
| `webdeepseek` | `deepseek` |
| `webgemini` | `qwen` |
| `webgrok` | `glm` |
| `webgpt` | `qwen` |

Family-for-family preserves the diversity a panel exists for; collapsing every
removed seat onto one model produces a panel that agrees with itself.

Build selection inside a family is capability-driven:

- **text question → `flash`.** Reaching for `pro` by default spends the capable
  build on work that never needed it.
- **multi-modal question → `pro`**, selected by asserting `image`/`pdf` input
  support against the live catalog. A multi-modal question can never land on a
  text-only build; if no configured model supports the input, the substitution
  returns nothing instead of answering blind.

Model ids come from the live OpenCode Go catalog, so preference lists may name
a build that does not exist yet — `opencode-go/kimi-k3` sits ahead of `k2.6` and
is simply skipped until scillm reports it. That is how a newer model is
preferred without inventing a working name.

### Prefer the local Claude lane over webclaude

Handler preference for Claude work, in order:

1. **`claude-fable-low`** — local Fable 5 at low reasoning effort. Preferred
   outright.
2. **`claude-opus-4-8`** — when Fable is rate limited.
3. **`webclaude`** — last resort only.

`webclaude` is a claude.ai chat tab: no tools, no repo access, no Ask-controlled
reasoning effort, and one more seat competing for the same Chrome. The local
lane answers the same questions with effort control and no browser at all.
Live-web questions still put a browser seat first, since that is what a chat tab
is actually better at.

This ordering lives in `WEBCLAUDE_PREFERRED_SUBSTITUTES` and is eval-gated.
Before it, the fallback list filtered to browser names only, so every Claude
fallback was forced onto a chat tab by construction.

### Unblocking: one singular MVP, or nothing

A spiralling agent does not need more options. It needs exactly one small thing
that demonstrably moves the wall, chosen by somebody other than itself.

```bash
skills/ask/run.sh unblock                                  # compile from the top open blocker
skills/ask/run.sh unblock --target T --failure-code F      # a specific wall
skills/ask/run.sh unblock ... --execute                    # dispatch isolated candidates
skills/ask/run.sh unblock --judge resp.md --run-proof      # score responses
```

It reads the open blocker from the ledger, grounds it with `/brave-search`
(queries built from the recorded `failure_code` and message, never from the
agent's own theory — that framing is what produced the spiral), and competes it
across isolated browser models that run their own web search. Candidates never
see each other: two models that read each other converge into one, and the
whole point is an outside view.

**The gate that does the real work: `PROOF_COMMAND` must fail right now.**

That single requirement kills the failure class this exists for. Work produced
to avoid a blocker has a proof that passes immediately — tests over your own
code, contracts for a path that never runs, a suite that was already green
while the wall stood. If a proposal's proof already passes, it does not address
anything currently broken, whatever its prose claims. `--run-proof` executes it
and requires a non-zero exit before the proposal can win.

Singularity is enforced mechanically, not requested politely, because "keep it
minimal" in a prompt is advice and advice is what an agent under pressure
rationalises away. Refused: a second deliverable (`and also`, `follow-up`,
`phase 2`), more than one change surface, a chained proof command, and a
whole-suite proof such as bare `pytest` or `./sanity.sh`.

If no candidate returns a singular proposal with a proof that fails now, the
result is `NEEDS_ATTENTION` and no winner. An unblocking step that does not
unblock is the spiral, not the exit. "This needs a human decision or an
upstream change" is an explicitly valid answer — without that escape the
candidates invent a fix.

### Blocked, or avoiding the blocker?

Ask emitted `BLOCKED` in 58 places and persisted **none** of it across runs, so
a blocker lasted exactly one process. That is why nothing could ever detect the
failure this guards: hit a wall on the load-bearing part, do not say "blocked",
and produce a stream of defensible deterministic work beside it -- tests over
your own code, contracts for a path that cannot run, greps instead of the live
call. Every artifact real, none of them touching the wall.

`goal-drift` cannot see this and is not meant to. It grades work against the
registered human goal, and this work *serves* the goal; it is the hard half
being routed around. goal-drift reports clean, exactly as the knowledge-drift
auditor did in the incident goal-drift itself was written for.

```bash
skills/ask/run.sh drift blockers                  # what is still in the way
skills/ask/run.sh drift check <target> --work "…" # was work done beside it?
skills/ask/run.sh drift acknowledge <target> <failure_code>
skills/ask/run.sh drift clear <target> <failure_code> --live-proof "…"
```

The ledger (`~/.ask/blockers.jsonl`) is written at Ask's own execution choke
point, not by an agent choosing to file a report -- the agent this detects is
by construction the one who would not have filed it. Identity is
`(target, failure_code)`, so one wall hit three times is one blocker.

Verdicts:

| verdict | meaning |
| --- | --- |
| `AVOIDANCE_DRIFT` | work landed on a target whose blocker is open and unacknowledged, and that work states its own live path did not run |
| `BLOCKED_DECLARED` | the blocker was acknowledged, attempted live, or nothing was built beside it — the honest cases |
| `CLEARED` | closed with live proof |
| `CLEAN` | no blocker, or no claim of a missing live path |

Two rules keep it honest. **Clearing requires live proof** — "it should work
now" is what an avoiding agent also says. **Attempting and failing is never
drift** — the detector must never punish going at the wall and losing.

The tell it keys on is the agent's own words. The output contract already
forces a statement of what was live and what was fixture-backed, so an avoiding
agent writes its own indictment voluntarily; selecting what to work on is
easy to rationalise, fabricating a live run is not.

Limitations, stated because they change how you read a verdict: it matches
phrases, so novel wording for "I did not run this live" slips through, and it
assesses whatever work items you hand it — feeding one commit that mixes
live-proven and fixture-only work yields a single coarse verdict. It reports
and never gates; a detector that can block work becomes one more lane to drift
into.

### Which model actually answered

Every browser lane receipt carries a `model_provenance` block. Ask requests a
reasoning tier (`Pro` by default) but Surf cannot always confirm the dropdown
took, and before this the receipt recorded `model: null` for every browser
handler -- so a panel could ask three seats for `Pro` and leave no evidence of
what answered.

`provenance_status` is one of:

| value | meaning |
| --- | --- |
| `confirmed` | an observation matched the request; `reasoning_proven: true` |
| `unconfirmed` | a tier was requested and nothing confirmed it -- the shape a silently-failing dropdown produces |
| `mismatch` | the provider was observed on a different tier than requested |
| `selection_failed` | Surf reported a selector error |
| `not_requested` | no tier was asked for |

Absence of evidence is never confirmation. Read `reasoning_proven` before
claiming a panel ran at a given tier; every real webgpt receipt on disk as of
2026-08-16 reads `unconfirmed`.

### Reclaiming finished runs

```bash
skills/ask/run.sh prune-outputs            # dry-run
skills/ask/run.sh prune-outputs --apply
```

Installed daily at 05:41. `run_state.prune_runs` covers runtime runs; this
covers the DAG output tree, a different directory shape it could not see --
which is why that tree reached 2.2 GB across 332 runs with nothing pruning it.

It removes a directory only when it carries `dag.json` or `compile-status.json`,
its newest file is older than 14 days, and any `execution-status.json` is
terminal. A non-terminal run is pinned regardless of age: a BLOCKED run is the
evidence for why it blocked. A stale `webgpt_inflight.json` is not liveness --
1,226 of them exist because completed submits leave the marker behind.

### Who owns a window Ask opened

Every window Ask causes to exist is recorded in `~/.ask/browser-windows.jsonl`
with the owning pid and a creation time. That ledger, not the lifecycle
receipt, is what makes a window closable later: closing was never the broken
part, ownership was. Measured 2026-08-14, 9 provider windows were open and none
appeared in any of 351 `browser-tab-lifecycle.json` receipts, because the
roundtable worker's recovery paths (`--create-tab`, `open-bind`) create windows
below the lifecycle layer. They now register through `ask.browser_windows` at
the transport choke point, so a window is claimed the moment it exists.

Three things close a window, in order of preference:

1. **In-run teardown.** A `fresh-temporary` run closes its own seat windows when
   Tau finishes. This works and always did.
2. **Provisioning-time reap.** The next Ask run reclaims windows whose owning
   process is gone and whose TTL has passed.
3. **The cron backstop**, for when there is no next run:

   ```bash
   skills/ask/run.sh reap-windows           # dry-run
   skills/ask/run.sh reap-windows --apply
   ```

   Installed at `*/30`. It closes only ledger-owned windows, and only when the
   owner is dead AND the TTL has passed -- both conditions, never either. A live
   owner means a run is still using the window; a young entry means a run may
   have died holding output that exists only in-tab.

TTLs by mode: `fresh-temporary` 15 min, `fresh-keep` 4 h, `pending-recovery`
12 h. Retention is an obligation with a clock, not an exemption -- 28 of those
351 receipts sat at `cleanup_status: skipped_pending_recovery`, keeping a window
open for a recovery nobody ever performed.

For tabs bound through `~/.pi/<backend>-projects/ask-*.json` rather than
windows, `skills/ask/run.sh close-stale-tabs` is the matching reaper.

Ask-created browser seat windows land on **Desktop 2** (wmctrl index 1). They
are reviewer windows Ask provisioned, not windows the human asked for, so they
belong on the reviewer desktop rather than on top of current work. Override with
`ASK_REVIEWER_DESKTOP=<index>`; set it empty to disable placement and leave
windows wherever Chrome puts them.

Placement is cosmetic and never fails a run. It reuses `browser-oracle
place-window` — the same logic `open-bind` uses — rather than reimplementing
it, because two details there are easy to get wrong: wmctrl output order is not
creation order (a last-sorts heuristic moved the wrong window), so the window is
identified by diffing a snapshot taken before creation; and `wmctrl` returning 0
does not mean the move stuck, because KDE can bounce a freshly-mapped window
back to the active desktop, so the move is verified by readback and retried.

Pass local evidence a browser seat must actually see with `--attach-file <path>`
(repeatable) on `tau-dag run` or `compete`. Ask forwards each file to Surf as
`--attach-file` for browser handlers and records `requested_attachment_paths`
plus `browser_attachment_paths` in the node receipt. A missing file or a handler
that cannot attach fails the lane closed rather than answering from prose.
Attachment delivery needs an extension build that handles
`AI_UPLOAD_FILE_TO_TAB`; older extensions reject the upload and the lane reports
`browser_submit_not_accepted` with that message.

### How old is this tab?

Stale reviewer tabs are the usual cause of a browser lane that used to work:
conversation state accumulates, rate-limit banners persist, and bindings drift.
Check age before blaming the transport.

```bash
cd skills/surf
./run.sh tab.age                  # every tab, oldest first
./run.sh tab.list --with-age      # ages on a normal listing
```

Read `age_source`, not just the number. `observed` is accurate; `at_least`
(shown with a `>=` prefix) means the tab predates the ledger and its real age
is unknown — Chrome exposes no creation time, so age is observed and
remembered, never read from the browser. `$surf` owns the ledger and the
contract; see its **Tab Age** section.

For a lane that is failing, the useful sequence is age first, then
`lane-diagnostics.json`, then the provider receipt — an old tab explains more
failures than anything in the code path does.

Browser providers do not share one payload contract. Before building or
repairing a browser roundtable packet, apply this matrix:

| Handler | Preferred review payload | Attachment rule | Explicit gotcha |
| --- | --- | --- | --- |
| `webgpt` | Short prompt plus one readable bundle | One attachment only; zip is allowed when the task needs a bundle | Multiple attachments fail before submission. Do not infer file creation from prose; download and verify generated artifacts. |
| `webgemini` | Short prompt plus one readable Markdown/text bundle | Ask inlines Markdown/text bundles for current Gemini tabs; do not rely on upload unless Surf records attachment metadata | Current Gemini UI may expose `Upload & tools` without an `input[type=file]`; stale page text can look like a response if sentinel capture is not strict. |
| `webkimi` | Short prompt plus one plain readable Markdown/text bundle | Do not use zip; Ask passes the Markdown/text bundle through Surf `kimi.submit --attach-file` | Kimi's Lexical composer can corrupt large inline payloads; do not paste or inline full review bundles into the composer. |
| `webclaude` | Prompt plus readable files | Multiple attachments are supported | Claude can stage a prompt without submitting it; require submit-acceptance and sentinel proof, not only a prepared prompt file. |
| `webdeepseek` / `deepseek` | Inline text or short prompt only | Attachments and zip files are unsupported | If local evidence is required, route through another handler or summarize the evidence into the prompt within size limits. |

Do not automatically convert every evidence set into a zip. For one-attachment
providers, choose the provider-compatible single file: usually Markdown for
Kimi and README/code review packets, and inline Markdown/text for Gemini when
the current tab lacks a file input; zip only when the provider is known to
accept it and the task actually needs an archive.

Failure classification must use the Ask browser failure-code registry in
`scripts/tau_roundtable_worker.py`, not bespoke prose. A lane is usable only
when its node receipt has `ok: true`, a non-empty response, and provider-specific
sentinel/attachment proof in metadata. `.submitted.md`, prepared prompts,
scheduler `node_completed`, and an Ask/Tau process exit code are not provider
acceptance proof.

Provider recovery must also be provider-specific. Ask must never turn a failed
browser lane into a generic `surf read`, `surf text`, page-text scrape, or
cross-provider extractor. If a submitted WebGrok lane misses the sentinel, the
recovery packet must name `surf grok.extract`; WebGPT uses
`surf webgpt.extract`; Gemini uses `surf gemini.extract` where applicable.
Handlers without a provider-owned extractor must fail closed with a ticket
instruction instead of pretending a generic page read is equivalent.

Browser lanes queue on the shared Surf browser lock. Ask derives the wait from
handler count and topology; pass `--browser-lock-timeout <seconds>` on `tau-dag
run` or `compete` to widen it for a busy browser. The resolved value is recorded
as `lock_timeout_seconds` in `browser-tab-lifecycle.json` and reaches each
browser handler's dispatch command.

After execution, read the returned `run_dir` and inspect:

- `dag.json`
- `command-specs/<node>/tau-dispatch-command.json`
- `node-artifacts/handler-*/node-receipt.json`
- `node-artifacts/handler-*/response.md`
- `node-artifacts/handler-*/browser-recovery-packet.json` when present
- `node-artifacts/handler-*/handler-recovery-packet.json` when present
- `node-artifacts/join/node-receipt.json` for roundtable
- `node-artifacts/join/compete-scorecard.json` for competition

Treat `PASS` as model/reviewer evidence only. Local closure still requires the
project's deterministic proof command or artifact validation. Treat `DEGRADED`,
`NEEDS_ATTENTION`, and provider rate limits as lane-local states: keep usable
peer receipts, read the recovery packet, and rerun only the affected lane or
launch a new round when appropriate.

Before launching a costly live browser panel, Ask runs a standard read-only
provider availability probe automatically. It inspects existing provider tabs
for visible rate-limit or capacity banners and writes
`<run_dir>/browser-provider-availability.json`; it does not submit prompts. If
the report is `ERROR`, or `NEEDS_ATTENTION` without specific provider cooldown
metadata, Ask exits before creating fresh browser tabs or dispatching Tau, with
`blocked_reason: browser_provider_unavailable_preflight`, `failure_code`, and
`next_command` in the top-level execution receipt. If `NEEDS_ATTENTION` names
provider-limited lanes, Ask treats that as lane-local: it records
`limited_providers` and `cooldown_policy` in the availability artifact, writes
`<run_dir>/browser-provider-selection.json`, removes unavailable requested
providers, and selects the next best available browser provider when the
workflow still has enough participants. WebGPT cooldowns opt the WebGPT worker
into one bounded Surf retry after 300 seconds only when that WebGPT lane is
still intentionally run.

Project agents can also run the same probe manually before a planned panel:

```bash
./run.sh browser-availability \
  --provider webgpt \
  --provider webclaude \
  --provider webkimi \
  --provider webgemini \
  --output /tmp/ask-provider-availability.json \
  --json
```

If this probe returns `ERROR` with `recovery_kind:
surf_stale_socket_no_listener`, `/tmp/surf.sock` exists but no Surf native host
is listening. This is local browser transport failure, not WebGPT provider
throttling. Follow the reported `next_command`; if it repeats, collect
`browser-provider-availability.json`, `/tmp/surf-host.log`, the native host
manifest, and `ss -xlpn | grep /tmp/surf.sock`, then file a `$ticket` to
`$surf`. Do not launch a browser roundtable, retry provider lanes, or classify
the failure as provider cooldown until Surf `tab.list` works again.

If the report is `NEEDS_ATTENTION` with `cooldown_policy.status:
LANE_LOCAL_RETRY`, do not cancel healthy peers. Treat only the named providers
as cooling down, preserve the policy, and use the adjusted handler list from
`browser-provider-selection.json`. If Ask cannot keep enough participants after
filtering unavailable providers, it exits with
`blocked_reason: browser_provider_selection_insufficient_participants`. This
preflight is not completion proof; it only prevents obvious provider throttle
loops from becoming whole-panel failures.

Failures must be non-silent. A failed browser/API/subagent lane must expose
`failure_code`, `recovery_packet_path`, `next_command` or an explicit
fail-closed reason, and `ticket_instruction`. If a recovery packet is missing,
misclassified, hides Surf/CDP/SciLLM stderr, gives no actionable recovery, or
still blocks the project after its recovery instruction is followed, file a
`$ticket` to `$ask` at `agent-skills@main`. Include the Ask `run_dir`,
`dag.json`, the failing node receipt, recovery packet, `response.meta.json`,
raw response, and exact command stderr.

## Required Behavior

### Diagnose from receipts first, then `/debugger` (operator 2026-08-04)

The full ladder lives in `$debugger` ("The escalation ladder"). In short:
dispatch on the symptom to the ONE artifact that owns it, escalate to a
breakpoint only when no artifact explains it, and escalate to `$brave-search`
or `$dogpile` only when the observed state is real but its meaning is unknown.
After two failed focused attempts the research rung is mandatory — a third
attempt from the same stale context is not a retry, it is a guess.

When an Ask run fails, read the run directory before forming a theory. Every
large diagnosis on 2026-08-03/04 was already named by a receipt field, and
inference over source produced a patch for a bug that did not exist.

| Symptom | Read this first | It names |
| --- | --- | --- |
| Lane NEEDS_ATTENTION | `node-artifacts/handler-*/node-receipt.json` | `status`, `failure_code` |
| Recovery did not help | `node-artifacts/handler-*/lane-recovery.json` | every rung, or `recovery_budget_exhausted` |
| Lane has no response | `browser-recovery-packet.json` | `failure_code`, `next_command` |
| Panel blocked pre-dispatch | `execution-status.json` → `receipt.alerts` | the exact Tau verdict |
| Seat missing from results | `browser-provider-selection.json` | `removed_handlers` |
| Provisioning blocked | `browser-tab-lifecycle.json` | `failure_code`, `identity_guard`, per-command stderr |
| Contract rejected at compile | `compile-status.json` | `tau_contract_validation` |

**Read a Tau contract violation in full — it is not just a message.** A
`tau.dag_error.v1` payload (pre-dispatch rejection) carries `verdict`,
`failure_code`, `severity`, `evidence.errors[]` naming the exact cause in plain
language, `evidence.primary_alert`, and `recommended_action` with `type`,
`next_agent`, and `reason` — Tau states the next step explicitly. A runtime
block instead puts its detail in `receipt.alerts[]`, each with `code`,
`message`, and an `evidence` object identifying the node and handler. Read every
one of those fields before theorising: `execution_profile_override_broadens_policy:max_concurrency`,
`limits.max_parallel_nodes is not allowed outside extensions`,
`evidence_goal_hash_missing`, and `join_requires_multiple_inputs` each named
their own fix precisely, and each was a real defect.

Only after a receipt fails to explain the behavior, and two focused attempts
have failed, invoke `$debugger`: set a breakpoint in the Ask code path, run the
reproduction, and inspect the paused frame **before** editing. Do not point a
breakpoint harness at a live browser lane — it will sit blocked on Chrome. Use
`surf js --tab-id <id> --no-activate` for live page state instead.

- Build a concrete bundle before review or oracle escalation: objective, target
  files/artifacts, commands already run, uncertainty, exact question, and
  acceptance gates.
- For human requests that ask a named handler/model to answer, solve, review, or
  collaborate, use `./run.sh tau-dag ...` as the modern front door. `$ask`
  compiles the request into a strict `tau.dag_contract.v1` bundle, emits
  `dag.json` before execution, uses `$interview` when required DAG fields are
  missing, and delegates execution and live status/viewer polling to `$tau`.
- Treat modern roundtable and creator-reviewer loops as prompt-to-Tau-DAG. The
  user should only need to name handlers and shape: single call, concurrent
  roundtable, creator-reviewer pipeline, compete/bakeoff, or explicit
  multi-step DAG. It must not matter to the user whether a handler is
  browser-backed or API-backed except for the handler/model name they request.
- Roundtable, creator-reviewer, and compete/bakeoff handler DAGs require an
  explicit immutable goal or acceptance bar. Pass it with `--immutable-goal` or
  label it in the request as `Immutable goal:`, `Acceptance bar:`, or
  `Stop condition:`. If it is missing, `$ask` must fail preflight with
  `NEEDS_INTERVIEW` before any browser or API handler is contacted. The same
  immutable goal is shared with every participant and included in the Tau goal
  hash.
- For substantial roundtables, apply `$best-practices-roundtable` as the
  leadership contract: equal shared context, concurrent seats, attributed
  dissent, research between rounds, and executable slices before local proof.
- For substantial compete/bakeoff workflows, apply
  `$best-practices-competition`: isolated candidates, identical task packets,
  local feature verification, evidence-backed winner selection, and
  winner-only continuation until the immutable goal is met. Treat iterative
  competitions as dynamically expanding Tau DAGs, or as linked next-round DAGs
  under the same immutable goal hash when the installed runtime cannot append
  nodes in place. Do not share participant information between candidate lanes
  or rounds; help each lane only with its own review, local evidence, and
  permitted research tools.
- Pass the bundle to the documented ask mode. Do not compress a review target
  into an informal prompt when the mode has a target option.
- Report artifact paths as evidence. Browser reviewers or model
  reviewers are not deterministic proof by themselves.
- Direct WebGPT/ChatGPT oracle routing is not an `$ask ask` backend: `$ask
  webgpt`, `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
  `webgpt-project` must fail closed. This does not ban Tau roundtable
  `webgpt`: `webgpt` is a supported Tau browser handler routed through `$surf`.
- Close only from local deterministic proof appropriate to the task: tests,
  schema checks, endpoint responses, screenshots, database/query evidence, or
  generated artifact validation.
- Fail closed when tab binding, target file, reviewer configuration, browser
  state, or runtime artifact creation is missing.
- Use readiness language when proof is incomplete: `NOT_READY`,
  `NOT_ESTABLISHED`, `NEEDS_ATTENTION`, or `BLOCKED`, with the missing proof
  named explicitly.
- Provider/model execution in generated Tau DAGs is Tau-owned: `$ask` emits
  local adapter nodes and Tau dispatches their command specs; those adapters
  call the `$scillm` container service (`http://127.0.0.1:4001` by default).
  Real provider calls require explicit `--allow-provider-calls`. Use
  `--local-fixture` only for Tau scheduler sanity proof; report that it does
  not prove provider/model behavior.

## Single Calls And Roundtables

Use `./run.sh tau-dag` for current handler/model orchestration.

- **Template selector**: prefer `--dag-template <name>` or its alias
  `--pattern <name>` when the user names a known agentic shape. This keeps
  project agents from manually translating prose into `--topology` and
  `--workflow-mode`. Supported Ask-side templates are:

| Template | Shape Ask emits now |
| --- | --- |
| `single-call` | One handler node plus join/human terminal |
| `prompt-chain` | Sequential handler pipeline with prior receipts |
| `creator-reviewer` | Sequential creator then reviewer; pass/fail requests require verdicts |
| `reflection-loop` | Sequential draft/review/revise-style receipt chain |
| `roundtable` | Concurrent handlers with equal shared context and join |
| `compete` | Concurrent isolated candidates with compete evaluator join |

  Recognized but not yet executable Ask-side templates such as `tool-use`,
  `rag-review`, `human-approval`, `exception-recovery`, `priority-queue`, and
  `exploration-research` fail closed with `NEEDS_INTERVIEW` and a recovery
  packet that points to the Tau native-template work. Do not simulate those
  templates in prompt prose.
- **Single call**: use one Tau handler or one solver/reviewer model. This is the
  path for "ask webclaude", "ask webkimi", "ask webgemini", "ask webgpt", or one
  API-backed model such as `gpt-5.5`, `claude-sonnet-4-6`, or another model
  routed by `$tau` through `$scillm`.
- **Roundtable (deliberation panel)**: repeatable `--handler` values with
  `--topology concurrent` - ALWAYS concurrent; see the Roundtable
  Collaboration Protocol below. Equal context demands that every seat answers
  the same shared prompt; a sequential chain is a PIPELINE, not a roundtable.
  Compiles to `tau.dag_contract.v1` with handler nodes and a join node.
- **Compete / bakeoff (isolated candidates)**: use `./run.sh compete` when the
  user wants multiple web/API handlers to solve the same task in isolation,
  then have the project agent compare the results, harvest only locally
  verified features after N rounds, pick a clear winner when the evidence
  supports one, and continue iterating with the winning participant until the
  immutable goal is met. This is NOT a roundtable: competitors do not see each
  other's output during candidate isolation. Browser handlers and `$scillm`
  model names are mixed with the same `--handler` flag.
- **Creator-reviewer loop (pipeline, not a roundtable)**: use `--topology
  sequential` and list the creator handler first, then reviewer handlers. Downstream handlers receive prior
  handler receipts and response excerpts. If the request asks for pass/fail
  review, the reviewer prompt requires `VERDICT: PASS`, `VERDICT: FAIL`, or
  `VERDICT: NEEDS_ATTENTION`.
- **Explicit DAG**: describe the dependency order in the request when the user
  wants multiple steps. Use `--topology sequential` for a linear handler chain;
  use `--topology concurrent` when handlers can work independently before join.
- **Supported browser handlers**: `webgpt`, `webclaude`, `webkimi`,
  `webgemini`, and `webgrok`. Browser aliases normalize as `gpt -> webgpt`,
  `kimi -> webkimi`, `gemini -> webgemini`, and `grok -> webgrok`. Spell
  `webclaude` explicitly for the claude.ai browser tab; bare `claude` is the
  agentic SciLLM Claude alias, not the browser seat.
- **WARNING - `webclaude` IS NOT agentic Claude** (operator, 2026-08-12).
  `webclaude` is a claude.ai CHAT TAB: no tools, no filesystem or repo access,
  no Ask-controlled effort, a different system prompt and context regime. It is
  a browser REVIEW seat only. For agentic Claude, use a SciLLM Claude handler
  such as `claude-fable-5-high`, `claude-sonnet-4-6-high`, or
  `claude-opus-5-high` executed inside the Tau DAG. The bare `claude` alias maps
  to the default agentic SciLLM Claude handler, currently `claude-fable-5`; do
  not use it when the requested lane must specifically be Opus or Sonnet. Direct
  `claude -p` subprocess calls are reported as degraded and are not a substitute
  for Ask/Tau receipts.
- **Supported local/API handlers**: explicit non-browser handler labels are
  routed by Tau according to their transport. SciLLM-compatible model labels
  use exact model ids plus optional effort suffixes, such as `gpt-5.5-high`,
  `claude-opus-5-high`, or `claude-sonnet-4-6-medium`, and emit Tau-owned
  `scillm.chat` adapter nodes. OAuth/Codex subagent selectors such as
  `gpt-5.5-xhigh` emit Tau-owned `subagent-runner.codex_exec` nodes and
  preserve `xhigh` as the requested reasoning effort. For Chutes exact models,
  project agents may write
  `chutes <provider/model>: <prompt>`; `$ask` canonicalizes that to one API
  handler with `provider_hint=chutes` before Tau writes the DAG. Do not pass
  the transport prefix as the model id: use `deepseek-ai/DeepSeek-V3.2-TEE`,
  not `chutes/deepseek-ai/DeepSeek-V3.2-TEE`.
  Mixed web/API panels may use natural concurrent syntax:
  `concurrently webgpt, webclaude, webkimi and chutes deepseek-ai/DeepSeek-V3.2-TEE <prompt>`.
- **Subagent versus Codex workspace lane**: `--handler gpt-5.5-xhigh` is an
  answer/review subagent call through Tau and `/subagent-runner`; it is
  non-mutating and does not require a workspace binding. `--handler codex`
  is the local Codex CLI coder lane; it requires `--handler-workspace
  codex=/path/to/worktree` and must produce a real git diff.
- **Browser transport**: browser handlers execute through `$surf` and
  `$browser-oracle` from Tau command specs. With `--execute`,
  `--browser-tab-lifecycle auto` is the default. For roundtable and compete
  browser handlers, auto creates one fresh run-scoped browser window, opens one
  provider tab per browser handler, binds those tabs under run-scoped
  browser-oracle projects, rewrites handler projects, and closes the owned
  window after execution. Use `--handler-project handler=project` only when
  deliberately reusing a pre-bound project; that is the fallback path, not the
  normal path.
- **Browser attachments**: project agents should not reason provider-by-provider
  for local bundles. Put readable local evidence in one bundle when possible
  and let `$ask` forward it to Surf as `--attach-file`; Surf browser wrappers
  also accept `--attach-files` for direct debugging. Supported browser handlers
  are `webgpt`, `webclaude`, `webkimi`, `webgemini`, and `webgrok`. If a
  provider cannot accept the specific file shape, Surf fails closed with
  attachment metadata; do not silently inline a huge bundle.
- **Evidence**: `--json` returns the Ask Tau bundle path, provider/handler gate,
  and Tau execution receipt when `--execute` is used. Preserve `dag.json`,
  command specs, node receipts, and join receipts.
- **Browser lifecycle evidence**: preserve `browser-tab-lifecycle.json`. It
  records the created window id, created provider tabs, run-scoped projects,
  lock timeout, cleanup policy, and cleanup attempts. For browser roundtables
  and competitions, validate this file together with Tau receipts and per-lane
  node receipts; command exit status alone is not proof.
- **Browser cooldown evidence**: preserve
  `browser-provider-availability.json` and
  `browser-provider-selection.json`. Ask writes these before browser tab
  lifecycle provisioning for executed browser roundtables and competitions. A
  visible WebGPT "Too many requests", WebGrok limit countdown, Kimi/Grok
  "System is currently busy", or similar provider banner is a lane-local
  cooldown, not a whole-panel launch block. Ask records `limited_providers` plus
  `cooldown_policy.status: LANE_LOCAL_RETRY`, records `cooldown_seconds: 600`,
  selects an available fallback such as WebClaude, WebGemini, or WebKimi when
  possible, and continues with available participants. Roundtable-mode
  WebClaude roundtable AND competition seats use Opus 5 High (Fable is rate-limited on this account, operator 2026-08-13); WebClaude uses Opus
  5 High by default. Stale or background old-tab read timeouts appear as
  `probe_degraded`; they are diagnostic, not proof of provider cooldown. Surf
  tab-list failure or non-timeout probe failures remain `ERROR`.
- **Surf lock behavior**: Tau may launch browser handler workers concurrently,
  but Surf browser operations share `/tmp/surf.sock` and must wait on the Surf
  lock. Ask emits long `--browser-lock-timeout` / `--lock-timeout` envelopes so
  concurrent browser lanes wait like database clients instead of failing after
  a short fixed timeout. Do not add `--no-lock` to roundtable or compete lanes.
- **Partial roundtable failures**: when at least one handler returns a usable
  response and the other handler seats have terminal receipts, Ask/Tau emits a
  `DEGRADED` join receipt instead of discarding the panel. Failed seats must be
  indexed as `NEEDS_ATTENTION` with `failure_code`, `response_path`, and
  `recovery_packet_path`. The join receipt and Markdown summary must include
  `degradation_analysis` explaining why the aggregate degraded, grouped failure
  codes, failed seats, and exact recovery commands when recovery packets exist.
  Each failed seat must also include `ticket_instruction` so the project agent
  knows exactly when to file a `$ticket` to `$ask` at `agent-skills@main`.
  A provider-specific rate limit degrades only that provider; keep usable seats
  and select available participants instead of failing the whole panel.
  `browser-provider-selection.json` must show `removed_handlers`,
  `fallback_handlers`, `active_handlers`, `cooldown_seconds`, `ticket_command`,
  and `ticket_instruction` when a requested provider was unavailable. File the
  `$ticket` when the unavailable provider looks broken, repeats after cooldown,
  or the packet lacks enough evidence for the project agent to recover.
  If a provider returns raw sentinel-bearing text but the cleaned response still
  contains the sentinel, classify the lane as
  `browser_clean_output_contaminated`, surface `raw_contains_sentinel`,
  `clean_contains_sentinel`, output paths, and tab ids in the recovery packet,
  and do not collapse it into stale tab, repo access, or generic timeout.
  If no handler produces usable reviewer evidence, the join status is
  `NEEDS_ATTENTION`.

## Compete / Bakeoff Protocol

For substantial competitions, use `$best-practices-competition` as the compact
leadership protocol and this section as the Ask-specific runtime runbook.

Use compete when the user asks for independent implementations, an approach
bakeoff, or a winner chosen from multiple candidate handlers. Do not use
roundtable for this: roundtable seats are collaborators with shared context,
while compete candidates are isolated.
Between candidate iterations, the project agent may use `$brave-search`,
`$github-search`, or `$dogpile` to help a candidate unblock, but it must not
share another candidate's output, approach, score, or failure analysis.
Iteration should be represented as a dynamically expanding Tau DAG whenever
the runtime supports appending nodes. Otherwise, launch a linked next-round DAG
that preserves the same immutable goal hash and cites the previous run
directory as input evidence.

Canonical compile command:

```bash
./run.sh compete "Implement the focused patch. Return concrete reusable features as VERIFIED_FEATURE: lines only when locally checkable." \
  --repo local/agent-skills \
  --target ask-compete \
  --immutable-goal "Select a winner only from locally verified features and continue with that winner until deterministic proof satisfies the task." \
  --handler webgpt \
  --handler webclaude \
  --handler gpt-5.5-high \
  --handler-project webgpt=tau \
  --criterion skill-contract \
  --criterion deterministic-proof \
  --json
```

Live execution adds `--execute` and uses the same Tau dispatch path as
roundtable. Browser handlers run through `$surf` and `$browser-oracle`; API
handler names route through `$tau` to either `$scillm` or `/subagent-runner`
depending on the handler transport. All-browser compete runs run a bounded
browser transport gate before Tau launch; if Surf/native-host or browser-oracle
bindings are unavailable, Ask returns `BLOCKED`/`NEEDS_ATTENTION` style
receipts with terminal candidate and join statuses instead of starting a long
Tau run that leaves handlers `RUNNING` and join `PENDING`.

Project-agent responsibilities after a compete run:

1. Read `dag.json`, command specs, each candidate `node-receipt.json`, each
   `response.md`, `join/compete-scorecard.json`, and
   `join/winner-continuation-request.md` or legacy
   `join/winner-revision-request.md`.
2. Check every candidate against the current codebase, relevant `SKILL.md`
   contracts, allowed files, and deterministic proof commands.
3. Treat candidate `VERIFIED_FEATURE:` lines as claims until locally checked.
   Promote only features the project agent can verify against repository state.
4. After N rounds, harvest useful features feature-by-feature. Losing
   participants may provide no useful ideas, one useful feature, or several
   useful features; the project agent decides from local evidence.
5. Accept a winner only when there is a clear receipt-backed and locally
   checked advantage. If there is a tie, missing candidate receipt, provider
   blocker, unclear patch, or no local proof, report `NEEDS_ATTENTION`.
6. Close the competition phase after winner selection. Continue iterating with
   the winning participant until the immutable goal is met or a real
   `NEEDS_ATTENTION` blocker is recorded.
7. Send a winner-continuation request only after pruning unverified features.
   The winner should keep its own implementation as the base and add only the
   explicitly verified features from other candidates.

Compete is fail-closed by design:

| Condition | Behavior |
| --- | --- |
| Fewer than two handlers | Emits an `$interview` packet instead of a DAG |
| Non-concurrent topology | Emits an `$interview` packet; isolation requires concurrent candidates |
| Missing immutable goal or acceptance bar | Emits an `$interview` packet before browser/API calls |
| All-browser execute preflight fails | Blocks before Tau launch and records terminal candidate/join statuses |
| Missing candidate receipt | Join reports `NEEDS_ATTENTION` |
| Candidate lane transport or provider error | Lane records `NEEDS_ATTENTION` and exits successfully so the join can emit the partial scorecard |
| Any candidate lane is `NEEDS_ATTENTION` | Scorecard remains `NEEDS_ATTENTION`; no clean winner is named until that lane is resolved or explicitly excluded |
| Degraded or blocked candidate set | `compete-scorecard.json` includes `degradation_analysis` with blockers, failed candidates, failure codes, and recovery commands |
| Candidate claims a feature without local proof | Project agent must not promote it |
| Tie or no clear winner | Report `NEEDS_ATTENTION`; do not fabricate a winner |
| Winner-continuation packet exists | It is a next request, not proof that revision was submitted |

Required compete artifacts:

- `request.json`
- `dag.json`
- `command-specs/<candidate>/tau-dispatch-command.json`
- `node-artifacts/<candidate>/node-receipt.json`
- `node-artifacts/<candidate>/response.md`
- `node-artifacts/join/compete-scorecard.json`
- `node-artifacts/join/winner-continuation-request.md` or legacy
  `node-artifacts/join/winner-revision-request.md`

Do not claim compete success from model prose. Closure still requires local
deterministic evidence: tests, schema checks, endpoint responses, screenshots,
database/query evidence, or generated artifact validation appropriate to the
task.

## Roundtable Collaboration Protocol (operator directive 2026-07-22)

For substantial roundtables, use `$best-practices-roundtable` as the compact
leadership protocol and this section as the Ask-specific runtime runbook.

Roundtable handlers are COLLABORATORS, not competitors. The panel's value is
model diversity: each seat contributes from different training and strengths.
Rules for the calling agent:

- **No blind rounds.** Every round, including the first, shares the full
  working context, all prior positions, and the calling agent's research brief
  with every seat identically. Prompts may invite a seat's strengths; they must
  never withhold context from any seat.
- **Equal sharing means concurrent topology.** Put the synthesis + research
  brief in the shared request text so all seats receive identical context.
  Sequential receipt-passing is asymmetric (the first seat sees nothing new)
  and is not a substitute for equal sharing.
- **Iterate, never one-shot.** Between rounds the calling agent researches the
  load-bearing claims from the responses: /dogpile (brave web + arxiv +
  github + more) when available, else /brave-search (subcommand is `web`).
  Then inject the fresh external evidence into the next round's shared prompt.
- **Converge or surface dissent.** Iterate to convergence or a 3-round cap;
  dissent surviving the cap goes to the human as a genuine split, never
  papered over. Verify panel-cited external claims (repos, papers, standards)
  before relying on them.

### Roundtable Runbook (exact steps)

1. **Round 1**: put the full shared context, evidence, constraints, and open
   questions in one prompt. Run all seats concurrently. If any handler is a
   browser handler, Ask automatically creates a fresh browser window:
   `./run.sh tau-dag "<full-context request>" --repo <r> --target <t>-r1 --immutable-goal "<goal>" --dag-template roundtable --handler webgpt --handler webclaude --handler webkimi --topology concurrent --execute --poll-timeout-seconds 3600 --json`
2. **Read responses** from the printed `run_dir`:
   `<run_dir>/node-artifacts/handler-<seat>/response.md`. Verify each seat's
   `node-receipt.json` status, `failure_code`, `browser_oracle`, and
   `browser_transport_failure_summary` when present.
3. **Read the join**:
   `<run_dir>/node-artifacts/join/node-receipt.json`. If `status` is
   `DEGRADED` or `NEEDS_ATTENTION`, keep the usable responses and follow only
   the failed seats' recovery packets. Do not discard the whole panel.
4. **Research between rounds (mandatory, before the next round is launched)**:
   `skills/dogpile/run.sh "<load-bearing claim>"` (falls back:
   `skills/brave-search/run.sh web "<query>" --count 5`). Read the output back;
   empty output is a blocker to diagnose, not to skip.
5. **Round N+1** (concurrent again): request text = synthesis of ALL prior
   positions (attributed per seat) + the research brief + the open questions,
   identical for every seat. Repeat 3-5 until convergence or 3 rounds.
6. **Close - executable slices, not prose**: a roundtable is INCOMPLETE
   until its converged plan is converted into an executable slice manifest
   committed to the project's evidence repo. Each slice states: owner
   (`codex-loop` | `project-agent-script` | `human`), the concrete artifact
   or command it produces, and a machine-checkable acceptance test. The
   final round's prompt should ask each seat to propose or amend slices
   directly (owner + artifact + acceptance), so the panel emits
   implementation, not advice. Then commit per-round responses as
   artifacts and report the slice manifest plus any surviving dissent
   (attributed) to the human. Prose-only convergence is a protocol
   violation (operator, 2026-07-23).

Manual browser-oracle binding is a fallback, not the normal roundtable path.
Use it only when the human explicitly names an existing tab or when
`fresh-temporary` is unavailable. In that case, verify the URL with
`skills/surf/run.sh tab.list --json`, bind with the command below, and pass
`--handler-project <handler>=<project>`.

```bash
skills/browser-oracle/run.sh bind <project> --backend <backend> --tab-id <id> --url "<live-url>" --manual --json
```

Known traps: prompt text containing `~<digits>` (e.g. "~20 pages") trips
surf's path preflight (agent-skills#973) - write "about 20"; browser providers
may rate-limit or show capacity banners, which is lane-local
`browser_provider_rate_limited` evidence; zsh does not word-split unquoted
argument variables, so spell out surf/ask args or use bash -c.

## Mode Router

Use the narrowest mode that matches the user request.

| Request | Runtime pattern | Required details |
| --- | --- | --- |
| Memory-backed question | `./run.sh ask "<question>" --json` | Include scope when relevant. |
| Oracle answer | `./run.sh ask "<question>" --oracle ... --json` | Choose backend/model/persona explicitly when requested. |
| Pi browser-handler shortcut | `./run.sh webgpt What is 2 + 2?` from `/skill:ask webgpt What is 2 + 2?` | Rewrites to Tau `single-call` with `--handler webgpt --execute --json`; use `--compile-only` to emit the DAG without live browser transport. |
| Single named handler | `./run.sh tau-dag "<request>" --handler <handler-or-model> --json` | Browser handlers use `$surf`; non-browser handlers are `$scillm` model names routed by Tau. Add `--execute` for live transport. |
| Multi-handler roundtable | `./run.sh tau-dag "<request>" --handler webclaude --handler gpt-5.5 ... --topology concurrent --execute --json` | Roundtable is prompt-to-Tau-DAG. Browser handlers get an Ask-owned fresh window by default. Preserve `browser-tab-lifecycle.json`, `dag.json`, command specs, handler receipts, and join receipts. |
| Compete / bakeoff | `./run.sh compete "<task>" --handler webgpt --handler webclaude --handler gpt-5.5-high --criterion deterministic-proof --execute --json` | Isolated candidates plus compete scorecard and winner continuation request. Browser/API handlers are peers. Project agent must locally verify features before promotion. |
| Creator-reviewer loop | `./run.sh tau-dag "<request>" --handler <creator> --handler <reviewer> --topology sequential --json` | The reviewer receives prior handler receipts. Pass/fail requests require a verdict in the reviewer response. |
| Supported direct browser oracle | documented browser mode such as `webgemini`, `webkimi`, `webperplexity`, or `cursor-browser` | Use only when the user asks for that direct mode; attach local target content when browser cannot read paths. |
| Deep review | `./run.sh ask "<question>" --deep-review --deep-review-target <path> ... --json` | Pass complete target bundle; return `review.md` and `review.json`. |
| Parallel review | `./run.sh ask "<question>" --parallel-review ... --json` | State reviewer count/focus and preserve per-reviewer outputs. |
| Persona roundtable/argue | `./run.sh ask "<question>" --roundtable ... --json` or argue mode | Persona deliberation only. For web/API handler roundtables, use `tau-dag`. |
| CAE gap review | documented CAE gap mode | Include current claim, evidence, gaps, and acceptance gate. |
| Tau DAG front door | `./run.sh tau-dag "<request>" --repo <repo> --target <target> --solver-model <model> --reviewer-model <model> --criterion <c> --json` | Emits strict `tau.dag_contract.v1` first; uses `$interview` packet when incomplete; add `--execute` to delegate to Tau. |
| Ask/scillm-style DAG file | `./run.sh ask "<question>" --dag-file <graph.json> ... --json` | Use only when the user provides an existing ask/scillm-style DAG file; preserve DAG manifest, node outputs, and fail-closed events. |
| Authorized local CAPTCHA evaluation | Generate `ask.dag.v1` with `../captcha/run.sh ask-dag ...`, then use `./run.sh ask "<request>" --dag-file <graph.json> --json` | Ask owns orchestration; `$captcha` owns authorization and receipts; `$surf` supplies browser-transport proof; ReCAP `dynamic` loopback only. |
| Image generation | documented image mode | Preserve prompt, provider response, output path, and review artifact. |
| OS/project health | `./run.sh os ... --json`, `./run.sh doctor ... --json` | Report degraded dependencies, not green-by-absence. |
| Status/config | `./run.sh status ... --json`, `./run.sh config doctor ... --json` | Use for artifact inspection and readiness preflight. |

## Browser Rules

### MANDATORY prompt/bundle preflight (run before EVERY browser submit)

surf's webgpt submit **rejects** any prompt or attached bundle that references
an unreadable local filesystem path (schema `surf.webgpt_prompt_preflight.v1`,
reason `web_review_bundle_unreadable`) or a `~<digits>` token (agent-skills#973),
failing late with `browser_submit_not_accepted` after tab binding and wasted
cycles. This is a *recurring* mistake — a comprehensive-context bundle naturally
contains paths (`/run/...`, `/home/...`, `/mnt/...`, `~/...`) and shorthand like
`~20 pages`. Do not rely on eyeballing it.

Before any `tau-dag`/`compete`/`webgpt`-shortcut submit with a web* handler, run
the fail-closed preflight on your prompt AND every `--attach-file`, and fix what
it names (describe paths/sockets as prose; write "about 20", not "~20"):

```bash
python3 skills/ask/scripts/browser_prompt_preflight.py --prompt "<prompt>" <each --attach-file>
# exit 0 = safe to submit; exit 2 = offending tokens listed, fix them first
```

Direct WebGPT/ChatGPT browser oracle workflows have moved out of `$ask ask`.
`$ask webgpt`, `$ask chatgpt`, `--oracle-backend webgpt`, `--webgpt-*`, and
`webgpt-project` must fail closed.

Do not confuse that direct-oracle restriction with Tau roundtable handlers:
`webgpt`, `webclaude`, `webkimi`, `webgemini`, and `webgrok` are supported as peer Tau
browser handlers through `$surf`/`$browser-oracle` command specs.

- A browser tab cannot inspect bare local paths unless the runtime attaches file
  contents or serves an artifact URL. Include readable target content in the
  bundle when needed.
- Use the configured tab id when available. If the tab is missing, wrong, stale,
  or cannot be proven to match the requested reviewer, stop with
  `NEEDS_ATTENTION`.
- Project agents should not manually remember or perform stale-tab rebinding
  during normal Ask runs. Browser-oracle bindings are starting hints. If Surf
  reports a stale/wrong provider tab, missing composer, or auth-like stale-tab
  failure, `$ask` scans already-open same-provider tabs, retries a bounded
  candidate set, and updates the browser-oracle binding only after a successful
  submit. The proof appears in `node-receipt.json` as
  `browser_oracle_binding_refresh` plus command entries such as
  `<handler>_stale_binding_scan_live_tabs` and
  `<handler>_stale_binding_submit_existing_tab`. If no candidate succeeds, the
  lane stays `NEEDS_ATTENTION` with a recovery packet.
- **Browser tab lifecycle for browser handlers**:
  - Default mode is `--browser-tab-lifecycle auto`. For executed roundtables
    and competitions with browser seats, auto behaves as `fresh-temporary`.
    For non-browser DAGs, it behaves as `reuse-bound`/skipped.
  - `fresh-temporary` asks `$surf` to create one Chrome window, records the
    returned `windowId`, creates one provider tab in that window with
    `tab.new --window-id`, binds temporary browser-oracle projects for each
    handler, runs Tau, then closes only the Ask-created window. Existing user
    tabs and pre-existing browser-oracle bindings are not closed by this
    lifecycle.
  - Use `--browser-tab-lifecycle fresh-keep` when the human or project agent
    needs to inspect the provider tabs after the run. It creates and binds the
    same fresh window/tabs but leaves them open.
  - Ask writes `<run_dir>/browser-tab-lifecycle.json` with `window_id`,
    `created_tabs`, temporary `handler_projects`, command receipts, and cleanup
    attempts. If fresh provisioning or binding fails, Ask records
    `browser_tab_lifecycle_failed`, does not launch Tau, and exits with a
    recovery packet.
  - Manual tab binding remains a fallback only: create/list/bind with `$surf`
    and `$browser-oracle`, then pass `--handler-project <handler>=<project>`.
    Do not make project agents manually rebind stale tabs when the Ask lifecycle
    can own the window.
- If a WebGPT/Tau browser-handler receipt or Surf metadata reports
  `conversation_max_length_detected` or `conversation_max_length_rollover`, treat
  it as Surf's controlled-tab conversation rollover path. Do not reclassify it
  as a generic reviewer failure, browser-oracle mismatch, download failure, or
  sentinel parser defect. If rollover succeeded, continue from the returned
  controlled tab and preserve the `from_tab_id`, `to_tab_id`, and `action`
  fields in the Ask/Tau artifacts. If rollover failed, mark only that handler
  node `NEEDS_ATTENTION` and route the next attempt through the same Surf
  `Start new chat`/fresh-tab recovery contract.
- If a WebGPT/Tau browser-handler receipt or Surf metadata reports
  `chatgpt_too_many_requests_detected` or `chatgpt_rate_limit`, treat it as
  Surf's provider-throttle cooldown path. Surf waits
  `SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS` (default `300`) before it clicks
  **Got it**, because dismissing the modal during the throttle restarts the
  limit window. Ask browser workers opt WebGPT into one automatic retry by
  setting `SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS=1`; raw Surf defaults still do
  not retry unless their caller opts in. Do not
  reclassify it as a reviewer failure, browser-oracle mismatch, download
  failure, or sentinel parser defect. Mark only that browser handler node
  `NEEDS_ATTENTION` or rate-limited, preserve the throttle metadata, continue
  with other available participants, and let the outer scheduler back off. Do
  not launch parallel WebGPT attempts to bypass the throttle.
- If a WebGPT handler leaves orphaned submit artifacts but no final
  `node-receipt.json`, treat those artifacts as terminal recovery evidence, not
  as a silent hang. Preserve and read `response.md.receipt.json`,
  `webgpt_inflight.json`, and `webgpt_heartbeat.json`; Ask should synthesize a
  lane-local `node-receipt.json` plus `browser-recovery-packet.json` that
  promotes submitted state, sentinel, requested tab id, heartbeat phase/page
  state, provider-throttle evidence, and an actionable `next_command` when one
  exists. If those synthesized receipts are missing or collapse rate-limit
  metadata into a generic timeout, file a `$ticket` to `$ask` at
  `agent-skills@main` with the Ask run directory and all three orphaned
  artifacts.
- If a WebKimi/Tau browser-handler receipt or Surf metadata reports
  `kimi_provider_capacity_busy`, `BLOCKED_KIMI_PROVIDER_CAPACITY`, or
  `proof_status: provider_capacity_limited`, classify only that browser handler
  as `browser_provider_rate_limited`. Preserve the recovery packet and use a
  different handler or rerun later; do not keep submitting Kimi prompts into a
  capacity-busy tab.
- If WebKimi or WebGrok reports `System is currently busy`, `capacity is busy`,
  `BLOCKED_KIMI_PROVIDER_CAPACITY`, `BLOCKED_GROK_PROVIDER_CAPACITY`, or
  `proof_status: provider_capacity_limited`, treat it as a lane-local provider
  capacity limit. Surf may wait a bounded cooldown and retry that one lane, but
  the project agent must not pause, cancel, or rerun healthy roundtable or
  competition participants because another participant is cooling down.
- Concurrent browser handlers remain independent Tau nodes. Their active Surf
  commands queue on the shared browser lock, but provider cooldown sleeps do
  not hold that lock and must not become DAG dependencies between participants.
- A missing Surf socket, native-host disconnect, or `Surf connection closed
  before response` is local transport failure
  `surf_browser_connection_unavailable`, not provider throttling. Recover the
  Surf host/socket and rerun only the affected lane; do not apply a provider
  cooldown.
- `stale_socket_no_listener` is the specific Surf native-host case where the
  socket path exists but has no listener. Ask preflight reports
  `recovery_kind: surf_stale_socket_no_listener` and should stop before Tau
  dispatch. Preserve the preflight artifact and follow the Surf runbook rather
  than submitting a browser-handler job.
- Competition joins preserve every terminal candidate receipt, including
  blocked lanes, but populate `winner_handler` and `winner_node_id` only when
  the scorecard is blocker-free `PASS`. A `NEEDS_ATTENTION` scorecard never
  names a winner.
- Do not use raw `surf` as a substitute for `$ask`; use it only for transport
  debugging, direct project-level WebGPT workflows, or Tau command specs emitted
  by `./run.sh tau-dag`.
- Browser review output is reviewer evidence. It still must be reconciled
  against repository state and deterministic local checks before closure.

## Review Contracts

Load only the reference needed for the selected mode:

- Deep review: `docs/ASK_DEEP_REVIEW_CONTRACT.md`
- Parallel review: `docs/ASK_PARALLEL_REVIEW_CONTRACT.md`
- Argue/roundtable: `docs/ASK_ARGUE_CONTRACT.md`
- CAE gap review: `docs/ASK_CAE_GAP_REVIEW_CONTRACT.md`
- SPARTA preflight: `docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md`
- Human chat examples: `docs/HUMAN_CHAT_EXAMPLES.md`
- Project knowledge: `docs/PROJECT_KNOWLEDGE.md`
- Review chains: `docs/chains/`
- Reviewer definitions: `docs/reviewers/`
- Templates: `docs/templates/`

When a reference file is selected, read it completely before running that mode.

## Command Reference

For common commands, use the examples above. For live browser workflow proof,
validate the returned run directory instead of trusting command exit status:

```bash
scripts/validate_live_browser_workflow.py <run-dir> \
  --workflow-mode roundtable \
  --handler webgpt --handler webclaude --handler webkimi --handler webgemini \
  --min-concurrency 4 \
  --require-cleanup \
  --json

scripts/validate_live_browser_workflow.py <run-dir> \
  --workflow-mode compete \
  --handler webgpt --handler webclaude --handler webkimi --handler webgemini \
  --min-concurrency 4 \
  --require-cleanup \
  --json
```

The release gate for mixed browser/API roundtable and competition transport is:

```bash
uv run --project skills/ask python \
  skills/ask/evals/live_mixed_dag_e2e.py --iterations 2 --allow-live
```

It resets each bound browser tab to a fresh chat, executes both Tau DAG modes,
and fails unless every browser/API lane and the join are live, non-mocked, and
usable. It can take several hours when providers impose cooldowns.

## Output Expectations

For normal answers, return the answer plus the artifact directory when artifacts
exist. For reviews, lead with findings and include the artifact paths. For
blocked or degraded runs, return the failing command, missing proof, and next
deterministic gate.

Do not say work is complete, verified, green, or fixed unless the artifacts and
local checks prove it.

## Related Skills

- Use `$memory` before ask when the task is about prior project context.
- Use `$scillm` only for direct model/runtime diagnosis after reading its skill.
- Use `$surf` or `$browser-oracle` only when this skill or a selected reference
  routes browser transport there.
- Use `$best-practices-roundtable` when leading or synthesizing a substantial
  roundtable.
- Use `$best-practices-competition` when leading or judging a substantial
  compete/bakeoff workflow.
- Use `$best-practices-skills` when modifying this skill or its scripts.
