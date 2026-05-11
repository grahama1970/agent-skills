---
name: ask
description: >
  Zero cognitive-load learning and querying skill. Learn about a topic or persona (e.g., "Lisa Feldman Barrett")
  by discovering, ingesting, and extracting knowledge — or ask questions against what's been learned.
  Supports multi-hour deep learning with progress tracking, persona profiles, and nightly incremental updates.
  Uses Federated Taxonomy for multi-hop graph traversal across knowledge domains.
  Composes: dogpile, discover-books, ingest-youtube, fetcher, extractor, memory, taxonomy, task-monitor.
allowed-tools: [Bash, Read, Write]
triggers:
  - I want to learn about
  - I want to ask
  - ask about
  - learn about
  - /ask
  - $ask Brandon
  - ask Brandon
  - ask <persona> what
  - ask <persona> how
  - ask <persona> critique
  - ask <persona> review
  - ask <persona>, <persona>, and <persona> to debate
  - ask roundtable
  - ask parallel reviewers
  - ask adversarial review
  - ask deep review
  - ask image generation
  - ask generate image
  - ask CAE gap review
  - ask QRA gap review
  - ask safe to proceed
  - ask comprehensive review
  - ask persona roundtable about
  - ask N parallel reviewers
  - ask NIST control
  - ask SPARTA countermeasure
  - ask current architecture risk
  - ask the oracle as
  - ask oracle with persona
  - ask webgpt
  - $ask webgpt
  - ask chatgpt
  - $ask chatgpt
  - webgpt review
  - webgpt oracle
  - chatgpt oracle
  - ask webgpt to review
  - ask webgpt about
  - teach me about
  - what does X say about
  - what does Sapolsky say
  - what does Barrett say
  - learn from
  - ask about embry
  - how does X skill work
  - what does the X skill do
  - is memory healthy
  - is X healthy
  - what skills provide
  - os health
  - os learn
metadata:
  short-description: Zero cognitive-load learning and querying for personas, topics, and OS internals
  author: "Horus"
  version: "0.6.1"

provides:
  - ask
  - oracle-query
  - os-knowledge
composes:
  - memory
  - dogpile
  - extract-entities
  - create-evidence-case
  - discover-books
  - ingest-youtube
  - fetcher
  - extractor
  - taxonomy
  - scillm
  - subagent-runner
  - create-context
  - monitor-memory
  - monitor-skills
  - monitor-skill-health
  - monitor-security
  - monitor-sparta
  - monitor-personas
  - monitor-taxonomy
  - project-knowledge
  - ops-workstation
  - ops-arango
  - ops-docker
  - ops-llm
  - ops-chutes
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ask

Zero cognitive-load learning and querying interface. Eight modes:

1. **Learn Mode** — Discover, ingest, and extract knowledge about a topic or persona
2. **Ask Mode** — Query accumulated knowledge with Federated Taxonomy multi-hop traversal
3. **Auto-Learn Mode** — Ask a question; if no knowledge exists, automatically learn then answer
4. **Nightly Mode** — Scheduled incremental updates to persona knowledge bases
5. **OS Mode** — Learn about and query embry-os internals, skills, packages, and runtime health
6. **Deep Review Mode** — High-reasoning, read-only review with `review.md` and `review.json`
7. **CAE Gap Review Mode** — Evidence-case-backed QRA review with bounded reviewer/judge rerouting
8. **Image Generation Mode** — Generate image artifacts through `/scillm` `/v1/images/generations`

## Literal Runtime Contract

When a human names `$ask`, `/ask`, or asks to use the ask skill, the project
agent must use this skill's `./run.sh` runtime unless the human explicitly asks
for a fallback or the runtime is unavailable.

Do not replace `$ask` with:

- `spawn_agent`
- an informal subagent prompt
- a plain model call
- a hand-written reviewer summary
- a web search
- a local-only critique that bypasses ask artifacts

For review requests, pass the complete target artifact through the documented
ask mode instead of summarizing it. Examples:

- Use `--deep-review --deep-review-target <path>` for Web-GPT-style prompt,
  schema, code, plan, or artifact reviews.
- Use `--parallel-review` for independent reviewer fanout.
- Use `--roundtable` only when the user asks for persona deliberation.
- Use `--cae-gap-review` only for evidence-case-backed CAE/QRA gap review.

Proof of a real `$ask` run is the ask artifact set, not an assistant summary.
Return the relevant artifact paths, such as:

- `.request.json`
- `.status.json`
- `.events.jsonl`
- `review.md`
- `review.json`
- mode-specific generated artifacts

If the runtime is unavailable, report that directly and ask before substituting
`spawn_agent` or another fallback.

Release readiness is evidence-based, not implied. `/ask` uses `ask.config.yml`,
`config doctor`, live sanity reports, and Docker preflights to say what is ready,
what needs user attention, and what is not established.

Every `ask` call also writes runtime artifacts so long oracle/review runs are
inspectable without guessing whether the runner is blocked in retrieval,
persona routing, oracle synthesis, or artifact verification.
Direct scillm oracle calls use SSE streaming and record
`oracle_scillm_call_started`, `oracle_scillm_stream_progress`,
`oracle_scillm_call_finished`, and `oracle_scillm_call_failed` events so
project agents can distinguish active model work from hard-deadline failure.
The same runtime protocol is available for `learn`, `nightly`, `os learn`,
`os ask`, and `os health`.

## WebGPT Oracle Backend

`--oracle-backend webgpt` (or the `$ask webgpt …` shorthand) routes oracle
synthesis through the user's already-authenticated ChatGPT tab in Chrome via
`surf webgpt.submit --no-activate`. The tab is controlled in the background;
it never foregrounds.

```bash
# Auto-resolve tab id (when exactly one chatgpt.com tab is open)
./run.sh ask "to perform the review on /tmp/code-runner-reliability-review/review-bundle.md" \
  --oracle --oracle-backend webgpt

# Equivalent shorthand
./run.sh ask webgpt to perform the review on /tmp/code-runner-reliability-review/review-bundle.md

# Explicit tab id (from the Tab ID Viewer Chrome extension)
./run.sh ask "summarise the review bundle" \
  --oracle --oracle-backend webgpt --webgpt-tab-id 837343564

# Resolve by ChatGPT conversation URL
./run.sh ask "summarise the review bundle" \
  --oracle --oracle-backend webgpt \
  --webgpt-url "https://chatgpt.com/c/6a0097ff-e7e0-83ea-93c2-3a6b88e2a67f"

# Autonomous mode: let surf pick or create a background ChatGPT tab.
./run.sh ask webgpt summarise the review bundle --webgpt-create-tab
```

Behavior:

