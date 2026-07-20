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

- "What did we decide about idempotent token refresh under concurrent auth retries?"
- "Ask the reliability architect whether the queue fallback fails closed when Redis quorum is lost."
- "Have the tester and maintainer roundtable the cache invalidation migration risk for cross-region writes."
- "What file, test, or artifact backs the claim that replayed webhook deliveries cannot double-charge customers?"

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
Gemini, Chutes, OpenCode Go, and other configured backends. Human chat can use
provider-family shorthand such as `$ask oc kimi ...` or `$ask chutes-kimi ...`
when the model choice matters.

## Try this first

You do not need to learn flags, install personas, or write a chain file before
using `ask`. Start with the question you actually have:

```text
$ask what did we decide about idempotent token refresh under concurrent auth retries?
$ask ask the reliability architect whether the queue fallback fails closed when Redis quorum is lost
$ask run 3 parallel reviewers on the cache invalidation migration
$ask argue whether replayed webhook delivery handling is safe to ship
$ask cae gap review AC-2 MFA evidence for the production tenant
$ask deep review src/ask/ask.py
$ask oc kimi explain the tradeoff in this patch
$ask chutes-kimi summarize the risk in this plan
$ask comment on the report --dag-file /tmp/report-review.dag.json
$ask is memory healthy?
```

Project agents translate those prompts into the correct CLI route. That is
enough to start.

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

**Review a compliance/cybersecurity evidence gap?**

```bash
./run.sh ask "cae gap review AC-2 MFA evidence for the production tenant" \
  --cae-max-rounds 3
```

This freezes a `/create-evidence-case` result first, then runs Brandon,
Margaret, and Jennifer through bounded CAE prompt-role presets. The judge may
reroute one unresolved missing evidence item per round, then stops with
`NEEDS_VERIFICATION`, `INSUFFICIENT_EVIDENCE`, or `NEEDS_CLARIFICATION`.
In the QRA lifecycle this sits after QRA generation and before human
approval: generated QRA → candidate QRA → CAE gap review → human review →
approve, edit, reject, or defer.

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

If a prompt names a persona that is not in memory, `/ask` treats that as an
error-correction moment, not a chance to invent a role. It should use
`/memory clarify`-style ambiguity handling, pause with `needs_attention`, and
offer a guided `/interview` or `/create-persona` path before rerunning the
persona or roundtable request.

