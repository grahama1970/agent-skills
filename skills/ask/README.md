# ask

<p align="center">
  <img
    src="docs/assets/ask-banner.png"
    alt="ask skill banner showing an arcade-style oracle console with Ask and Roundtable controls"
    width="100%"
  />
</p>

> Ask normal questions. Let the system find the right memory, persona, evidence,
> or reviewer.

Agents accumulate useful state in many places: run logs, stored lessons, persona
profiles, source bundles, evidence cases, review artifacts, and fresh research.
Humans should not have to remember where the answer lives or which backend can
reason over it.

`ask` exists to make that routing problem disappear. You write the question in
plain language; `/ask` decides whether to use durable recall, a loaded persona,
fresh discovery, an oracle model, or a bounded review protocol.

Use it for questions like:

- "What did we decide about this?"
- "Which persona should critique this plan?"
- "Is this implementation safe to proceed?"
- "What evidence backs this claim?"

```text
human asks naturally
    ↓
/ask resolves intent
    ↓
/memory provides durable context
    ↓
optional /dogpile discovers fresh external evidence
    ↓
optional oracle or subagent path produces high-reasoning synthesis
    ↓
artifacts and telemetry persist for later recall
```

**Core principle:** Memory recall is context, not evidence. Code and design
claims must still be grounded in inspected files, diffs, tests, logs, or
artifacts.

Under the hood, `/ask` uses whatever model surfaces are available in the current
environment: Codex subscription surfaces, OpenAI API access, `/scillm` routes,
local models, DeepSeek, Gemini, or other configured backends.

## Quick Start

```bash
# Query stored knowledge.
./run.sh ask "What do we know about the auth retry bug?"

# Learn a new project or topic.
./run.sh learn "architecture of this repository" --scope project --depth standard

# Ask for high-reasoning synthesis.
./run.sh ask "Should we use subagent-runner or direct scillm for focused reviews?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high

# Run independent adversarial reviewers.
./run.sh ask "Review this pull request" \
  --parallel-review \
  --parallel-reviewers 3 \
  --parallel-review-focus correctness,tests,maintainability

# Run deep review with audit artifacts.
./run.sh ask "deep review this implementation" \
  --deep-review \
  --deep-review-target src/ask/ask.py

# Check runtime health through OS mode.
./run.sh os health "is memory healthy?"

# Serve an auto-updating read-only monitor for a run.
./run.sh status --run <ask_id> --serve --open
```

### Ask through loaded personas

`ask` can route a question through complex personas stored in `/memory`. A
persona can include profile data, domain expertise, prior lessons, operating
style, and lore. `/ask` recalls the actual persona profile before answering
instead of treating the name as a prompt label.

```bash
# One loaded persona
./run.sh ask "Critique this reliability plan" \
  --oracle \
  --oracle-persona Brandon

# Two voices in sequence
./run.sh ask "Where is this architecture weak?" \
  --oracle \
  --oracle-persona Brandon \
  --oracle-peer Margaret \
  --oracle-iterations 2

# A protocolized roundtable
./run.sh ask "Should we ship this change?" \
  --roundtable \
  --roundtable-personas "Brandon:failure_mode,Margaret:evidence_auditor,Jennifer:complexity_minimizer"
```

## When to Use Each Mode

| Mode | Use when you need | Example |
| --- | --- | --- |
| Ask | Stored project or topic knowledge | `./run.sh ask "what do we know about X?"` |
| Learn | New durable knowledge | `./run.sh learn "architecture of this repository"` |
| Auto-learn | Recall first, learn only if memory is weak | `./run.sh ask "question" --auto-learn` |
| Oracle | Highest-available reasoning synthesis | `./run.sh ask "question" --oracle` |
| Persona | A loaded profile with domain expertise, lessons, and voice | `./run.sh ask "question" --oracle --oracle-persona Architect` |
| Roundtable | Sequential persona deliberation | `./run.sh ask "topic" --roundtable --roundtable-personas Architect,Tester,Maintainer` |
| Argue | Two parallel advocates plus sequential judge | `./run.sh ask "argue whether X" --argue` |
| Parallel review | Independent reviewer fanout | `./run.sh ask "review this" --parallel-review --parallel-reviewers 3` |
| Deep review | Web-GPT-style review with artifacts | `./run.sh ask "deep review this" --deep-review --deep-review-target src/ask/ask.py` |
| Doctor | Dependency and runtime preflight | `./run.sh doctor --json` |
| Chains | Inspect saved review workflows | `./run.sh chains list --json` |
| Status | Inspect recent runs and memory state | `./run.sh status --runs --json` |
| OS health | Ask runtime/ops questions | `./run.sh os health "is memory healthy?"` |