- **Tab resolution.** Priority: `--webgpt-tab-id` → `--webgpt-url` →
  `--webgpt-create-tab` → auto-resolve from `surf tab.list` filtered to
  chatgpt.com. **Auto-resolve fails closed** when 0 or >1 candidates exist —
  the call refuses to run rather than guess. When the project agent hits
  this, it must ask the human to either:
  (a) open exactly one ChatGPT tab so auto-resolve picks it,
  (b) provide a tab id from the Tab ID Viewer extension to pass through
  `--webgpt-tab-id`, or
  (c) re-invoke with `--webgpt-create-tab` for the agent to acquire a tab
  autonomously (surf picks the most-recent existing chatgpt.com tab without
  foregrounding, or creates a fresh background one if none are open). The
  resolved tab id surfaces in `oracle_model_served: webgpt:<id>` so the
  agent can pass it explicitly to follow-up rounds.
- **File auto-attachment.** Absolute paths embedded in the question (e.g.
  `/tmp/foo.md`, `~/notes.md`) are read from disk and inlined under
  `## Attached files` in the prompt. Truncated at 2 MB per file.
- **Focus preservation.** The controlled tab is never foregrounded. The
  caller's active tab and focused window are unchanged across the call;
  `meta.focus_changed` must be `false`.
- **Multi-turn iteration.** Each `$ask webgpt` call is one round on the same
  controlled tab. ChatGPT keeps the conversation context per tab, so a second
  call refines naturally. The canonical pattern is: project agent reads the
  first round's answer, decides whether to push back, and re-invokes
  `$ask webgpt …` to send the follow-up — no special iteration flag needed.
  Internal `--oracle-iterations N` is also honoured: each iteration sends one
  follow-up nudge ("identify the weakest claim and address it").
- **Proof contract.** Inherits the WebGPT sentinel contract from `surf`:
  `controlled_tab_id == requested_tab_id`, sentinel present in raw response,
  stripped from clean response, no clean-response contamination from page
  chrome. `oracle_webgpt_call_started` / `_finished` / `_failed` events are
  recorded to the run state.
- **Other consumers.** `/review-prompt`, `/review-design`, `/review-code`,
  `/review-plan` compose `/ask` and inherit this backend for free —
  pass `--oracle-backend webgpt` (or set `ASK_ORACLE_BACKEND=webgpt`) to the
  underlying `/ask` call.
- **Live sanity.** `skills/ask/sanity-webgpt.sh` exercises the full path
  end-to-end against a real ChatGPT tab and asserts the proof contract,
  oracle wiring, and focus invariance. Modes: `--tab-id ID`, `--url URL`,
  `--create-tab`, or no flag (which auto-picks a single chatgpt.com tab or
  prints a 4-option help block when 0 or >1 candidates exist). Run after
  changes to `webgpt_runtime.py`, the oracle dispatcher, or the model
  alias router.

## Image Generation Mode

Use `/ask --image-generate` when the answer should be an image artifact rather
than retrieved memory or an oracle text response. `/ask` sends the prompt to
`/scillm` `POST /v1/images/generations`, writes generated image files under the
ask run directory by default, and records an `image_generation.json` manifest.

```bash
./run.sh ask "a precise architecture diagram of ask calling scillm for image generation" \
  --image-generate \
  --image-model gpt-image-2 \
  --image-size 1024x1024 \
  --image-quality high
```

Image generation is standalone: do not combine it with memory retrieval,
oracle, roundtable, argue, parallel-review, deep-review, or CAE gap-review
options. Use `--image-output` to choose a file or directory, and
`--image-output-format png|jpeg|webp` to choose the artifact format.

## Zero Cognitive Load for Project Agents

Project agents should just ask — the skill handles all discovery complexity:

```bash
# Project agent just asks a question
./run.sh ask "Lisa Feldman Barrett how might we improve our /memory system?" --auto-learn

# What happens automatically:
# 1. Memory check (existing knowledge?)
# 2. /dogpile deep research (Brave, Perplexity, ArXiv, YouTube, GitHub)
# 3. YouTube transcript ingestion (lectures, interviews)
# 4. Web content fetching (blogs, articles)
# 5. QRA extraction + Federated Taxonomy tagging
# 6. Memory storage with persona profile
# 7. Answer synthesis with multi-hop traversal
```

## Human Chat Usage

As the human using chat, use natural `$ask` phrasing. The agent should translate
these into the correct `/ask` CLI call. See `docs/HUMAN_CHAT_EXAMPLES.md` for
the complete human-facing example catalog. Representative examples are enforced
by `sanity.sh` via `tests/test_human_chat_examples.py`; do not add new chat patterns
without adding route coverage.

Agent translation rules:
- Preserve the human's natural topic text; do not over-normalize domain terms.
- Treat a named persona before the question as `--oracle-persona <name>`.
- Treat multiple named personas with "debate", "roundtable", or "discuss" as `--roundtable`.
- Treat "parallel reviewers", "adversarial reviewers", or "N reviewers" as `--parallel-review`.
- Treat "argue whether", "debate whether", or "make the case for and against" as `--argue`.
- Treat "review then roundtable" as both `--parallel-review` and `--roundtable`.
- Treat "CAE gap review", "QRA gap review", or "CAE reviewers" as `--cae-gap-review`.
- Treat "generate an image", "image generation", or "make an image" as
  `--image-generate`; keep it standalone from memory/oracle/review modes.
- Treat "deep review", "comprehensive review", "safe to proceed", or "production readiness" as `--deep-review`; require or infer a concrete `--deep-review-target`.
- Treat leading model shorthand such as `$ask oc kimi ...`, `$ask opencode qwen ...`, `$ask chutes kimi ...`, `$ask oc-kimi ...`, or `$ask chutes-kimi ...` as `--oracle --oracle-backend scillm` with the resolved provider model.
- Treat leading `$ask webgpt ...` (or `$ask chatgpt ...`) as `--oracle --oracle-backend webgpt`. This drives an already-authenticated ChatGPT tab in the user's Chrome via the surf-cli extension; the controlled tab never foregrounds (`--no-activate`).
- Treat date-sensitive words (`2026`, `current`, `latest`, `today`, `recent`) as `--dogpile auto`.
- Default high-value analytical questions to `--oracle --oracle-model gpt-5.5 --oracle-reasoning high`.

