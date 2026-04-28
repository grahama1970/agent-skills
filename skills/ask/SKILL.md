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
  - ask argue
  - ask for and against
  - ask devil's advocate
  - ask both sides
  - ask deep review
  - ask safe to proceed
  - ask comprehensive review
  - ask persona roundtable about
  - ask N parallel reviewers
  - ask NIST control
  - ask SPARTA countermeasure
  - ask current architecture risk
  - ask the oracle as
  - ask oracle with persona
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
  version: "0.6.0"

provides:
  - ask
  - oracle-query
  - os-knowledge
composes:
  - memory
  - dogpile
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

Zero cognitive-load learning and querying interface. Runtime modes:

1. **Learn Mode** — Discover, ingest, and extract knowledge about a topic or persona
2. **Ask Mode** — Query accumulated knowledge with Federated Taxonomy multi-hop traversal
3. **Auto-Learn Mode** — Ask a question; if no knowledge exists, automatically learn then answer
4. **Nightly Mode** — Scheduled incremental updates to persona knowledge bases
5. **OS Mode** — Learn about and query embry-os internals, skills, packages, and runtime health
6. **Deep Review Mode** — High-reasoning, read-only review with `review.md` and `review.json`
7. **Doctor Mode** — Preflight `/memory`, `/dogpile`, `/scillm`, `/subagent-runner`, reviewer specs, chains, and artifact paths
8. **Run Status Mode** — Inspect recent `/ask` run ids, artifact directories, verifier status, and needs-attention state
9. **Chains Mode** — Inspect and validate saved deep-review and parallel-review chain specs

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
- Treat "argue", "for and against", "devil's advocate", or "both sides" as `--argue`.
- Treat "parallel reviewers", "adversarial reviewers", or "N reviewers" as `--parallel-review`.
- Treat "review then roundtable" as both `--parallel-review` and `--roundtable`.
- Treat "deep review", "comprehensive review", "safe to proceed", or "production readiness" as `--deep-review`; require or infer a concrete `--deep-review-target`.
- Treat date-sensitive words (`2026`, `current`, `latest`, `today`, `recent`) as `--dogpile auto`.
- Default high-value analytical questions to `--oracle --oracle-model gpt-5.5 --oracle-reasoning high`.

| Human chat prompt | Route |
|-------------------|-------|
| `$ask what do we know about the release checklist?` | Memory-backed ask synthesis |
| `$ask What is the state of Python packaging in 2026?` | Oracle with auto persona selection and `--dogpile auto` |
| `$ask What is the state of space-based cybersecurity in 2026?` | SPARTA-scoped oracle: `--scope sparta --oracle` |
| `$ask Brandon what is the state of space-based cybersecurity in 2016?` | Brandon persona oracle over `--scope sparta` |
| `$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: What is the state of cybersecurity in 2026?` | SPARTA-scoped sequential persona roundtable |
| `$ask Brandon what is the best way to review this API boundary?` | Brandon persona oracle subagent |
| `$ask Brandon persona about whether this retry design fails closed` | Brandon persona oracle over memory/project context |
| `$ask Brandon argue for and Margaret argue against using queues` | Two-sided FOR/AGAINST argue protocol with neutral judge |
| `$ask devil's advocate: should we enable deep-review by default?` | Default argue protocol with fixed judge rubric |
| `$ask Brandon critique this architecture` | Brandon persona critique |
| `$ask Brandon ask Margaret where are we weak?` | Safe Brandon→Margaret peer deliberation |
| `$ask Brandon, Margaret, and Jennifer personas to roundtable about the topic: Should this service use retries or queues?` | Sequential protocolized persona roundtable |
| `$ask run 3 parallel adversarial reviewers on this implementation` | Independent parallel review plus moderator synthesis |
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

# Preflight ask dependencies and runtime objects
./run.sh doctor --json

# Inspect recent ask/oracle/review runs
./run.sh status --runs --json

# Inspect saved review workflows
./run.sh chains list --json

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
  --argue                Run two-sided FOR/AGAINST argument with neutral judge
  --argue-personas <p>   Comma-separated FOR/AGAINST personas
  --argue-rounds <n>     Number of argument rounds (default: 2)
  --roundtable          Run sequential protocolized persona deliberation
  --roundtable-personas <p> Comma-separated persona[:protocol_role] participants
  --roundtable-role-preset <p> Role preset (default: adversarial-review)
  --roundtable-rounds <n> Number of full participant rounds (default: 2)
  --roundtable-mode <m> Mode label (default: adversarial)
  --roundtable-persist <summary|full> Persist compact protocol state or full turns
  --parallel-review     Run independent parallel adversarial reviewers
  --parallel-reviewers <n> Number of default reviewers (default: 3)
  --parallel-review-personas <p> Comma-separated reviewer persona[:protocol_role] specs
  --parallel-review-focus <f> Comma-separated focus labels for default reviewers
  --parallel-review-role-preset <p> Role preset for parallel reviewers
  --deep-review          Run read-only deep review with review.md and review.json artifacts
  --deep-review-target <target> Explicit target: paths, diff, plan, manifest, or artifact
  --deep-review-profile <p> Deep-review profile label (default: max_available)
  --deep-reviewers <n> Reviewer breadth requested for deep review (default: 5)
  --deep-review-focus <f> Comma-separated deep-review focus labels
  --deep-review-fallback-policy <fail_closed|warn> Downgrade behavior
  --deep-review-persist <summary|full> Persist compact metadata or full review state
  --deep-review-output-root <dir> Artifact root (default: .ask_artifacts/deep-review)
  --run-id <id>           Explicit run id for artifact/status correlation
  --review-context <fresh|fork> Child context policy for oracle/review runs
  --inherit-memory <yes|no|summary> Memory inheritance policy
  --inherit-skills <yes|no|selected> Skill inheritance policy
  --inherit-project-context <yes|no> Project-context inheritance policy
  --dogpile <auto|off|force> Freshness policy for date-sensitive oracle prompts
  --raw                   Return raw memory results (no synthesis)
  --json                  JSON output
  --debug                 Enable debug logging