## Installation

`ask` is normally installed through an agent skills tree:

```bash
cd /path/to/workspace
ls .pi/skills/ask
```

For direct development from the skills repository:

```bash
cd /path/to/agent-skills/skills/ask
./run.sh ask "is memory healthy?"
```

Expected companion skills:

- `/memory`
- `/dogpile`
- `/extract-entities`
- `/create-evidence-case`
- `/scillm`
- `/subagent-runner`
- `/project-knowledge`
- monitor/ops skills used by OS mode

## Common Human Chat Prompts

Project agents translate natural `$ask` prompts into the correct CLI route.

```text
$ask what do we know about the auth retry bug?
$ask what changed in the API client architecture?
$ask what are the risks in this implementation?
$ask run 3 parallel adversarial reviewers on this pull request
$ask argue whether this retry policy should fail closed
$ask review then roundtable with Architect, Tester, and Maintainer
$ask deep review this implementation --deep-review-target src/ask/ask.py
$ask oracle should we use subagent-runner here?
$ask what tests prove the cache invalidation behavior?
$ask learn the architecture of this repository
$ask is memory healthy?
```

See `docs/HUMAN_CHAT_EXAMPLES.md` for the complete human-facing route catalog.

## Workflows

### Memory-backed question

```bash
./run.sh ask "What tests prove the cache invalidation behavior?" \
  --bridges
```

### Persona oracle

```bash
./run.sh ask "Critique this reliability plan" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-persona Architect
```

### Sequential roundtable

Roundtable is sequential, not parallel chat. `/ask` builds a shared review
state, gives each persona a protocol role, requires claim-specific reactions,
then runs a moderator synthesis. Use it when the order of critique matters.

```bash
./run.sh ask "Should we split the API client package?" \
  --roundtable \
  --roundtable-personas "Architect:failure_mode,Tester:evidence_auditor,Maintainer:complexity_minimizer" \
  --roundtable-rounds 2
```

Roundtable participants have two separate layers: the stored persona is the
domain voice, while the protocol role is the bounded review job loaded from
`docs/reviewers/*.md`.

### Parallel findings then roundtable debate

```bash
./run.sh ask "Review this cache invalidation design" \
  --parallel-review \
  --roundtable \
  --roundtable-personas "Architect:failure_mode,Tester:evidence_auditor,Maintainer:complexity_minimizer"
```

### Adversarial argue

Argue is an explicit `/scillm` DAG, not a single self-debate prompt:

```text
FOR advocate /scillm call || AGAINST advocate /scillm call
  ↓
sequential judge /scillm call
  ↓
deterministic verifier
  ↓
argue.md + argue.json + verifier.log
```

Use it when the user wants calibrated judgment on a decision without forcing
fake certainty. The judge may return `FOR`, `AGAINST`, `NO_CLEAR_WINNER`, or
`INSUFFICIENT_EVIDENCE`; binary forced decisions require
`--decision-required` plus an explicit tie-breaker.

```bash
./run.sh ask "argue whether this runtime path should retry without source grounding" \
  --argue

./run.sh ask "argue whether to ship this fallback today" \
  --argue \
  --decision-required \
  --tie-breaker fail-closed
```

Every argue node carries opaque `scillm_metadata` for correlation and a
serialized source bundle for grounding. If `/scillm` source grounding fails or
times out, `/ask` retries without `source`, records the degradation in node
artifacts, and still lets the deterministic verifier decide whether the result
is trustworthy.

Argue, oracle, OS knowledge answers, deep review, and parallel review use the
`ask.citations.v1` citation contract. Memory citations are valid for knowledge,
persona, and project-context answers. They are not valid for code/review safety
claims; safe review verdicts require target/file/diff/artifact citations.

### Preferred model with a one-shot peer model