| Human chat prompt | Route |
|-------------------|-------|
| `$ask what do we know about the release checklist?` | Memory-backed ask synthesis |
| `$ask What is the state of Python packaging in 2026?` | Oracle with auto persona selection and `--dogpile auto` |
| `$ask What is the state of space-based cybersecurity in 2026?` | SPARTA-scoped oracle: `--scope sparta --oracle` |
| `$ask oc kimi explain this design tradeoff` | scillm OpenCode Go oracle using live model discovery and capability metadata, currently `opencode-go/kimi-k2.6` |
| `$ask oc kimi for a $review-design with maximum 3 rounds` | Ask-backed review-design loop using `opencode-go/kimi-k2.6`; capture fresh screenshots, ask Kimi for a verdict, patch locally, re-render, and stop after PASS/blocker/3 rounds |
| `$ask oc-qwen compare these options` | Hyphenated OpenCode Go shorthand, currently `opencode-go/qwen3.6-plus` |
| `$ask chutes kimi explain this design tradeoff` | scillm Chutes oracle using configured alias `chutes-kimi` |
| `$ask chutes-kimi explain this design tradeoff` | Hyphenated Chutes shorthand using configured alias `chutes-kimi` |
| `$ask webgpt to perform the review on /tmp/review-bundle.md` | WebGPT oracle backed by the user's signed-in ChatGPT tab (via `surf webgpt.submit --no-activate`). File paths in the prompt are auto-attached. Tab id auto-resolves when exactly one chatgpt.com tab is open; otherwise pass `--webgpt-tab-id`. |
| `$ask webgpt again — refine your answer` | Multi-turn: each `$ask webgpt` call is one round against the same controlled tab. ChatGPT preserves conversation context, so iterations form a coherent dialogue. |
| `$ask Brandon what is the state of space-based cybersecurity in 2016?` | Brandon persona oracle over `--scope sparta` |
| `$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: What is the state of cybersecurity in 2026?` | SPARTA-scoped sequential persona roundtable |
| `$ask Brandon what is the best way to review this API boundary?` | Brandon persona oracle subagent |
| `$ask Brandon persona about whether this retry design fails closed` | Brandon persona oracle over memory/project context |
| `$ask Brandon critique this architecture` | Brandon persona critique |
| `$ask Brandon ask Margaret where are we weak?` | Safe Brandon→Margaret peer deliberation |
| `$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: Should this service use retries or queues?` | Sequential protocolized persona roundtable |
| `$ask run 3 parallel adversarial reviewers on this implementation` | Independent parallel review plus moderator synthesis |
| `$ask cae gap review AC-2 MFA evidence for the production tenant` | Evidence-case-backed QRA review: `--cae-gap-review --cae-max-rounds 3` |
| `$ask generate an image of the ask to scillm image route` | Image artifact generation: `--image-generate` |
| `$ask argue whether we should ship this change` | Two parallel `/scillm` advocates plus sequential judge and verifier |
| `$ask deep review this implementation --deep-review-target src/ask/ask.py` | Read-only deep review with markdown and JSON artifacts |
| `$ask review then roundtable with Brandon, Margaret, Jennifer` | Parallel findings first, then sequential persona debate |
| `$ask oracle should we use subagent-runner here?` | GPT-5.5 high-reasoning oracle |
| `$ask learn Lisa Feldman Barrett` | Learn/persona-ingest mode |
| `$ask is memory healthy?` | OS/runtime health mode |

Natural persona syntax is supported by the CLI too:

```bash
./run.sh ask Brandon what is the best way to review this API boundary?
```

This is equivalent to:

```bash
./run.sh ask "what is the best way to review this API boundary?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-persona Brandon \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high
```

The subagent, not the chat router, decides whether `/dogpile` is necessary after
checking `/memory`. The `/ask` controller decides the timeout and records execution
telemetry in `/memory` for future timeout policy.

Plain broad analytical questions, such as "what is the state of X", are routed
to the oracle with persona consultation even when the human does not name a
persona. The oracle should choose the best ready persona using `/memory recall`
over persona lessons/lore; `/monitor-personas` is only an optional readiness
check.

## Quick Start

```bash
cd .pi/skills/ask

# Learn about a persona (deep learning)
./run.sh learn "Lisa Feldman Barrett" --scope behavioral --depth deep

# Ask with auto-learn (discovers + ingests if no knowledge exists)
./run.sh ask "What does Sapolsky say about free will?" --scope behavioral --auto-learn

# Interactive mode (asks about learning preferences)
./run.sh learn "Robert Sapolsky" --scope behavioral --interactive

# Check learning progress (includes task-monitor state with ETA)
./run.sh status --scope behavioral

# Run nightly persona update
./run.sh nightly --scope behavioral
```

## Commands

### `ask` — Query Accumulated Knowledge

```bash
./run.sh ask <question> [options]
./run.sh ask Brandon what is the state of space-based cybersecurity in 2016? --scope sparta

Options:
  --scope <scope>         Memory scope to query (default: "ask")
  --k <n>                 Number of results (default: 5)
  --bridges               Also traverse bridge attributes (multi-hop)
  --auto-learn            Auto-discover and learn if no knowledge found
  --collection <coll>     Taxonomy collection for auto-learn (default: behavioral)
  --consult-personas      Find and suggest relevant personas to consult
  --persona-scope <scope> Scope to search for personas (default: personas)
  --hybrid                Use hybrid RAG+QRA retrieval
  --oracle                Use scillm/Codex for final oracle synthesis
  --oracle-backend <b>    Oracle backend: auto, scillm, subagent-runner
  --oracle-model <model>  Oracle synthesis model (default: gpt-5.5)
  --oracle-reasoning <r>  Oracle reasoning effort (default: high; deep-review default: xhigh)
  --oracle-timeout <sec>  Oracle HTTP timeout in seconds (default: 300)
  --oracle-idle-timeout <sec> Subagent silence timeout before stalled recovery (default: 300)
  --oracle-heartbeat-interval <sec> Memory heartbeat write interval (default: 30)
  --oracle-persona <p>    Primary persona/subagent for oracle synthesis
  --oracle-peer <p>       Second persona/subagent for oracle deliberation
  --oracle-persona-model <m> Model for primary persona turns
  --oracle-peer-model <m> Model for peer persona turns
  --oracle-iterations <n> Sequential oracle deliberation calls (default: 1)
  --roundtable          Run sequential protocolized persona deliberation
  --roundtable-personas <p> Comma-separated persona[:protocol_role] participants
  --roundtable-role-preset <p> Role preset (default: adversarial-review)
  --roundtable-rounds <n> Number of full participant rounds (default: 2)
  --roundtable-mode <m> Mode label (default: adversarial)
  --roundtable-persist <summary|full> Persist compact protocol state or full turns
  --argue                Run two parallel /scillm advocates followed by a judge
  --decision-required    Force FOR/AGAINST with uncertainty disclosure
  --tie-breaker <policy> Tie-breaker for --decision-required
  --parallel-review     Run independent parallel adversarial reviewers
  --parallel-reviewers <n> Number of default reviewers (default: 3)
  --parallel-review-personas <p> Comma-separated reviewer persona[:protocol_role] specs
  --parallel-review-focus <f> Comma-separated focus labels for default reviewers
  --parallel-review-role-preset <p> Role preset for parallel reviewers
  --cae-gap-review      Run evidence-case-backed CAE/QRA gap review
  --cae-reviewers <p>   Comma-separated CAE persona:role pairs
  --cae-judge <p>       CAE judge persona label
  --cae-max-rounds <n>  Maximum CAE clarify/reroute rounds
  --deep-review          Run read-only deep review with review.md and review.json artifacts
  --deep-review-target <target> Explicit target: paths, diff, plan, manifest, or artifact
  --deep-review-profile <p> Deep-review profile label (default: max_available)
  --deep-reviewers <n> Reviewer breadth requested for deep review (default: 5)
  --deep-review-focus <f> Comma-separated deep-review focus labels
  --deep-review-fallback-policy <fail_closed|warn> Downgrade behavior
  --deep-review-persist <summary|full> Persist compact metadata or full review state
  --deep-review-output-root <dir> Artifact root (default: .ask_artifacts/deep-review)
  --chain <name|path>   Saved review chain spec (e.g. deep-review-safety)
  --reviewer-spec <name|path> Reviewer role/focus spec (repeatable)
  --dogpile <auto|off|force> Freshness policy for date-sensitive oracle prompts
  --dry-run             Emit execution spec/risk analysis without mutation
  --ask-id <id>          Stable runtime artifact id for this ask call
  --run-output-root <dir> Runtime artifact root (default: .ask_artifacts/runs or ASK_RUN_OUTPUT_DIR)
  --overwrite            Replace an existing run directory for --ask-id
  --resume               Resume a non-terminal existing run directory for --ask-id
  --raw                   Return raw memory results (no synthesis)
  --image-generate        Generate image artifact(s) through scillm
  --image-model <model>   Image generation model (default: gpt-image-2)
  --image-size <size>     Image size, for example auto or 1024x1024
  --image-quality <q>     Image quality, for example auto, medium, or high
  --image-count <n>       Number of images to generate (default: 1)
  --image-output <path>   Output file or directory for generated image(s)
  --image-output-format <fmt> Image file format: png, jpeg, or webp
  --image-timeout <sec>   Image generation timeout in seconds (default: 300)
  --json                  JSON output
  --debug                 Enable debug logging
```

