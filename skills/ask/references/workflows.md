# Ask: Workflow Protocols

Single calls, roundtables, compete/bakeoff, creator-reviewer: full runtime
runbooks, fail-closed tables, required artifacts, and the roundtable
collaboration protocol. Read before compiling or executing any multi-seat DAG.

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
  API-backed model such as `gpt-5.5`, `Codex-sonnet-4-6`, or another model
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
  such as `claude-fable-low`, `claude-sonnet-4-6-high`, or
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