```bash
# One loaded persona
./run.sh ask "Critique this queue failover plan" \
  --oracle \
  --oracle-persona ReliabilityArchitect

# Two voices in sequence
./run.sh ask "Where is this webhook replay design weak?" \
  --oracle \
  --oracle-persona ReliabilityArchitect \
  --oracle-peer EvidenceAuditor \
  --oracle-iterations 2

# A protocolized roundtable
./run.sh ask "Should we ship this cache invalidation migration?" \
  --roundtable \
  --roundtable-personas "ReliabilityArchitect:failure_mode,EvidenceAuditor:evidence_auditor,Maintainer:complexity_minimizer"
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
| Natural DAG orchestration | You want `/ask` to compile a clear natural-language skill workflow into an executable DAG | `./run.sh ask 'Use $memory and $scillm to analyze this, then $create-report a report' --orchestrate` |
| DAG JSON | A project agent can express memory, dogpile, oracle, subagent, and report steps more clearly as a graph | `./run.sh ask "review report" --dag-file /tmp/report-review.dag.json` |
| Deep review | You want a thorough, audit-friendly review with artifacts | `./run.sh ask "deep review this" --deep-review --deep-review-target src/ask/ask.py` |
| Browser oracle (Cursor Browser) | **In Cursor IDE** — self-contained Browser; **viewId** not Chrome tab id | `./run.sh ask cursor-browser "question" --oracle --cursor-browser-project my-project` |
| Cursor Browser project bindings | Persistent viewId per project (`~/.pi/cursor-browser-projects/`) | `./run.sh cursor-browser-project bind my-project --view-id f53e74 --manual` |
| Browser oracle (WebGemini) | **Design** review — Gemini tab in Chrome | `./run.sh ask webgemini "review /tmp/review-bundle.md" --oracle --gemini-tab-id <id>` |
| Browser oracle (WebKimi) | **Prose** / writing — Kimi tab in Chrome | `./run.sh ask webkimi "review /tmp/review-bundle.md" --oracle --kimi-tab-id <id>` |
| Browser oracle (WebPerplexity) | **Research** questions — one-shot Perplexity via `$surf` | `./run.sh ask webperplexity "summarize current state of X" --oracle` |
| Doctor | You want a preflight check on dependencies and runtime | `./run.sh doctor --json` |
| Chains | You want to inspect saved review workflows | `./run.sh chains list --json` |
| Status | You want to see recent runs and memory state | `./run.sh status --runs --json` |
| OS health | You are asking the runtime about itself | `./run.sh os health "is memory healthy?"` |

## DAG JSON E2E

`--orchestrate` is the natural-language front door for the same backend DAG
executor. `/ask` owns skill dependencies and artifacts; `$scillm` owns model
routing, pooling, queues, fallback, and telemetry; `$interview` is reserved for
missing target skills, output artifacts, or acceptance criteria.

Project agents can hand `/ask` a graph JSON file instead of expanding a long
flag list. The live sanity check exercises the real `/ask`, `/memory`, and
`/create-report` runtimes with an ask-owned DAG: two concurrent memory recall
nodes feed a sequential report node. React Flow and migration tooling may still
submit `scillm.exec.graph.v1` compatibility envelopes, but `/ask` normalizes
them at the boundary; natural language and `ask.dag.v1` are the preferred
human/project-agent surfaces.

```bash
./scripts/dag_e2e_sanity.py --output-root /tmp/ask-dag-e2e-proof --ask-id ask-dag-e2e-proof
```

The check verifies the ask request/status/events artifacts, DAG manifest,
per-node artifacts, concurrent layer event, and generated Markdown report.
Add `--include-oracle` when you want the same graph to include two live
one-shot `/scillm` oracle nodes before the final report join. Oracle layers also
write a `dag/layer-*-scillm.subgraph.json` handoff artifact so `$ask` remains
the DAG owner while `$scillm` owns model routing, pooling, queues, fallback, and
telemetry. That subgraph is a diagnostic handoff receipt, not a user-authored
execution surface.


Fail-closed required nodes and optional `allow_failure` probes are documented in
`SKILL.md`. To prove a live required-node failure stops dependents and emits
`dag_layer_failed`:

```bash
./scripts/dag_negative_sanity.py --output-root /tmp/ask-dag-negative-proof --ask-id ask-dag-negative-proof
```

## Browser-backed oracle backends

Embry OS routes browser oracle work by **task type** first, then by **where the browser lives** (Chrome vs Cursor).

### Which backend for which work (team default)

| Work type | Preferred backend | Why |
| --- | --- | --- |
| **Code** — review bundles, architecture, implementation, test manifests, tech-lead adjudication | `$webgpt` | WebGPT/ChatGPT workflows live in the dedicated `$webgpt` skill |
| **Prose** — papers, narratives, voice, clarity, long-form writing critique | `$ask webkimi` | Kimi in Chrome with browser sentinel artifacts |
| **Design** — mockups, UX, visual hierarchy, design review, tokens | `$ask webgemini` | Gemini in Chrome on `gemini.google.com` |
| **Research** — fresh web facts, citations, "what is current", OSINT-style questions | `$ask webperplexity` | One-shot Perplexity (no standing review thread) |
| **Inside Cursor IDE** — ChatGPT in the embedded Browser pane (self-contained, no external Chrome) | `$ask cursor-browser` | Uses **viewId** + cursor-browser-bridge; not Chrome tab ids |

When you are already working in **Cursor** and want ChatGPT without switching to external Chrome, use **`cursor-browser`**. When you need WebGPT/ChatGPT in external Chrome, use **`$webgpt`**, not `$ask`.

Do not use `webperplexity` for multi-round code/design review loops — it does not keep a standing conversation tab.

### Chrome vs Cursor (transport)

Two browser **lanes** exist. Pick the lane that matches where the session is open:

| Lane | Tab id | Transport | When |
| --- | --- | --- | --- |
| **Chrome** (`webgemini`, `webkimi`, `webperplexity`) | Chrome numeric tab id (`surf tab.list`) | surf-cli extension | Signed-in tabs in your normal Chrome |
| **Cursor Browser** (`cursor-browser`) | **`viewId`** (e.g. `f53e74`; `surf cursor-browser.tab.list`) | [cursor-browser-bridge](https://github.com/VectorlyApp/cursor-browser-bridge) | ChatGPT inside Cursor's embedded Browser |

### Chrome browser oracles (external Chrome)

Browser oracles in **external Chrome** route through your authenticated session via `$surf`.
`$ask` owns orchestration and run artifacts for supported browser lanes.
`$surf` owns transport and proof (sentinel injection, clean/raw/meta outputs).
Do not call `$surf` directly for normal review work unless you are debugging
transport.

| Shorthand | `--oracle-backend` | Site / tab | Multi-turn on same tab |
| --- | --- | --- | --- |
| `$ask webgemini` | `webgemini` | `gemini.google.com` | Yes (`--gemini-tab-id`, `--gemini-url`) |
| `$ask webkimi` | `webkimi` | `kimi.com` | Yes (`--kimi-tab-id`, `--kimi-url`) |
| `$ask webperplexity` | `webperplexity` | Perplexity (no standing tab) | No (one-shot research) |
| `$ask cursor-browser` | `cursor-browser` | `chatgpt.com` in Cursor Browser | Yes (`--cursor-browser-project`, `--cursor-browser-view-id`) |

Proof of a real browser-oracle run is the **ask artifact set**
(`.ask_artifacts/runs/<ask_id>/`), not an assistant paraphrase. For Gemini/Kimi,
meta JSON must record `controlled_tab_id == requested_tab_id` and a sentinel in the
final assistant message.


### Cursor Browser oracle (`$ask cursor-browser`)

Shell automation for Cursor's embedded Browser requires **cursor-browser-bridge**
(one-time install + Cursor window reload). Port file: `/tmp/cursor-browser-bridge-port`.

```bash
# List tabs (viewId, title, url)
cd ~/.claude/skills/surf && ./run.sh cursor-browser.tab.list