Runtime artifacts:

```text
.ask_artifacts/runs/<ask_id>/
  <ask_id>.request.json
  <ask_id>.status.json
  <ask_id>.events.jsonl
.ask_artifacts/runs/index.jsonl
```

`request.json` captures the normalized routed request before mutation or oracle
execution. `status.json` is atomically replaced as the run progresses.
`events.jsonl` is append-only and records lifecycle events such as
`request_written`, `ask_started`, `memory_recall_started`,
`memory_recall_finished`, `evidence_case_started`, `synthesis_finished`,
`finished`, and `failed`.

When a run cannot safely continue, `status.json` uses `state:
needs_attention` and includes a structured `needs_attention` object with
`reason`, `question`, `safe_default`, and `resume_hint`. Deep review pauses this
way when the target is missing instead of guessing repo scope.

Inspect a run:

```bash
./run.sh status --run <ask_id> --tail-events 25
./run.sh status --run .ask_artifacts/runs/<ask_id> --json
./run.sh status --run <ask_id> --watch --watch-timeout-seconds 300
./run.sh status --run <ask_id> --serve --open
./run.sh status --runs --limit 10
./run.sh status --prune --older-than-days 14 --dry-run
```

`status --run <ask_id> --serve` writes a read-only HTML monitor into the run
directory and serves it from `127.0.0.1` with a random query token. The viewer
polls `status.json`, `events.jsonl`, and `request.json` so long-running
`argue`, `parallel-review`, `deep-review`, and SPARTA evidence-case routes are
not black boxes. The server auto-shuts down after terminal state plus TTL.

Runtime safety:
- Generated run IDs include timestamp, question digest, and random suffix to avoid same-second collisions.
- Explicit `--ask-id` reuse is rejected by default so event logs cannot mix separate runs.
- `--overwrite` is explicit and replaces a prior run directory; `--resume` is explicit and only allowed for non-terminal runs.
- Plain `/ask` degrades to a no-op runtime state if artifact writes fail; deep review and parallel review fail closed.
- `status --prune` removes only validated direct-child `ask.runtime.v1` run directories whose `ask_id` and `artifacts.run_dir` match the directory.
- `status --watch` has a bounded timeout and exits nonzero if the run never reaches a terminal state.
- `status --serve` is read-only, localhost-bound, token-gated, and intended for
  human inspection of run artifacts; it must not mutate answers or retry nodes.
- Runtime artifacts are validated by doctor against the deterministic request/status/event schema.
- `status --runs` reads the append-only `index.jsonl` first, then falls back to directory scanning.

Dry-run preview:

```bash
./run.sh ask "safe to proceed?" --deep-review --dry-run --json
./run.sh learn "Lisa Feldman Barrett" --dry-run
./run.sh nightly --dry-run --json
./run.sh os learn --dry-run --json
```

Dry-run mode emits `ask.dry_run.v1` execution specs with planned steps, external
calls, filesystem writes, memory writes, and risk notes. It exits before runtime
artifacts, memory writes, oracle calls, dogpile calls, or ingestion subprocesses.

Saved review specs:

```bash
./run.sh ask "review this runtime layer" \
  --chain deep-review-safety \
  --reviewer-spec security \
  --reviewer-spec qa \
  --deep-review-target src/ask/run_state.py
```

Built-in specs live under `docs/chains/` and `docs/reviewers/`. Historical
and active implementation/orchestration plans live under `docs/plans/`. Chain
specs set deterministic workflow options; reviewer specs contribute protocol
role/focus labels without making the agent infer the review contract.

Preflight the runtime:

```bash
./run.sh config doctor --profile release --json
./run.sh config init
./run.sh doctor
./run.sh doctor --json
./run.sh doctor --live --json
```

`config doctor` is non-interactive and safe for CI/release sanity. Missing config,
credentials, Docker storage, or companion service paths return `needs_attention`
with `safe_default=do_not_claim_release_ready`. `config init` is the interactive
repair path and may call `/interview` to collect missing local values.

**Oracle Synthesis:**

`--oracle` keeps `/ask` retrieval, bridge traversal, and optional auto-learn local, then makes
focused oracle calls for final synthesis. The default model is `gpt-5.5` with `high`
reasoning. Backend `auto` uses direct scillm for simple one-shot calls and
`subagent-runner` for persona/iteration deliberation:

```bash
./run.sh ask "What should we do next?" --oracle
./run.sh ask "What should we do next?" --oracle --oracle-backend subagent-runner --oracle-model gpt-5.5 --oracle-reasoning high
```

For deliberation, set `--oracle-iterations` and optional persona roles. `/ask` will run sequential
subagent-style oracle calls, feeding each turn into the next:

```bash
./run.sh ask "What should we do next?" --oracle \
  --oracle-backend subagent-runner \
  --oracle-persona "systems architect" \
  --oracle-peer "skeptical reviewer" \
  --oracle-iterations 3
```

Natural peer syntax is also supported:

```bash
./run.sh ask Brandon ask Margaret where are we weak?
```

This maps to `--oracle-persona Brandon --oracle-peer Margaret --oracle-iterations 2`
with `subagent-runner`. Do not have subagents recursively call `/ask` for peer
questions unless the human explicitly asks for recursive calls; `/ask` should
orchestrate persona-to-persona turns. For same-model persona dialogue, `/ask`
uses one subagent session and has it switch personas dynamically so it keeps the
full subagent conversation context. Separate sessions are only for isolation,
parallelism, or different peer model backends such as DeepSeek via `/scillm`.

**Ask-backed design review loops:**

When `$ask` is combined with `$review-design`, route the request as a bounded
review-design critique loop, not as a generic Q&A answer. Leading model
shorthand still applies. For example, `$ask oc kimi for a $review-design with
maximum 3 rounds` resolves the reviewer model to `opencode-go/kimi-k2.6`
through `/scillm`.

