# ask — Ask, Argue and Roundtable

<p align="center">
  <img
    src="docs/assets/ask-banner.png"
    alt="ask skill banner showing an arcade-style oracle console with Ask and Roundtable controls"
    width="100%"
  />
</p>

Agents accumulate a lot of context over time: run logs, stored lessons, persona
profiles, source bundles, evidence cases, review artifacts, and whatever fresh
research happened yesterday. You should not have to remember where any of that
lives, or which backend is best at reasoning over it.

That is what `ask` is for. You write the question in plain language. `/ask`
figures out the rest: whether to pull from durable memory, load a persona, kick
off fresh discovery, hand it to an oracle model, or run a structured review
protocol.

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

**One core principle:** memory recall is context, not evidence. Code and design
claims still need to be grounded in inspected files, diffs, tests, logs, or
artifacts. `/ask` enforces that distinction deliberately.

Under the hood, `/ask` uses whatever model surfaces are configured in your
environment: Codex, OpenAI API, `/scillm` routes, local models, DeepSeek,
Gemini, and other configured backends.

## Quick Start

The basics: just ask.

```bash
# Query what your agent already knows.
./run.sh ask "What do we know about the auth retry bug?"

# Teach it something new.
./run.sh learn "architecture of this repository" --scope project --depth standard
```

Those two commands cover most daily use. Everything below is for when you need
more control.

**Need more reasoning firepower?**

```bash
./run.sh ask "Should we use subagent-runner or direct scillm for focused reviews?" \
  --oracle \
  --oracle-backend subagent-runner \
  --oracle-model gpt-5.5 \
  --oracle-reasoning high
```

**Want adversarial review?**

```bash
# Three reviewers, three angles
./run.sh ask "Review this pull request" \
  --parallel-review \
  --parallel-reviewers 3 \
  --parallel-review-focus correctness,tests,maintainability

# Or run a full two-sided argument with a judge
./run.sh ask "argue whether this retry policy should fail closed" \
  --argue
```

**Need a deep, auditable analysis of a specific file?**

```bash
./run.sh ask "deep review this implementation" \
  --deep-review \
  --deep-review-target src/ask/ask.py
```

**Check if the runtime is healthy:**

```bash
./run.sh os health "is memory healthy?"
```

**Watch a live run in your browser:**

```bash
./run.sh status --run <ask_id> --serve --open
```

That is the surface. For the full option list, environment variables, and
agent-facing contract, see [SKILL.md](SKILL.md).

## Asking through a Persona

`/ask` can route a question through a complex persona stored in `/memory`. A
persona is not just a name tag: it can include profile data, domain expertise,
prior lessons, operating style, and lore. `/ask` recalls the actual persona
profile before answering instead of treating the name as a prompt label.

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

| Mode | Reach for it when… | Example |
| --- | --- | --- |
| Ask | You think the answer is already somewhere in memory | `./run.sh ask "what do we know about X?"` |
| Learn | You want to teach the agent something new and durable | `./run.sh learn "architecture of this repository"` |
| Auto-learn | You want recall first, and a fresh learn pass only if memory comes up empty | `./run.sh ask "question" --auto-learn` |
| Oracle | You want the strongest reasoning model available, not just recall | `./run.sh ask "question" --oracle` |
| Persona | You want a specific stored voice with domain expertise and prior lessons | `./run.sh ask "question" --oracle --oracle-persona Architect` |
| Roundtable | You want personas to deliberate in sequence with defined review roles | `./run.sh ask "topic" --roundtable --roundtable-personas Architect,Tester,Maintainer` |
| Argue | You want a real two-sided argument with a judge | `./run.sh ask "argue whether X" --argue` |
| Parallel review | You want independent reviewers looking at the same thing without influencing each other | `./run.sh ask "review this" --parallel-review --parallel-reviewers 3` |
| Deep review | You want a thorough, audit-friendly review with artifacts | `./run.sh ask "deep review this" --deep-review --deep-review-target src/ask/ask.py` |
| Doctor | You want a preflight check on dependencies and runtime | `./run.sh doctor --json` |
| Chains | You want to inspect saved review workflows | `./run.sh chains list --json` |
| Status | You want to see recent runs and memory state | `./run.sh status --runs --json` |
| OS health | You are asking the runtime about itself | `./run.sh os health "is memory healthy?"` |

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