# Bind a project (recommended)
./run.sh cursor-browser-project bind sparta-cursor --view-id f53e74 \
  --url "https://chatgpt.com/c/..." --manual

# Ask with artifacts
./run.sh ask cursor-browser "what is the capital of Texas" \
  --oracle --oracle-backend cursor-browser \
  --cursor-browser-project sparta-cursor
```

Tab resolution is fail-closed: `--cursor-browser-view-id` → `--cursor-browser-url` →
`--cursor-browser-project` → auto-resolve when exactly one `chatgpt.com` tab exists
in Cursor Browser.

Without the bridge, use `@Browser` in chat for ad-hoc work, or install the bridge for `./run.sh` artifacts.

### Review bundle delivery (required for browser reviewers)

Browser tabs **cannot read your local filesystem**. Listing paths in the prompt
(e.g. "see `/tmp/foo.json` and `/tmp/bar.md`") does **not** deliver evidence.

`$ask` validates evidence **before** calling `$surf` and returns a friendly
project-agent message with `needs_attention` (exit code 2) when the bundle is
unreadable:

> I'm a web-based agent and I can't read local file paths. Please provide a
> concatenated text file.

**Valid formats:**

| Format | When to use | Backends |
| --- | --- | --- |
| **Concatenated text** | One `.md` or `.txt` path in the prompt; `$ask` inlines content under `## Attached files` (max 2 MB) | WebGemini, WebKimi, WebPerplexity, Cursor Browser |

**Rejected (fail closed):**

- Multiple path references without inlined content
- Directory paths ("review everything in `/tmp/bundle/`")
- `MANIFEST.json` that lists other files by path only
- Zip bundles on ask browser lanes; archive attachment delivery belongs to `$webgpt`

**RIGHT — concatenated review bundle:**