Required behavior:

1. Capture or accept the current screenshot bundle for the UI surface.
2. Send the screenshot(s), design constraints, and review-design verdict schema
   to the resolved reviewer model.
3. Require a structured verdict: `satisfied`, `needs_changes`, or `blocked`.
4. If the verdict is `needs_changes`, the project agent patches the UI, captures
   a fresh screenshot, and asks the reviewer again.
5. Stop at the first `satisfied` verdict, concrete blocker, or requested maximum
   round count.

The round cap is literal. "maximum 3 rounds" means no more than three reviewer
verdict calls. The reviewer must inspect a fresh rendered screenshot before
marking the design satisfied.

Peer turns can use any one-shot model supported by `/scillm`. This lets a Codex
subagent converse with DeepSeek V4, MiniMax, Gemini, or other scillm routes:

```bash
./run.sh ask "What should we do next?" --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-persona "systems architect" \
  --oracle-peer "DeepSeek V4 critic" \
  --oracle-peer-model opencode-go/deepseek-v4-pro \
  --oracle-iterations 3
```

If `--consult-personas` is also set, suggested personas are included as advisory subagent context,
and the top suggestion is used as the deliberation peer when `--oracle-peer` is omitted.

When `--oracle-persona`, `--oracle-peer`, or `--consult-personas` names a stored persona,
`/ask` recalls the actual persona profile from `/memory` and includes it in the oracle context.
For example, `--oracle-persona Brandon` resolves to the stored Brandon Bailey profile when present.
Runner-backed Codex subagents also receive explicit instructions and environment access to call
the core oracle tool belt themselves during the session:

```bash
$ASK_ORACLE_MEMORY_RUN recall --q "Persona: Brandon Bailey"
$ASK_ORACLE_SCILLM_RUN warm-check --json
$ASK_ORACLE_DOGPILE_RUN --help
```

Core tool rules for oracle subagents:
- `/memory` is mandatory for stored facts, actual personas, persona lessons, persona lore, prior lessons, and database state.
- If no persona is specified, the oracle should use `/memory recall` as the primary persona selector because it already combines semantic, BM25, and graph traversal over persona lessons/lore; `/monitor-personas` is only an optional readiness/ops check.
- Persona subagents must assume their persona may have stored lessons/lore and query it before answering from that persona's perspective.
- Persona subagents may store a concise `/memory learn` record when the conversation produces a durable, reusable lesson; do not store transient chatter or secrets.
- `/scillm` is available for one-shot peer model checks, not batch loops.
- `/dogpile` is available for fresh external discovery only; do not use it for private/internal facts.
- Subagents must state whether an answer used memory context, scillm peer checks, dogpile discovery, or inference.

Use oracle mode for single high-value questions, not nightly runs or batch ingestion loops.

**Roundtable, Argue, Parallel Review, and CAE Gap Review Modes:**

`/ask` supports four distinct review protocols:

- `--parallel-review`: independent reviewers inspect the same artifact/question concurrently, then a neutral moderator synthesizes findings.
- `--argue`: a FOR advocate and AGAINST advocate run in parallel through `/scillm`; a sequential judge decides or abstains, then a deterministic verifier gates the verdict.
- `--roundtable`: selected personas speak sequentially through a state-machine protocol; each turn must reference prior claims and critiques.
- `--cae-gap-review`: `/create-evidence-case` builds or loads the QRA/evidence snapshot first; Brandon, Margaret, and Jennifer review policy evidence, technical enforcement, and control mapping; a judge reroutes one missing evidence item per round before halting.

Use both together when you want independent findings first, followed by persona debate over those findings.

Citation rule: `/ask` uses `ask.citations.v1` across answer surfaces. Memory
citations support knowledge/persona/project-context answers, but never code or
review safety claims. Safe review claims must cite target/file/diff/artifact
sources, and verifier gates reject missing or inadmissible citations.

The narrow contract for reviewer fanout is documented in
`docs/ASK_PARALLEL_REVIEW_CONTRACT.md`. The key boundary is that `/ask`
owns target resolution, read-only reviewer roles, synthesis, verifier gates, and
artifacts; `/code-runner` owns implementation, and Pi/subagent adapters only
provide bounded execution mechanics.

Personas and protocol roles are separate:

```text
persona = domain/voice/source-of-judgment
protocol_role = job in the review loop
```

Explicit role assignment:

```bash
./run.sh ask "Formal Methods in large scale aerospace projects in 2026" \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer" \
  --roundtable-rounds 2 \
  --dogpile auto
```

Natural roundtable syntax:

```bash
./run.sh ask Brandon, Margaret, and Jennifer to debate the relevance of Formal Methods in large scale aerospace projects in 2026
```

This maps to:

```bash
./run.sh ask "the relevance of Formal Methods in large scale aerospace projects in 2026" \
  --roundtable \
  --roundtable-personas "Brandon,Margaret,Jennifer" \
  --roundtable-role-preset adversarial-review \
  --roundtable-rounds 2 \
  --oracle-backend subagent-runner \
  --dogpile auto
```

Parallel review:

```bash
./run.sh ask "Review this implementation" \
  --parallel-review \
  --parallel-reviewers 3 \
  --parallel-review-focus correctness,tests,maintainability
```

Argue:

```bash
./run.sh ask "Should we ship this reversible runtime change?" \
  --argue
```

Forced binary decision:

```bash
./run.sh ask "Should we ship this reversible runtime change?" \
  --argue \
  --decision-required \
  --tie-breaker more-reversible
```

Review then roundtable:

```bash
./run.sh ask "Review this architecture" \
  --parallel-review \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer"
```

CAE/QRA gap review:

```bash
./run.sh ask "cae gap review AC-2 MFA evidence for the production tenant" \
  --cae-reviewers "Brandon:cae_policy_evidence,Margaret:cae_technical_enforcement,Jennifer:cae_control_mapping" \
  --cae-judge "CAE Gap Judge" \
  --cae-max-rounds 3
```

CAE gap review is a post-evidence-case review layer, not the QRA generator and
not a compliance oracle. The QRA claim, answer, controls, and `evidence_case`
snapshot stay fixed. The only adaptive behavior is targeted recurrence: when the
judge returns `NEEDS_CLARIFICATION`, `/ask` reroutes exactly one missing evidence
item to the matching CAE reviewer role, then asks the judge again. It halts on a
terminal judge decision, repeated missing evidence, invalid judge JSON, model
failure, or the max round limit.

Use it in the QRA lifecycle as:

```text
generated QRA
  → candidate QRA
  → CAE gap review
  → human review
  → approve / edit / reject / defer
  → promote to sparta_qra or keep as gap
```