```bash
./run.sh ask "What is the strongest objection to this plan?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-persona "GPT-5.5 architect" \
  --oracle-peer "DeepSeek V4 critic" \
  --oracle-peer-model opencode-go/deepseek-v4-pro \
  --oracle-iterations 3
```

## Deep Review

Deep review is a read-only oracle/review lane for comprehensive analysis without
browser copy-paste. It wraps the high-reasoning oracle path with:

- pass-based review prompts
- target resolution
- read-only git status checks
- deterministic artifact generation
- machine-checkable JSON verification

Deep review should produce analysis, verdicts, artifacts, telemetry, and
remediation plans. It should not patch source files.

```bash
./run.sh ask "deep review this implementation" \
  --deep-review \
  --deep-review-target src/ask/ask.py \
  --deep-reviewers 5 \
  --deep-review-focus boundaries,fail-closed,tests,auditability
```

Outputs:

```text
.ask_artifacts/deep-review/<run_id>/review.md
.ask_artifacts/deep-review/<run_id>/review.json
```

The JSON verifier rejects:

- missing required sections
- unsafe write evidence
- shallow summaries
- invalid verdicts
- safe verdicts without inspected evidence

Saved review workflows live in `docs/chains/*.chain.yaml`.

The default `deep-review` chain is:

```text
target resolution
  → context bundle
  → parallel reviewers
  → moderator synthesis
  → deterministic verifier
```

## Safety and Evidence

For SPARTA, CWE, NIST, CAPEC, ATT&CK, and space-cybersecurity control
questions, `/ask` first sends the preserved question text through
`/extract-entities` and `/memory` recall.

Grounded SPARTA-corpora matches route to `/create-evidence-case`. If that
required evidence-case route is unavailable or fails, `/ask` pauses with
`needs_attention` and `safe_default=do_not_answer_as_grounded` instead of
falling through to ordinary memory/oracle synthesis.

No grounded match continues normal `/ask` routing. See
`docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md`.

## Command Reference

```bash
./run.sh ask <question> [options]
./run.sh learn <topic> [options]
./run.sh doctor [options]
./run.sh chains <list|show|validate> [options]
./run.sh status [options]
./run.sh nightly [options]
./run.sh os <learn|ask|health> [options]
```

Common `ask` options:

| Option | Meaning |
| --- | --- |
| `--scope <scope>` | Memory scope to query |
| `--bridges` | Traverse bridge/taxonomy context |
| `--auto-learn` | Learn if memory has no useful result |
| `--oracle` | Use oracle synthesis |
| `--oracle-persona <name>` | Primary stored persona or role |
| `--argue` | Run two parallel advocates, a sequential judge, and a verifier |
| `--decision-required` | Force `--argue` to choose `FOR` or `AGAINST` |
| `--tie-breaker <policy>` | Tie-breaker for forced argue decisions |
| `--roundtable` | Run protocolized sequential deliberation |
| `--parallel-review` | Run independent reviewer fanout |
| `--review-target <target>` | Explicit target for parallel-review evidence bundles |
| `--deep-review` | Emit deep-review markdown and JSON artifacts |
| `--deep-review-target <target>` | Explicit target: paths, diff, plan, manifest, or artifact |
| `--run-id <id>` | Explicit run id for artifacts and status lookup |
| `--review-context <fresh|fork>` | Child context policy |
| `--inherit-memory <yes|no|summary>` | Memory inheritance policy |
| `--inherit-skills <yes|no|selected>` | Skill inheritance policy |
| `--inherit-project-context <yes|no>` | Project context inheritance policy |
| `--dogpile <auto|off|force>` | Freshness policy |
| `--json` | Machine-readable command output |

See `SKILL.md` for the full option list and agent-facing contract.

## Domain Examples

Domain-specific prompts are supported, but the README keeps onboarding examples
developer-neutral. Put exhaustive domain examples in `docs/HUMAN_CHAT_EXAMPLES.md`
and sanity/E2E fixtures.

```text
$ask what do we know about SPARTA QRA validation?
$ask Brandon persona about how NIST AC-3 relates to SPARTA countermeasure CM0001
```

## Configuration

Most users do not need environment overrides. Common variables:

| Variable | Purpose |
| --- | --- |
| `ASK_DEFAULT_SCOPE` | Default memory scope |
| `ASK_ORACLE_MODEL` | Preferred oracle model |
| `ASK_ORACLE_REASONING` | Preferred oracle reasoning effort; default is `high` |
| `ASK_ORACLE_BACKEND` | Default oracle backend |
| `ASK_ORACLE_TIMEOUT` | Oracle call timeout |
| `ASK_ORACLE_IDLE_TIMEOUT` | Subagent silence timeout |
| `SCILLM_BASE_URL` | `/scillm` service URL |
| `SCILLM_API_KEY` | `/scillm` bearer token |
| `ASK_DEBUG` | Enable debug logging |

See `SKILL.md` for exhaustive environment and runtime details.

## Artifacts and Telemetry

`ask` records execution details into `/memory` so timeout and reliability policy
can become data-driven over time.

### Runtime surfaces

Expected telemetry surfaces:

- `ask_call_log`
- `ask_subagent_heartbeat`
- compact roundtable and parallel-review summaries
- artifact paths for generated review outputs
- `.ask_artifacts/<mode>/<run_id>/request.json`
- `.ask_artifacts/<mode>/<run_id>/status.json`
- `.ask_artifacts/<mode>/<run_id>/events.jsonl`
- durable lessons when a conversation produces reusable knowledge
- `argue/source_bundle.json`, `argue/for.json`, `argue/against.json`,
  `argue/judge.json`, `argue/argue.json`, `argue/verifier.log`
- `parallel_review/source_bundle.json`, reviewer outputs, `judge.json`,
  `verdict.json`, and `verifier.log`
- `index.html`, `ask-viewer.css`, `ask-viewer.js`, and `viewer.json` when
  `status --run <ask_id> --serve` is used

### DAG observability

`/scillm` DAG modes record per-node runtime correlation:

- `scillm_metadata` sent with every advocate, reviewer, and judge node
- returned `/scillm` call/model/metadata observability when provided
- source bundle IDs and source IDs used for grounding/citation checks
- explicit degradation status when source grounding falls back or fails
- verifier failures for unqualified `FOR`/`AGAINST` or safe review verdicts
  when source grounding degrades
- verifier failures for missing structured citations on verdict-bearing argue,
  deep-review, and parallel-review outputs
- chunked source IDs such as `TARGET_BUNDLE.1` for large target bundles so
  `/scillm` grounding and verifier citations address the same material
- verifier failures for returned `scillm_metadata` mismatches on core node
  identity fields
- structured `needs_attention` diagnostics when reviewer, advocate, or judge
  calls fail before a trustworthy verdict can be produced

### Retention

Do not store full prompts, full reviewer chatter, full code diffs, or full repo
snippets by default.

Timeout handling is push-style where the runner supports it:

- `/subagent-runner` emits transcript delta and heartbeat events while a Codex
  session is alive.
- `/ask` follows `events.jsonl` first and falls back to status polling only when
  needed.
- `--oracle-idle-timeout` is treated as silence/stall detection, not normal
  long-running reasoning failure.
- `--oracle-timeout` remains the wall-clock cap.
- Heartbeat snapshots are sparse and stored for future timeout policy; full
  chatter is not persisted by default.

Semantic validation is part of the E2E contract. These cases must fail the
relevant E2E check:

- empty answers
- `No answer could be synthesized`
- refusal-style non-answers
- wrong persona routing
- missing roundtable participants
- missing domain grounding

Mocked tests are regression coverage, not integration proof. New user-visible
composition paths through `/scillm` require an opt-in live smoke/E2E check
before being described as validated.

## Current Readiness

As of 2026-04-29, `$ask` is usable for the intended interactive workflows:

- Realistic domain sanity/E2E checks passed `3/3` with scoped memory, a stored
  persona, and a multi-persona roundtable.
- Targeted regression suite passed `30/30`.
- Deterministic `/ask` protocol suite passed `98/98` after adding argue and
  parallel-review `/scillm` metadata/source payloads.
- Deterministic `/ask` protocol suite passed `102/102` after adding verifier
  gates for source-grounding degradation and returned metadata mismatches.
- Deterministic `/ask` suite passed `134/134` after promoting runtime parity
  and adding full structured citation enforcement across ask, oracle, OS,
  argue, deep-review, and parallel-review surfaces.