```bash
# Build one readable file the browser tab can actually see
cat /tmp/evidence/REVIEW_REQUEST.md /tmp/evidence/gate_output.json   > /tmp/review-bundle.md

./run.sh ask webgemini "Review /tmp/review-bundle.md. Return VERDICT: PASS | NEEDS_CHANGES | BLOCKED." --oracle --gemini-tab-id <id>
```

**WRONG — path-only manifest (browser cannot open these files):**

```bash
./run.sh ask webgemini "Review bundle at /tmp/bundle/REVIEW_REQUEST.md; see also /tmp/bundle/gate_output.json"
```

For WebGPT/ChatGPT review, use `$webgpt`. `$ask webgpt`, `$ask chatgpt`,
`--oracle-backend webgpt`, `--webgpt-*`, and `webgpt-project` fail closed.

### Bounded browser Review Loop

Use this when the human has given an intent and wants the project agent to
execute while a browser-backed reviewer adjudicates the evidence. Start with `/interview` only when
the definition of done is still ambiguous.

```text
intent -> optional /interview -> implementation/evidence bundle
  -> /ask webgemini|webkimi|webperplexity review (concatenated text) or $webgpt review -> local fixes -> repeat
```

The human-facing update should stay short: current state, blocker, proposed
decision, evidence path, what changed since last round, and whether a human
decision is required.

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
- `/surf` (Chrome transport for `webgemini`, `webkimi`, `webperplexity`; Cursor Browser via `cursor-browser.*`)
- `/project-knowledge`
- monitor/ops skills used by OS mode

If a companion skill is missing, some modes fail closed with
`needs_attention`; others continue with an explicit degraded status. Fail
closed means a required dependency is missing and `/ask` refuses to guess.

### Release setup

For release-grade use, create a local non-secret config and validate it before
running live checks:

```bash
./run.sh config init
./run.sh config doctor --profile release --json
```

`config init` may launch `/interview` to collect local paths and credential
policy. `config doctor` never prompts; it returns machine-readable
`needs_attention` when config, credentials, companion skill paths, Docker
storage, or service URLs are missing.

For a one-command Docker release attempt:

```bash
docker compose --profile release up --build
```

The compose stack includes `/ask`, `/memory` infrastructure, `/scillm`,
`utls-proxy`, Redis, ArangoDB, Qdrant, and embedding service wiring. It mounts
host credentials such as `~/.codex`, `~/.claude`, and `~/.gemini` explicitly so
missing auth becomes a release blocker instead of a hallucinated success.
Set `SCILLM_REPO` or `MEMORY_REPO` if those repositories are not siblings of
`agent-skills`.

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
$ask oc kimi explain this design tradeoff
$ask oc-qwen compare these options
$ask chutes kimi summarize this plan
$ask chutes-kimi summarize this plan
$ask what tests prove the cache invalidation behavior?
$ask learn the architecture of this repository
$ask is memory healthy?
```

Full route catalog: [docs/HUMAN_CHAT_EXAMPLES.md](docs/HUMAN_CHAT_EXAMPLES.md).

> **At this point, you know enough to use `ask`.**
>
> The rest of this README is reference material for workflows, contracts,
> configuration, telemetry, development, and troubleshooting. Skim, search, or
> skip until you need it.

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

Rule of thumb: use `failure_mode` when the question is "how does this break,"
`evidence_auditor` when the question is "where is the proof," and
`complexity_minimizer` when the question is "are we overbuilding this."

### Parallel findings, then roundtable debate

```bash
./run.sh ask "Review this cache invalidation design" \
  --parallel-review \
  --roundtable \
  --roundtable-personas "Architect:failure_mode,Tester:evidence_auditor,Maintainer:complexity_minimizer"
```

### CAE gap review

CAE gap review is for compliance/cybersecurity evidence questions, not generic
website or design critique. It composes `/create-evidence-case` with fixed CAE
prompt-role presets:

- `Brandon:cae_policy_evidence`
- `Margaret:cae_technical_enforcement`
- `Jennifer:cae_control_mapping`
- judge: `CAE Gap Judge`

```bash
./run.sh ask "cae gap review AC-2 MFA evidence for the production tenant" \
  --cae-reviewers "Brandon:cae_policy_evidence,Margaret:cae_technical_enforcement,Jennifer:cae_control_mapping" \
  --cae-judge "CAE Gap Judge" \
  --cae-max-rounds 3