Protocol rules:
- Critiques must anchor to specific claims.
- Each participant must add a non-trivial disagreement or justify why none exists.
- Critique and synthesis are separate; the moderator performs final synthesis.
- Default persistence stores compact state, durable lessons, unresolved issues, and critique summaries.
- SPARTA and space-cybersecurity questions use the deterministic SPARTA preflight
  contract in `docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md`: preserve the question
  text, run `/extract-entities` and `/memory` recall first, route grounded
  SPARTA-corpora matches to `/create-evidence-case`, fail closed with
  `needs_attention` and `safe_default=do_not_answer_as_grounded` when required
  evidence-case creation is unavailable or fails, and continue normal `/ask`
  routing only when no grounded match is found.
- SPARTA-corpora match signals are only extractor-grounded resolved control IDs,
  control metadata for SPARTA/CWE/NIST/CAPEC/ATT&CK, related/crosswalk pairs,
  taxonomy tags, or SPARTA recall items. Unresolved or fabricated SPARTA-looking
  references require `needs_attention`; never fabricate a control, crosswalk,
  relationship, or compliance status. All CAE/evidence-case outputs default to
  `NEEDS_VERIFICATION` and require human review before any status change.
  structured citations, and what would change the verdict. See
  `docs/ASK_ARGUE_CONTRACT.md`.

**Deep Review Mode:**

Use deep review when the human wants a comprehensive, Web-GPT-style review
without copy-paste into the browser. Deep review is not `/code-runner`; it must
produce analysis and artifacts, not patches.

```bash
./run.sh ask "deep review this implementation" \
  --deep-review \
  --deep-review-target src/ask/ask.py \
  --deep-reviewers 5 \
  --deep-review-focus boundaries,fail-closed,tests,auditability \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-reasoning xhigh
```

Deep review writes:

```text
.ask_artifacts/deep-review/<timestamp>/review.md
.ask_artifacts/deep-review/<timestamp>/review.json
```

When deep review runs under an `--ask-id`, those `review.md` and `review.json`
paths are also registered in `<ask_id>.status.json` under `artifacts`.

Deep review verifier rules:
- Reject missing or `not_assessed` required sections.
- Reject `SAFE` or `SAFE_WITH_CONDITIONS` without inspected evidence.
- Reject major findings that lack evidence, impact, fix, or verification.
- Reject unexpected non-artifact file changes from before/after git status.
- Treat JSON as an audit gate, not proof of reasoning quality.

Every `/ask` execution is logged to `/memory` collection `ask_call_log` with
question, scope, persona, oracle backend, model, iteration count, status, and
duration. This telemetry is the basis for future data-driven timeout selection.

Runner-backed oracle calls also have heartbeat/recovery telemetry:
- `/subagent-runner` emits transcript delta and heartbeat events while the PTY
  session is alive.
- `/ask` follows runner `events.jsonl` as the primary liveness channel and falls
  back to status polling only when necessary.
- If transcript output is silent for `--oracle-idle-timeout`, the runner marks
  the session `stalled` and terminates the process group.
- `/ask` writes sparse heartbeat snapshots to `/memory` collection
  `ask_subagent_heartbeat`.
- Heartbeat records include session id, artifact dir, persona, model, turn number, status, transcript byte count, `last_output_age_ms`, timeout, and idle timeout.
- On `stalled`, `timed_out`, `failed`, or `cancelled`, `/ask` returns the terminal status plus the transcript tail so the project agent can recover or retry with a different timeout/model.
- E2E validators must fail empty answers, `No answer could be synthesized`,
  refusal-style non-answers, missing domain grounding, wrong persona routing, or
  missing roundtable participants.

**Oracle Backend Decision Table:**

| User intent | Use | Why |
|-------------|-----|-----|
| One direct high-reasoning answer | `--oracle --oracle-backend scillm` | Fast path through `/scillm` |
| Focused Codex agent answer | `--oracle --oracle-backend subagent-runner` | Runs a real Codex CLI subagent session |
| Persona or peer deliberation | `--oracle --oracle-backend auto --oracle-iterations 2+` | `auto` selects `subagent-runner` |
| N-persona sequential debate | `--roundtable --roundtable-personas ...` | State-machine review protocol with claim anchoring |
| Two-sided calibrated decision | `--argue` | Two parallel `/scillm` advocates, sequential judge, verifier gate |
| N independent adversarial reviewers | `--parallel-review --parallel-reviewers N` | Parallel breadth before moderator synthesis |
| Independent findings then debate | `--parallel-review --roundtable` | Best for high-stakes review |
| Web-GPT-style deep review | `--deep-review --deep-review-target <target>` | Pass-based review with `review.md` and `review.json` |
| GPT-5.5 vs DeepSeek/Gemini/MiniMax debate | `--oracle-peer-model <scillm-model>` | Codex turn uses runner; peer turn uses `/scillm` |
| Batch/nightly ingestion | Do not use oracle | OAuth models and subagents are not batch lanes |

**How to Prompt an Agent to Use `/ask` Oracle:**

Natural user prompts should map to these commands:

```text
Use $ask oracle on "should subagent-runner replace direct scillm for focused agent calls?"
```

```bash
./run.sh ask "should subagent-runner replace direct scillm for focused agent calls?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high
```

```text
Use $ask oracle with 3 rounds: architect vs skeptical reviewer.
```

```bash
./run.sh ask "<question>" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-persona "systems architect" \
  --oracle-peer "skeptical reviewer" \
  --oracle-iterations 3
```

```text
Use $ask oracle and have GPT-5.5 converse with DeepSeek V4.
```

```bash
./run.sh ask "<question>" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-persona "GPT-5.5 architect" \
  --oracle-peer "DeepSeek V4 critic" \
  --oracle-peer-model opencode-go/deepseek-v4-pro \
  --oracle-iterations 3
```

**Correct Usage Examples:**

```bash
# Ask memory first, then use GPT-5.5 high reasoning as the final oracle.
./run.sh ask "What is the best architecture for X?" --oracle

# Force direct scillm when you want a single fast oracle call.
./run.sh ask "Summarize the tradeoff in one paragraph." \
  --oracle --oracle-backend scillm

# Force a real Codex subagent session.
./run.sh ask "Analyze this design decision." \
  --oracle --oracle-backend subagent-runner

# Let /ask suggest personas and include them in oracle context.
./run.sh ask "How should we improve visual hierarchy?" \
  --consult-personas --oracle --oracle-iterations 2
```

**Incorrect Usage Examples:**

```bash
# WRONG: Using oracle mode for many independent items.
for q in "${questions[@]}"; do ./run.sh ask "$q" --oracle; done

# RIGHT: Use normal /ask or batch-capable /scillm lanes for bulk work.
./run.sh ask "one high-value question" --oracle
```

```bash
# WRONG: Assuming --oracle-peer changes the model.
./run.sh ask "question" --oracle --oracle-peer "DeepSeek critic"

# RIGHT: Set the peer model explicitly for scillm one-shot model turns.
./run.sh ask "question" --oracle \
  --oracle-peer "DeepSeek critic" \
  --oracle-peer-model opencode-go/deepseek-v4-pro \
  --oracle-iterations 2
```

```bash
# WRONG: Asking for persona deliberation with --raw.
./run.sh ask "question" --raw --oracle --oracle-iterations 3

# RIGHT: Oracle synthesis requires synthesized context, so omit --raw.
./run.sh ask "question" --oracle --oracle-iterations 3
```