**Companion skills `/ask` expects to find:**

- `/memory`
- `/dogpile`
- `/extract-entities`
- `/create-evidence-case`
- `/scillm`
- `/subagent-runner`
- `/project-knowledge`
- monitor/ops skills used by OS mode

If a companion skill is missing, some modes fail closed with
`needs_attention`; others continue with an explicit degraded status. Fail
closed means a required dependency is missing and `/ask` refuses to guess.

## Talking to It in Plain English

Project agents translate natural `$ask` prompts into the correct CLI route, so
most of the time you can just say what you mean:

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

Full route catalog: [docs/HUMAN_CHAT_EXAMPLES.md](docs/HUMAN_CHAT_EXAMPLES.md).

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

A roundtable is sequential, not parallel chat. `/ask` builds a shared review
state, gives each persona a protocol role, requires claim-specific reactions,
and runs a moderator synthesis at the end. Use it when the order of critique
matters.

```bash
./run.sh ask "Should we split the API client package?" \
  --roundtable \
  --roundtable-personas "Architect:failure_mode,Tester:evidence_auditor,Maintainer:complexity_minimizer" \
  --roundtable-rounds 2
```

Roundtable participants have two layers: the stored persona is the domain
voice; the protocol role is the bounded review job loaded from
`docs/reviewers/*.md`.

### Parallel findings, then roundtable debate

```bash
./run.sh ask "Review this cache invalidation design" \
  --parallel-review \
  --roundtable \
  --roundtable-personas "Architect:failure_mode,Tester:evidence_auditor,Maintainer:complexity_minimizer"
```

### Adversarial argue

`--argue` is an explicit `/scillm` DAG, not a single self-debate prompt:

```text
FOR advocate /scillm call || AGAINST advocate /scillm call
  ↓
sequential judge /scillm call
  ↓
deterministic verifier
  ↓
argue.md + argue.json + verifier.log
```

Reach for it when you need calibrated judgment on a decision without forcing
fake certainty. The judge can return `FOR`, `AGAINST`, `NO_CLEAR_WINNER`, or
`INSUFFICIENT_EVIDENCE`. If you need a binary answer, add
`--decision-required` and an explicit tie-breaker.

```bash
# Let the judge call it honestly.
./run.sh ask "argue whether this runtime path should retry without source grounding" \
  --argue

# Force a decision with a tie-breaker.
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

Argue, oracle, OS knowledge answers, deep review, and parallel review all use
the `ask.citations.v1` citation contract. Memory citations are valid for
knowledge, persona, and project-context answers. They are not valid for code or
review safety claims; those require target/file/diff/artifact citations.

### Preferred model with a one-shot peer

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

Deep review is for the kind of comprehensive, Web-GPT-style analysis you would
otherwise do by copy-pasting code into a chat window. It wraps the
high-reasoning oracle path with pass-based review prompts, target resolution,
read-only git status checks, and machine-checkable artifacts.

It is intentionally read-only. It produces analysis, verdicts, artifacts,
telemetry, and remediation plans. **It does not patch your code.**

```bash
./run.sh ask "deep review this implementation" \
  --deep-review \
  --deep-review-target src/ask/ask.py \
  --deep-reviewers 5 \
  --deep-review-focus boundaries,fail-closed,tests,auditability