```

The claim and retrieved evidence case stay fixed. The adaptive part is narrow:
if the judge says `NEEDS_CLARIFICATION`, `/ask` reroutes exactly one missing
evidence item to the matching reviewer role and asks the judge again. It halts
on a terminal judge decision, repeated missing evidence, invalid judge JSON, or
the max round limit. The output is an analyst workbench result, not approval,
certification, attestation, or an audit opinion.

Within a QRA review system, `/create-evidence-case` is still responsible for
building or loading the QRA, resolved controls, answer, crosswalk chains,
formal-proof/SACM references when present, and cached `evidence_case` metadata.
`/ask --cae-gap-review` reviews that frozen snapshot and writes a separate
review artifact that can inform human promotion, edit, rejection, or deferral.

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

Minimal citation objects carry `source_id`, `source_kind`, `quote_or_summary`,
and `supports`:

```json
{
  "evidence_citations": [
    {
      "source_id": "TARGET_BUNDLE.1",
      "source_kind": "file",
      "quote_or_summary": "Retry fallback returns needs_attention when quorum is unavailable.",
      "supports": "The queue fallback fails closed instead of silently retrying."
    }
  ]
}
```

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

### Provider/model shorthand

For direct scillm oracle calls, put the provider/model family before the
question:

```text
$ask oc kimi explain this design tradeoff
$ask oc-qwen compare these options
$ask chutes kimi summarize this plan
$ask chutes-kimi summarize this plan
```

`oc` and `opencode` query scillm's live OpenCode Go model discovery endpoint,
then select the best supported configured model for the requested family. As of
the current live check, Kimi resolves to `opencode-go/kimi-k2.6` and Qwen
resolves to `opencode-go/qwen3.6-plus`. `chutes` uses scillm configured aliases
such as `text-kimi`.

Successful oracle answers count as answered runs even when memory returns zero
items, and runtime artifacts preserve the resolved `oracle_model_alias` so the
route is auditable.

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
$ask ControlMapper persona about how NIST AC-3 relates to SPARTA countermeasure CM0001
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

Local release config lives in `ask.config.yml`; use
`ask.config.yml.example` as the documented template. Secrets stay in `.env` or
host credential stores, not in `ask.config.yml`.

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

### Live bug-hunting sanity

`sanity.sh` is deterministic regression coverage. It intentionally uses mocked
or controlled paths for speed and repeatability.

Use `sanity-e2e.sh` when you want real-world bug discovery across composed
skills. It calls live `/memory`, `/scillm`, `/subagent-runner`, OS health,
review, argue, deep-review, and missing-persona clarification paths, then
writes `report.json`, `index.html`, and `report.md` with feature readiness,
claim coverage signals, command results, artifacts, liveness, and findings.

```bash
# Preview the planned live checks without calling external services.
./sanity-e2e.sh --plan-only

# Run the release-profile live bug-hunting suite.
ASK_LIVE_SANITY_E2E=1 ./sanity-e2e.sh --profile release

# Include slower/costlier fresh-discovery and SPARTA evidence-case routes.
ASK_LIVE_SANITY_E2E=1 ./sanity-e2e.sh --include-expensive
```

Reports are written under `.ask_artifacts/live-sanity/<run_id>/`.
Failures are not softened: nonzero exits, timeouts, tracebacks, malformed JSON,
missing runtime artifacts, suspiciously shallow answers, non-answer markers,
unexpected `needs_attention`, and missing registered artifacts are reported as
findings. Skipped release-required routes are coverage gaps or blockers, not
success. The suite also checks that prompts such as "have the tester and
maintainer roundtable this risk" do not silently invent missing personas; `/ask`
should clarify and offer persona creation through `/interview` or
`/create-persona`.

### WebClaude sanity eval

`scripts/webclaude_sanity_eval.py` is a focused opt-in eval for the current
WebClaude browser path. It lives in `/ask` so Ask maintainers can test browser
reviewer readiness, but it uses `$browser-oracle` and `$surf` directly because
there is not yet a reusable `surf claude.submit` / `webclaude.submit` wrapper.

The live eval checks:

- `webclaude` browser-oracle binding resolves or verifies.
- Surf sees the expected Claude tab id and URL.
- Claude answers a text sentinel prompt.
- Claude accepts a zip attachment containing one Markdown file and one PNG.
- Claude reports both filenames, the Markdown sentinel, and the exact text
  visible in the PNG.
- A same-tab screenshot and machine-readable `result.json` are written.

```bash
# Preview without touching Claude.
uv run python scripts/webclaude_sanity_eval.py --plan-only

