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
  - compete
  - bakeoff
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
  - subagent-runner
  - browser-oracle
  - create-report
  - tau
  - interview
  - best-practices-roundtable
  - best-practices-competition
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

Run commands from this directory. `./run.sh tau-dag "<request>"` maps to the
Typer `tau-dag run` subcommand internally.

```bash
cd skills/ask
./run.sh --help
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
`gpt-5.5-xhigh`, or `chutes deepseek-ai/DeepSeek-V3.2-TEE` are routed by Tau.
Project agents should not care which side is browser or API beyond naming the
handler.

For executed roundtables and competitions with browser handlers, Ask defaults to
`--browser-tab-lifecycle auto`. Auto creates one Chrome window, creates one tab
per requested browser handler, binds temporary browser-oracle projects, runs
Tau, and closes only that Ask-created window. The project agent does not need to
pre-create tabs or pass `--handler-project` for normal web seats. Use
`--browser-tab-lifecycle fresh-keep` only when a human needs to inspect the tabs
after the run. Use `--browser-tab-lifecycle reuse-bound` only for an
intentionally known-good existing browser-oracle project.

Pass local evidence a browser seat must actually see with `--attach-file <path>`
(repeatable) on `tau-dag run` or `compete`. Ask forwards each file to Surf as
`--attach-file` for browser handlers and records `requested_attachment_paths`
plus `browser_attachment_paths` in the node receipt. A missing file or a handler
that cannot attach fails the lane closed rather than answering from prose.
Attachment delivery needs an extension build that handles
`AI_UPLOAD_FILE_TO_TAB`; older extensions reject the upload and the lane reports
`browser_submit_not_accepted` with that message.

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

Before launching a costly live browser panel, Ask now runs a standard read-only
provider availability probe automatically. It inspects existing provider tabs
for visible rate-limit or capacity banners and writes
`<run_dir>/browser-provider-availability.json`; it does not submit prompts. If
the report is `NEEDS_ATTENTION` or `ERROR`, Ask exits before creating fresh
browser tabs or dispatching Tau, with `blocked_reason:
browser_provider_unavailable_preflight`, `failure_code`, `limited_providers`,
and `next_command` in the top-level execution receipt.

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

If the report is `NEEDS_ATTENTION`, treat the named provider as currently
unavailable for new roundtable or competition lanes unless the human explicitly
asks to try it anyway. This preflight is not completion proof; it only prevents
obvious provider-throttle loops before a live DAG starts.

Failures must be non-silent. A failed browser/API/subagent lane must expose
`failure_code`, `recovery_packet_path`, `next_command` or an explicit
fail-closed reason, and `ticket_instruction`. If a recovery packet is missing,
misclassified, hides Surf/CDP/SciLLM stderr, gives no actionable recovery, or
still blocks the project after its recovery instruction is followed, file a
`$ticket` to `$ask` at `agent-skills@main`. Include the Ask `run_dir`,
`dag.json`, the failing node receipt, recovery packet, `response.meta.json`,
raw response, and exact command stderr.

## Required Behavior

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
  `webgemini`, and `webgrok`. Aliases normalize as `gpt -> webgpt`,
  `claude -> webclaude`, `kimi -> webkimi`, `gemini -> webgemini`, and
  `grok -> webgrok`.
- **Supported local/API handlers**: explicit non-browser handler labels are
  routed by Tau according to their transport. SciLLM-compatible model labels,
  such as `gpt-5.5-high`, emit Tau-owned `scillm.chat` adapter nodes.
  OAuth/Codex subagent selectors such as `gpt-5.5-xhigh` emit Tau-owned
  `subagent-runner.codex_exec` nodes and preserve `xhigh` as the requested
  reasoning effort. For Chutes exact models, project agents may write
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
  `browser-provider-availability.json`. Ask writes this before browser tab
  lifecycle provisioning for executed browser roundtables and competitions. A
  visible WebGPT "Too many requests", WebGrok limit countdown, Kimi/Grok
  "System is currently busy", or similar provider banner blocks the launch
  before any prompt is submitted. That provider is unavailable for this run;
  rerun the availability probe after the cooldown and continue with available
  participants when the workflow allows it. Stale or background old-tab read
  timeouts appear as `probe_degraded`; they are diagnostic, not proof of
  provider cooldown. Surf tab-list failure or non-timeout probe failures remain
  `ERROR`.
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
| Image generation | documented image mode | Preserve prompt, provider response, output path, and review artifact. |
| OS/project health | `./run.sh os ... --json`, `./run.sh doctor ... --json` | Report degraded dependencies, not green-by-absence. |
| Status/config | `./run.sh status ... --json`, `./run.sh config doctor ... --json` | Use for artifact inspection and readiness preflight. |

## Browser Rules

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
  limit window, and retries only when the caller
  deliberately opts in with `SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS>0`; default
  Ask/SURF behavior is no automatic WebGPT resubmit after this modal. Do not
  reclassify it as a reviewer failure, browser-oracle mismatch, download
  failure, or sentinel parser defect. Mark only that browser handler node
  `NEEDS_ATTENTION` or rate-limited, preserve the throttle metadata, continue
  with other available participants, and let the outer scheduler back off. Do
  not launch parallel WebGPT attempts to bypass the throttle.
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