```bash
# WRONG: Treating /ask as a replacement for fresh web search.
./run.sh ask "latest price/news today" --oracle

# RIGHT: Use /dogpile or a search-capable skill first, then ask the oracle over gathered context.
./run.sh ask "question over learned or retrieved context" --oracle
```

**Persona Routing:**

When `--consult-personas` is enabled, /ask uses Federated Taxonomy bridges to find
personas best suited to answer the question:

```bash
./run.sh ask "How should we improve visual hierarchy in the UI?" --consult-personas

# Output:
#   Suggested personas to consult:
#     - Paula Scher (Graphic Designer) [Precision]
#     - Don Norman (Cognitive Scientist) [Precision, Loyalty]
```

This enables cross-persona knowledge queries where Embry can automatically
identify that Paula Scher should be consulted for typography questions.

**Auto-Learn Flow:**
```
Question → Memory Recall → No results?
  YES → Learn Pipeline (dogpile → YouTube → web → QRA → store)
      → Re-query Memory → Return answer with multi-hop traversal
  NO  → Return answer directly with bridge connections
```

### `learn` — Discover and Ingest Knowledge

```bash
./run.sh learn <topic> [options]

Options:
  --scope <scope>         Memory scope (default: "ask")
  --collection <coll>     Taxonomy collection (lore, operational, sparta, behavioral)
  --depth <level>         Learning depth: quick (5-10min), standard (30-60min), deep (hours)
  -i, --interactive       Use /interview to ask about learning preferences
  --youtube <url>         Specific YouTube URL to ingest (repeatable)
  --books-only            Only discover and process books
  --youtube-only          Only process YouTube content
  --max-books <n>         Max books to discover (default: 5)
  --max-videos <n>        Max YouTube videos to process (default: 3)
  --dry-run               Preview what would be ingested without storing
  --ask-id <id>           Stable runtime artifact id for this learn call
  --run-output-root <dir> Runtime artifact root (default: .ask_artifacts/runs or ASK_RUN_OUTPUT_DIR)
  --overwrite             Replace an existing run directory for --ask-id
  --resume                Resume a non-terminal existing run directory for --ask-id
  --debug                 Enable debug logging
```

**Learning Depths:**

| Depth | Time | Videos | Books | ArXiv | Use Case |
|-------|------|--------|-------|-------|----------|
| `quick` | 5-10 min | 3 | 0 | 0 | Quick overview, verify facts |
| `standard` | 30-60 min | 5 | 3 | 3 | Moderate understanding |
| `deep` | 2-6 hours | 10+ | 5 | 10 | Comprehensive persona building |

**Persona Detection:**
When the topic looks like a person's name (e.g., "Lisa Feldman Barrett", "Dr. Robert Sapolsky"),
the skill automatically:
- Stores a persona profile to memory
- Searches for additional lectures by the person
- Downloads books by/about the person
- Creates a queryable knowledge base

### `status` — Learning Progress

```bash
./run.sh status [options]

Options:
  --scope <scope>         Filter by scope
  --run <id|path>         Show runtime status for an ask id, run directory, or status file
  --tail-events <n>       Include the last N runtime events with --run
  --watch                 Watch runtime status until terminal
  --watch-timeout-seconds <n> Maximum seconds to wait with --watch
  --poll-interval-seconds <n> Polling interval for --watch
  --serve                 Serve a local read-only HTML viewer for --run
  --open                  Open the local HTML viewer in a browser
  --serve-port <n>        Port for --serve; 0 selects a free port
  --serve-ttl-seconds <n> Seconds to keep viewer alive after terminal state
  --runs                  List recent runtime runs
  --limit <n>             Maximum runs to list with --runs
  --prune                 Prune old runtime run directories
  --older-than-days <n>   Age threshold for --prune (default: 14)
  --dry-run               Preview --prune without deleting
  --run-output-root <dir> Runtime artifact root for --run ids
  --json                  JSON output
  --debug                 Enable debug logging
```

Shows:
- Total knowledge items in scope
- Persona profiles
- Q-R-A pairs count
- Last task-monitor state (steps, timing, stats, ETA)

### `nightly` — Scheduled Persona Updates

```bash
./run.sh nightly [options]

Options:
  --scope <scope>         Memory scope to update (default: ask)
  --persona <name>        Update a single persona by name
  --dry-run               Preview without storing
  --ask-id <id>           Stable runtime artifact id for this nightly call
  --run-output-root <dir> Runtime artifact root (default: .ask_artifacts/runs or ASK_RUN_OUTPUT_DIR)
  --overwrite             Replace an existing run directory for --ask-id
  --resume                Resume a non-terminal existing run directory for --ask-id
  --json                  Output summary as JSON
  --debug                 Enable debug logging
```

**Nightly Update Flow:**
1. Query memory for all stored persona profiles
2. For each persona, search for new content since last update
3. Ingest new YouTube videos, papers, news articles
4. Update persona profile with new sources
5. Report summary via task-monitor

### `os` — Query Embry-OS Internals

```bash
# Index OS knowledge (skills, packages, config)
./run.sh os learn --depth quick --dry-run
./run.sh os learn --depth standard
./run.sh os learn --depth quick --dry-run --ask-id os-preview

# Query OS knowledge
./run.sh os ask "what does the /dogpile skill do?"
./run.sh os ask "which skills provide memory?" --json
./run.sh os ask "which skills provide memory?" --ask-id os-memory-query

# Query runtime health
./run.sh os health "is memory healthy?"
./run.sh os health "check workstation" --subsystem workstation
./run.sh os health "is memory healthy?" --ask-id os-memory-health

# Classify query intent
./run.sh intent "how does the memory skill work?"
```

**OS Learn** crawls `.pi/skills/*/SKILL.md`, `packages/*/package.json`, `.pi/config.toml`,
and `.pi/extensions/*.ts`. Generates QRA triples tagged with `scope=os`, bridge attributes,
and source metadata (skill, package, config, extension).

**OS Health** dispatches to the relevant monitor/ops skill (e.g., `monitor-memory health --json`)
and combines runtime data with static knowledge from memory.

**Intent Classifier** routes queries through a 3-stage pipeline:
1. Memory cache (~1ms) — cached classifications
2. Rule-based heuristics (<5ms) — regex pattern matching
3. LLM fallback (1-5s) — scillm classification when uncertain

## Architecture