# Run against the configured browser-oracle project.
uv run python scripts/webclaude_sanity_eval.py --allow-live --project webclaude

# Or pin an explicit tab and URL.
uv run python scripts/webclaude_sanity_eval.py --allow-live \
  --tab-id 837359291 \
  --expect-url 'https://claude.ai/chat/3cdf38d5-2c6c-4727-b5b9-eb7fd95f5146'
```

Reports are written under `.ask_artifacts/webclaude-sanity/<run_id>/`.
This eval is live browser evidence, not default regression coverage; failures
are reported as missing readiness proof rather than softened into skips.

## Interop with Companion Skills

`ask` is a routing and verification layer. It composes with companion skills
for durable memory, fresh evidence, model calls, detached sessions, and
development context.

| Companion | What `ask` uses it for |
| --- | --- |
| `/memory` | Durable recall, persona profiles, lessons, scoped context, and clarification when recall is ambiguous |
| `/dogpile` | Fresh external evidence when memory is stale or thin |
| `/extract-entities` | First-pass entity extraction for SPARTA/CWE/NIST routing |
| `/create-evidence-case` | Required grounding step for SPARTA-class questions |
| `/interview` | Clarification and guided persona creation when a prompt names missing personas |
| `/create-persona` | Persona materialization after the user confirms a missing-persona interview |
| `/scillm` | Model calls, advocate/judge DAG execution, peer checks |
| `/subagent-runner` | Detached child sessions for oracle and deep-review runs |
| `/project-knowledge` | Curated current-state projection for development context |

When a required companion route is unavailable, required evidence paths fail
closed with `needs_attention`. Optional paths either continue without that
capability or record an explicit degraded status.

## Current Readiness

As of 2026-05-01, `$ask` is usable for the intended interactive workflows:

- Realistic domain sanity/E2E checks pass with scoped memory, a stored persona,
  and a multi-persona roundtable.
- Deterministic `/ask` protocol coverage includes structured citation
  enforcement across ask, oracle, OS, argue, deep-review, and parallel-review.
- Opt-in live `/scillm` E2E passes for argue metadata/source bundles and
  parallel-review composition with `ASK_LIVE_SCILLM_E2E=1`.
- Live `$ask` E2E passes for OpenCode Go and Chutes model shorthand:
  `$ask oc kimi`, `$ask oc-qwen`, `$ask chutes kimi`, and `$ask chutes-kimi`
  all reach scillm, return oracle answers, preserve alias metadata, and mark
  runtime status as `answered`. As of 2026-05-03, direct scillm oracle calls
  use OpenAI-compatible SSE streaming with explicit request deadlines and emit
  `oracle_scillm_call_started` / `oracle_scillm_stream_progress` /
  `oracle_scillm_call_finished` / `oracle_scillm_call_failed` runtime events
  with requested model, served model, backend, reasoning effort, timeout, and
  accumulated content length.
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
| `sanity-e2e.sh` | Opt-in live bug-hunting sanity checks with HTML report |
| `scripts/live_sanity_report.py` | Real-world composed-path E2E reporter |
| `scripts/webclaude_sanity_eval.py` | Opt-in WebClaude text and zip-upload browser eval |

## Development

Documentation-only changes do not require a build.

For code changes:

```bash
bash sanity.sh
```

For live integration checks that intentionally look for real composed-path
bugs:

```bash
ASK_LIVE_SANITY_E2E=1 ./sanity-e2e.sh
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