```

Outputs land here:

```text
.ask_artifacts/deep-review/<run_id>/review.md
.ask_artifacts/deep-review/<run_id>/review.json
```

The JSON verifier rejects missing sections, unsafe write evidence, shallow
summaries, invalid verdicts, and safe verdicts that arrived without inspected
evidence.

Saved review workflows live in `docs/chains/*.chain.yaml`. The default
`deep-review` chain is:

```text
target resolution → context bundle → parallel reviewers → moderator synthesis → deterministic verifier
```

## Safety and Evidence

For SPARTA, CWE, NIST, CAPEC, ATT&CK, and space-cybersecurity control
questions, `/ask` first sends the preserved question text through
`/extract-entities` and `/memory` recall. Grounded SPARTA-corpora matches route
to `/create-evidence-case`.

If that required evidence-case route is unavailable or fails, `/ask` pauses
with `needs_attention` and `safe_default=do_not_answer_as_grounded` rather than
falling through to ordinary memory/oracle synthesis. No grounded match
continues normal `/ask` routing.

Full contract: [docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md](docs/ASK_SPARTA_PREFLIGHT_CONTRACT.md).

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
| `--ask-id <id>` | Explicit ask id for artifacts and status lookup |
| `--review-context <fresh\|inherited>` | Child context policy |
| `--inherit-memory <none\|summary\|full>` | Memory inheritance policy |
| `--inherit-skills <none\|selected\|all>` | Skill inheritance policy |
| `--inherit-project-context <no\|summary\|full>` | Project context inheritance policy |
| `--dogpile <auto\|off\|force>` | Freshness policy |
| `--json` | Machine-readable command output |

The full contract, triggers, and exhaustive examples live in [SKILL.md](SKILL.md).

## Domain Examples

Domain-specific prompts work fine, but the README keeps onboarding examples
developer-neutral. Exhaustive domain examples and sanity/E2E fixtures live in
[docs/HUMAN_CHAT_EXAMPLES.md](docs/HUMAN_CHAT_EXAMPLES.md).

```text
$ask what do we know about SPARTA QRA validation?
$ask Brandon persona about how NIST AC-3 relates to SPARTA countermeasure CM0001
```

## Configuration

Most users never touch environment overrides. If you do need to tweak defaults,
these are the knobs you will reach for most often:

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

Full list: [SKILL.md](SKILL.md).

## Artifacts and Telemetry

`ask` writes execution details into `/memory` so timeout and reliability policy
can become data-driven over time.

### What gets written

Standard runtime artifacts:

```text
.ask_artifacts/runs/<ask_id>/<ask_id>.request.json
.ask_artifacts/runs/<ask_id>/<ask_id>.status.json
.ask_artifacts/runs/<ask_id>/<ask_id>.events.jsonl
.ask_artifacts/runs/index.jsonl
```

Argue runs additionally write `argue/source_bundle.json`, `argue/for.json`,
`argue/against.json`, `argue/judge.json`, `argue/argue.json`, and
`argue/verifier.log`.

Parallel-review runs write `parallel_review/source_bundle.json`, per-reviewer
outputs, `judge.json`, `verdict.json`, and `verifier.log`.

When you use `status --run <ask_id> --serve`, the local viewer writes
`index.html`, `ask-viewer.css`, `ask-viewer.js`, and `viewer.json`.

Runtime telemetry surfaces:

- `ask_call_log`
- `ask_subagent_heartbeat`
- compact roundtable and parallel-review summaries
- artifact paths for generated review outputs
- durable lessons whenever a conversation produces reusable knowledge

### DAG observability

`/scillm` DAG modes record per-node correlation:

- `scillm_metadata` sent with every advocate, reviewer, and judge node
- returned `/scillm` call/model/metadata observability where available
- source bundle IDs and source IDs used for grounding/citation checks
- explicit degradation status when source grounding falls back or fails
- chunked source IDs such as `TARGET_BUNDLE.1` for large bundles, so grounding
  and verifier citations address the same material

### What the verifier rejects

The verifier is intentionally strict. It will fail a run for:

- unqualified `FOR`/`AGAINST` or safe review verdicts when source grounding has
  degraded
- missing structured citations on verdict-bearing argue, deep-review, and
  parallel-review outputs
- returned `scillm_metadata` mismatches on core node identity fields
- structured `needs_attention` failures from reviewer, advocate, or judge calls
  before a trustworthy verdict can be produced

### Retention

By default, `/ask` does not store full prompts, full reviewer chatter, full code
diffs, or full repo snippets. Heartbeat snapshots are sparse and stored for
future timeout policy; full chatter is not persisted by default.

### Timeout handling

Timeouts are push-style where the runner supports it. `/subagent-runner` emits
transcript delta and heartbeat events while a Codex session is alive. `/ask`
follows `events.jsonl` first and falls back to status polling only when needed.

- `--oracle-idle-timeout` is silence/stall detection, not a normal long-running
  reasoning failure.
- `--oracle-timeout` remains the wall-clock cap.

### Semantic validation

These cases are part of the E2E contract and must fail the relevant check:

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

- Realistic domain sanity/E2E checks pass with scoped memory, a stored persona,
  and a multi-persona roundtable.
- Deterministic `/ask` protocol coverage includes structured citation
  enforcement across ask, oracle, OS, argue, deep-review, and parallel-review.
- Opt-in live `/scillm` E2E passes for argue metadata/source bundles and
  parallel-review composition with `ASK_LIVE_SCILLM_E2E=1`.
- SPARTA evidence-case routing fails closed when `/create-evidence-case` is
  required but unavailable.
- Runtime status can be inspected in an auto-updating local HTML viewer with
  `./run.sh status --run <ask_id> --serve --open`.
- Normal oracle reasoning defaults to `high`; deep-review defaults to `xhigh`
  when no explicit reasoning is supplied.

Latest evidence dashboard:
`.ask_artifacts/validation-dashboard/20260427T171501Z/index.html`.

## Development Knowledge

Curated development context lives in
[docs/PROJECT_KNOWLEDGE.md](docs/PROJECT_KNOWLEDGE.md).

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

| Symptom | Try this |
| --- | --- |
| Memory answers feel stale | Memory may not have refreshed. Try `/memory recall` directly, or add `--dogpile auto` for a freshness check. |
| Persona answer sounds generic | Confirm the persona profile exists in `/memory`. If it was overwritten, relearn or restore it. |
| Oracle call stalls | Check `ask_subagent_heartbeat` and transcript tail to see where it paused. |
| Pipeline feels opaque | Run `./run.sh status --run <ask_id> --serve --open` to watch it live in your browser. |
| Deep review returns shallow JSON | The verifier should reject it. Inspect `review.json` to see which gate failed. |
| Date-sensitive answer lacks freshness | Use `--dogpile force`, or verify that `--dogpile auto` is routing to discovery. |

## What ask is not

A few boundaries are worth being explicit about:

- **It is not a bulk prompt runner.** If you need to blast through 10,000
  prompts, use a batch pipeline. `ask` is for interactive, high-stakes
  questions.
- **It is not `/code-runner`.** Runtime review modes do not patch source files.
- **It is not a patch robot.** Deep review will tell you what is wrong and how
  to fix it. It will not edit your files. That boundary matters.
- **It is not proof by JSON.** Structured output makes audits easier. It does
  not make the reasoning smarter. Do not let clean JSON create false
  confidence.
- **It is not evidence by memory alone.** Memory recall guides review;
  inspected artifacts ground claims. `/ask` enforces that distinction
  deliberately.
- **It is not ChatGPT Web parity.** Local oracle review uses the Codex and
  `/scillm` surfaces you actually have, not a cloud-only feature set.

Start with `./run.sh ask "..."`, add `--oracle` when you want it to reason
harder, and reach for `--argue`, `--roundtable`, or `--deep-review` when a
single answer is not enough.