```

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

**Roundtable and Parallel Review Modes:**

`/ask` supports two distinct adversarial review protocols:

- `--parallel-review`: independent reviewers inspect the same artifact/question concurrently, then a neutral moderator synthesizes findings.
- `--argue`: exactly two sides argue FOR and AGAINST, then a neutral judge scores the stronger argument.
- `--roundtable`: selected personas speak sequentially through a state-machine protocol; each turn must reference prior claims and critiques.

Use both together when you want independent findings first, followed by persona debate over those findings.

Personas and protocol roles are separate:

```text
persona = domain/voice/source-of-judgment
protocol_role = job in the review loop
```

Protocol roles are first-class reviewer specs in `docs/reviewers/*.md`.
Each spec uses YAML frontmatter for model, reasoning, fallback models, tools,
write policy, inheritance policy, and required output sections. Do not bury new
reviewer behavior only in this `SKILL.md`; add or update a reviewer spec.

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

Two-sided argue syntax:

```bash
./run.sh ask "Brandon argue for and Margaret argue against using queues"
./run.sh ask "devil's advocate: should we enable deep-review by default?"
./run.sh ask "Should this service use retries or queues?" \
  --argue \
  --argue-personas "Brandon,Margaret" \
  --argue-rounds 2 \
  --oracle-backend subagent-runner
```

The argue judge uses this fixed rubric by default:

- `evidence_strength`
- `failure_mode_coverage`
- `assumption_quality`
- `target_relevance`
- `falsifiability`
- `implementation_cost_or_risk`

Allowed verdicts are `FOR`, `AGAINST`, `NO_CLEAR_WINNER`, and `INSUFFICIENT_EVIDENCE`.
The prompt payload review bundle is `docs/prompts_review/ASK_ARGUE_PROMPT_PAYLOAD.md`.

Parallel review:

```bash
./run.sh ask "Review this implementation" \
  --parallel-review \
  --parallel-reviewers 3 \
  --parallel-review-focus correctness,tests,maintainability
```

Review then roundtable:

```bash
./run.sh ask "Review this architecture" \
  --parallel-review \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer"
```

Protocol rules:
- Critiques must anchor to specific claims.
- Each participant must add a non-trivial disagreement or justify why none exists.
- Critique and synthesis are separate; the moderator performs final synthesis.
- Default persistence stores compact state, durable lessons, unresolved issues, and critique summaries.
- Full transcript/state requires `--roundtable-persist full`.
- `--dogpile auto` marks date-sensitive prompts such as `in 2026`, `current`, `latest`, or `today` for fresh external discovery by oracle subagents.
- SPARTA and space-cybersecurity questions should use `--scope sparta` so memory
  retrieval uses the security corpus instead of `/ask` project notes.

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

Every serious run also has a standard run directory:

```text
.ask_artifacts/<mode>/<run_id>/request.json
.ask_artifacts/<mode>/<run_id>/status.json
.ask_artifacts/<mode>/<run_id>/events.jsonl
```

Saved review chains live in `docs/chains/*.chain.yaml`. Use them for repeatable
deep-review and parallel-review orchestration instead of adding more one-off
prompt branches.

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
./run.sh status --runs --json
./run.sh status --id <run_id>

Options:
  --scope <scope>         Filter by scope
  --runs                  Show recent /ask runtime runs
  --last <n>              Number of recent runs (default: 10)
  --id <run_id>           Show one runtime run
  --json                  JSON output
  --debug                 Enable debug logging
```

Shows:
- Total knowledge items in scope
- Persona profiles
- Q-R-A pairs count
- Last task-monitor state (steps, timing, stats, ETA)
- Recent run ids, artifact dirs, verifier status, and needs-attention state when `--runs` or `--id` is used

### `doctor` — Runtime Preflight

```bash
./run.sh doctor [options]

Options:
  --artifact-root <dir>   Override artifact root for the writable check
  --json                  JSON output
```

Checks:
- `/memory`, `/dogpile`, `/scillm`, `/subagent-runner`, and `/monitor-personas` runner availability
- artifact directory writability
- `git status` readability
- reviewer frontmatter specs
- saved review-chain specs

### `chains` — Saved Review Workflows

```bash
./run.sh chains list [--json]
./run.sh chains show deep-review [--json]
./run.sh chains validate [--json]
```

Use this command to inspect the saved `deep-review` and `parallel-review`
state-machine specs before launching expensive review runs.

### `nightly` — Scheduled Persona Updates

```bash
./run.sh nightly [options]

Options:
  --scope <scope>         Memory scope to update (default: ask)
  --persona <name>        Update a single persona by name
  --dry-run               Preview without storing
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

# Query OS knowledge
./run.sh os ask "what does the /dogpile skill do?"
./run.sh os ask "which skills provide memory?" --json

# Query runtime health
./run.sh os health "is memory healthy?"
./run.sh os health "check workstation" --subsystem workstation

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