- Opt-in live `/scillm` E2E passed for argue metadata/source bundles and
  parallel-review composition with `ASK_LIVE_SCILLM_E2E=1`.
- SPARTA evidence-case routing now fails closed when `/create-evidence-case` is
  required but unavailable, returning `needs_attention` rather than a normal
  answer.
- Runtime status can be inspected in an auto-updating local HTML viewer with
  `./run.sh status --run <ask_id> --serve --open`.
- Latest targeted validation after the fail-closed/viewer update: `105 passed`,
  `sanity.sh` passed, and CDP verified the HTML viewer.
- Normal oracle reasoning defaults to `high`; deep-review defaults to `xhigh`
  when no explicit reasoning is supplied.
- The latest evidence dashboard is generated at
  `.ask_artifacts/validation-dashboard/20260427T171501Z/index.html`.

## Development Knowledge

Curated development context lives in `docs/PROJECT_KNOWLEDGE.md`.

```bash
cd /path/to/skills/ask
PROJECT_KNOWLEDGE_CWD=docs ../project-knowledge/run.sh sync
../project-knowledge/run.sh recall --project ask
```

Agents should still query `/memory` first. Project knowledge is a curated
current-state projection, not a replacement for inspected code or test output.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `SKILL.md` | Full skill contract, triggers, commands, and examples |
| `README.md` | Developer/GitHub overview |
| `run.sh` | CLI entrypoint |
| `src/ask/ask.py` | Main command implementation |
| `src/ask/deep_review.py` | Deep-review prompt, artifact, and verifier support |
| `src/ask/ask_routing.py` | Natural prompt routing |
| `src/ask/ask_oracle.py` | Oracle/subagent synthesis path |
| `src/ask/ask_results.py` | Result formatting and persistence support |
| `src/ask/run_state.py` | Run ids, artifact directories, events, status, context policy |
| `src/ask/run_viewer.py` | Token-gated local HTML viewer for runtime artifacts |
| `src/ask/doctor.py` | Preflight diagnostics for composed dependencies |
| `src/ask/reviewer_specs.py` | Reviewer-role frontmatter loading and dynamic angle selection |
| `src/ask/chain_specs.py` | Saved review-chain loading and validation |
| `src/ask/review_protocols/` | Roundtable and adversarial review protocols |
| `docs/reviewers/` | Protocol role specs with YAML frontmatter |
| `docs/chains/` | Saved deep-review and parallel-review workflow specs |
| `docs/plans/` | Historical and active implementation/orchestration plans |
| `docs/HUMAN_CHAT_EXAMPLES.md` | Human prompt examples and route expectations |
| `docs/PROJECT_KNOWLEDGE.md` | Curated current development state |
| `sanity.sh` | Deterministic smoke checks |

## Development

Documentation-only changes do not require a build.

For code changes:

```bash
bash sanity.sh
```

When tests are added or modified:

```bash
uv run --project . --group dev python -m pytest -q tests/test_human_chat_examples.py
uv run --project . --group dev python -m pytest -q tests/test_ask_cli_protocols.py
uv run --project . --group dev python -m pytest -q tests/test_deep_review_protocol.py
bash sanity.sh
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Memory answers look stale | Run `/memory recall` directly and consider `--dogpile auto` |
| Persona answer sounds generic | Confirm persona profile exists in `/memory` |
| Oracle call stalls | Check `ask_subagent_heartbeat` and transcript tail |
| Pipeline feels opaque | Run `./run.sh status --run <ask_id> --serve --open` |
| Deep review returns shallow JSON | Verifier should reject it; inspect `review.json` |
| Date-sensitive answer lacks freshness | Use `--dogpile force` or verify `--dogpile auto` routing |

## Non-goals

- **Not a batch LLM runner.** Use batch-capable lanes for high-volume prompts.
- **Not `/code-runner`.** Runtime review modes should not patch source files.
- **Not a patch generator.** Deep review produces analysis, verdicts, and remediation plans.
- **Not proof by JSON.** Structured output improves auditability, not reasoning depth.
- **Not evidence by memory alone.** Memory recall guides review; inspected artifacts ground claims.
- **Not exact ChatGPT Web parity.** Local oracle review uses available Codex/scillm surfaces.