```
Agent: "Lisa Feldman Barrett how might we improve our memory system?"
                    │
                    ▼
            ┌──────────────┐
            │ Persona Detect│  ← Is this a person?
            └──────┬───────┘
                   │
            ┌──────┴───────┐
            │ Memory Recall │  ← Check what we already know
            └──────┬───────┘
                   │
              Items found?
              ┌────┴────┐
             YES        NO + --auto-learn
              │          │
              │    ┌─────┴──────────────────────────────────┐
              │    │ Learn Loop (multi-source, multi-hour)  │
              │    │                                         │
              │    │ 1. /dogpile (Brave + Perplexity + etc)  │
              │    │ 2. YouTube ingest (lectures, interviews)│
              │    │ 3. Web fetch (blogs, articles)          │
              │    │ 4. discover-books (OpenLibrary)         │
              │    │ 5. extractor --format qra               │
              │    │ 6. memory learn + persona profile       │
              │    │                                         │
              │    │ (tracked via task-monitor with ETA)     │
              │    └─────┬──────────────────────────────────┘
              │          │
              │    ┌─────┴──────┐
              │    │ Re-query   │
              │    └─────┬──────┘
              │          │
              └────┬─────┘
                   │
            ┌──────┴───────┐
            │  Synthesize  │  ← Combine results
            └──────┬───────┘
                   │
            ┌──────┴────────────────┐
            │ Federated Taxonomy    │  ← Multi-hop bridge traversal
            │ (Corruption, Precision,│
            │  Resilience, etc.)     │
            └───────────────────────┘
```

## Task-Monitor Integration

Every `learn` session registers with `/task-monitor`:

- **Registry**: `~/.pi/task-monitor/registry.json`
- **State file**: `.pi/skills/ask/ask_task_state.json` (atomic writes)
- **Steps tracked**: `memory_check → dogpile → ingest_youtube → fetch_web → extractor_qra → store`
- **Sub-steps**: Individual items within each step (e.g., each video URL)
- **ETA**: Estimated time remaining based on depth and progress
- **Stats**: books_discovered, youtube_ingested, web_fetched, qra_extracted, items_stored

```bash
# View real-time progress
uv run --project .pi/skills/ask python -m json.tool < .pi/skills/ask/ask_task_state.json

# Example state output:
{
  "completed": 3,
  "total": 6,
  "progress_pct": 55.0,
  "current_item": "ingest_youtube",
  "current_detail": "https://youtube.com/watch?v=...",
  "substep_current": 2,
  "substep_total": 5,
  "eta_seconds": 180.0,
  "eta_display": "~3 min remaining",
  "depth": "standard"
}

# Via task-monitor TUI
cd ~/.pi/skills/task-monitor
uv run python monitor.py tui --filter ask
```

## Federated Taxonomy Integration

Knowledge is tagged with bridge attributes for multi-hop graph traversal:

| Bridge | Meaning | Example Topics |
|--------|---------|----------------|
| Corruption | Moral decay, entropy | Power dynamics, institutional failure |
| Precision | Exactness, clarity | Scientific method, measurement |
| Resilience | Recovery, adaptation | Stress response, neuroplasticity |
| Fragility | Vulnerability | Trauma, system failure |
| Stealth | Hidden operations | Unconscious processes |

**Multi-hop Query Example:**
```
Query: "How does stress affect decision-making?"
          │
          ├── Direct hits: Stress research papers
          │
          └── Bridge traversal:
              ├── [Resilience] → Neuroplasticity studies
              ├── [Fragility] → Trauma responses
              └── [Corruption] → Decision biases under stress
```

## Memory Scopes

| Scope | Use |
|-------|-----|
| `behavioral` | Psychology, neuroscience, behavioral studies |
| `ask` | General learning (default) |
| Custom | Any scope name you provide |

## Environment

| Variable | Purpose |
|----------|---------|
| `ASK_DEFAULT_SCOPE` | Override default memory scope |
| `ASK_NIGHTLY_SCOPE` | Scope for nightly updates |
| `ASK_MAX_BOOKS` | Override default max books to discover |
| `ASK_MAX_VIDEOS` | Override default max videos |
| `ASK_ORACLE_MODEL` | Override default oracle model (default: `gpt-5.5`) |
| `ASK_ORACLE_REASONING` | Override default oracle reasoning effort (default: `high`) |
| `ASK_ORACLE_TIMEOUT` | Override default oracle timeout seconds (default: `300`) |
| `ASK_ORACLE_IDLE_TIMEOUT` | Override subagent silence timeout before `stalled` (default: `300`) |
| `ASK_ORACLE_HEARTBEAT_INTERVAL` | Override heartbeat write interval seconds (default: `30`) |
| `ASK_ORACLE_BACKEND` | Override oracle backend (default: `auto`) |
| `ASK_RUN_OUTPUT_DIR` | Override runtime artifact root for request/status/events files |
| `ASK_SUBAGENT_RUNNER` | Path to subagent-runner `run.sh` |
| `ASK_SUBAGENT_OUTPUT_DIR` | Output directory for oracle subagent artifacts |
| `ASK_MEMORY_RUN` | Path to memory `run.sh` exposed to oracle subagents |
| `ASK_SCILLM_RUN` | Path to scillm `run.sh` exposed to oracle subagents |
| `ASK_DOGPILE_RUN` | Path to dogpile `run.sh` exposed to oracle subagents |
| `ASK_MONITOR_PERSONAS_RUN` | Path to monitor-personas `run.sh` exposed to oracle subagents |
| `SCILLM_BASE_URL` | scillm base URL for oracle synthesis (default: `http://localhost:4001`) |
| `SCILLM_API_KEY` | scillm bearer token for oracle synthesis (default: `sk-dev-proxy-123`) |
| `ASK_DEBUG` | Enable debug logging (set to any value) |
| `TASK_MONITOR_URL` | Task-monitor API URL for remote push |

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/dogpile` | Primary discovery engine (Brave, Perplexity, ArXiv, YouTube, GitHub) |
| `/memory` | Knowledge storage and retrieval |
| `/project-knowledge` | Curated human-readable current-state document for `/ask` development |
| `/discover-books` | Book discovery via OpenLibrary |
| `/ingest-youtube` | YouTube transcript extraction |
| `/fetcher` | Web content fetching |
| `/extractor` | Document extraction with QRA mode |
| `/taxonomy` | Federated Taxonomy tagging |
| `/interview` | Interactive preference gathering |
| `/task-monitor` | Progress tracking with ETA |
| `/scheduler` | Nightly update scheduling |
| `/prompt-lab` | Prompt optimization for scillm calls |

## Persona Profiles

When learning about a person, a persona profile is stored to memory:

```json
{
  "name": "Lisa Feldman Barrett",
  "scope": "behavioral",
  "sources": {
    "dogpile_sections": 5,
    "books": 3,
    "youtube": 8,
    "web": 4
  },
  "stats": {
    "qra_extracted": 45,
    "stored": 46
  },
  "last_updated": "2024-01-15T10:30:00"
}
```

Query a persona:
```bash
./run.sh ask "How does Barrett define emotions?" --scope behavioral --bridges
```

## Nightly Scheduling

To run nightly persona updates automatically, use the `/scheduler` skill or cron:

```bash
# Via scheduler skill
./path/to/scheduler/run.sh add ask-nightly \
  --command ".agent/skills/ask/run.sh nightly --scope behavioral" \
  --schedule "0 3 * * *"  # 3 AM daily

# Via cron
# Add to crontab -e:
# 0 3 * * * /path/to/.agent/skills/ask/run.sh nightly --scope behavioral >> /var/log/ask-nightly.log 2>&1
```
