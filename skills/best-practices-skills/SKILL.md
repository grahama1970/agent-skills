---
name: best-practices-skills
description: >
  Best practices for designing and structuring agent skills: SKILL.md frontmatter rules,
  triggers, progressive disclosure, and when to use scripts vs references.
triggers:
  - best practices skills
  - skill structure
  - skill design
  - skill frontmatter
  - skill template
  - skill checklist
metadata:
  short-description: Skill structure and design patterns
provides:
  - skill-validation
  - skill-scaffolding
  - composition-rules
  - misuse-guard-template
  - project-state-readiness-pattern
composes:
  - task-monitor
  - monitor-misuse
  - memory
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-scillm
  - best-practices-arangodb
  - best-practices-security
taxonomy:
  - validation
  - compliance
  - composition
  - self-improvement
disciplines:
  - engineering-standards
  - developer-tooling
---

# Skills Best Practices

Use this skill when creating or reviewing skills under `.pi/skills/`.


## Runtime self-improvement tier

Declare in frontmatter when a skill is more than a simple one-shot CLI:

```yaml
runtime_self_improvement: none | basic | substantial
```

| Tier | Verify command | Maintainer ticket | Agent post-run section |
|------|----------------|-------------------|------------------------|
| `none` | No | No | No |
| `basic` | `sanity.sh` only | No | Optional |
| `substantial` | `./run.sh verify` + receipt | `file-maintainer-ticket` | Required in `agents/<skill>/AGENTS.md` |

Full contract: `references/runtime-self-improvement.md`

Template files: `references/templates/runtime-self-improvement/`

Validator enforces `substantial` via rules `RSI001`–`RSI004` in `scripts/validate_skill.py`.

Rollout: wire substantial skills incrementally; `voice-segment-selector` is the reference implementation.


## ArangoDB Access Policy (NON-NEGOTIABLE)

- `/memory` is the ONLY skill that accesses ArangoDB directly
- `/ops-arango` handles admin ops (backups, indexes, migrations)
- `monitor-memory` has read-only exception for health probes (documented)
- ALL other skills MUST use `memory/run.sh` subcommands:
  - `memory recall` — semantic + BM25 search
  - `memory learn` — store lessons/data
  - `memory sample` — random document sampling
  - `memory tag` — post-insert tag stamping
  - `memory count` — collection statistics
  - `memory archive-session` — episodic archival
- NEVER: `from arango import ArangoClient`
- NEVER: `sys.path.insert(0, MEMORY_PATH)`
- NEVER: hardcoded passwords or raw `/_api/cursor` calls

## Storage Policy (NON-NEGOTIABLE)

**The root NVMe is for CODE ONLY.** All heavy artifacts MUST live on the 12TB drive
and be symlinked back. This is enforced by `/skills-broadcast` and `/ops-workstation`.

### What MUST be on `/mnt/storage12tb`

| Category | Examples | Storage Path |
|----------|----------|--------------|
| **Model weights** | `.safetensors`, `.gguf`, `.bin`, `.pt` | `/mnt/storage12tb/skills/<skill-name>/models/` |
| **Training logs** | RVC logs, checkpoints, tensorboard | `/mnt/storage12tb/skills/<skill-name>/logs/` |
| **Extracted data** | `extracted_runs/`, PDF extractions | `/mnt/storage12tb/skills/<skill-name>/extracted_runs/` |
| **Generated outputs** | batch results, GRPO outputs | `/mnt/storage12tb/skills/<skill-name>/outputs/` |
| **Datasets** | training data, WAV files, corpora | `/mnt/storage12tb/skills/<skill-name>/data/` |
| **Work dirs** | temp processing, intermediate files | `/mnt/storage12tb/skills/<skill-name>/work/` |
| **Backups** | `.backups/`, snapshots | `/mnt/storage12tb/backups/<project>/` |

### What MUST NEVER be synced by `/skills-broadcast`

These directories are **excluded from rsync** and must not exist as real directories
in skill folders (only as symlinks to `/mnt/storage12tb/`):

`.venv`, `node_modules`, `__pycache__`, `models`, `rvc`, `outputs`, `logs`, `data`,
`pods`, `extracted_runs`, `work`, `weights`, `checkpoints`, `artifacts`, `sessions`,
`papers`, `datasets`, `*.safetensors`, `*.gguf`, `*.bin`, `*.pt`

### How to set up a new heavy artifact directory

```bash
# 1. Create the storage location on 12TB drive
mkdir -p /mnt/storage12tb/skills/<skill-name>/models

# 2. Move existing data (if any)
mv /path/to/skill/models/* /mnt/storage12tb/skills/<skill-name>/models/

# 3. Remove the directory and create symlink
rmdir /path/to/skill/models
ln -s /mnt/storage12tb/skills/<skill-name>/models /path/to/skill/models
```

### Enforcement

- `/skills-broadcast sanity` FAILS if any skill has non-symlinked dirs >100MB
- `/ops-workstation slim` reports storage policy violations
- `.gitignore` in every skill should exclude heavy artifact patterns

## Error Classification Policy (adopt incrementally)

A skill MUST NOT surface a generic, ambiguous failure (`timeout`,
`NEEDS_ATTENTION`, a bare non-zero) when the real cause is knowable. Route the
raw signal through **`/triage-error`** so every layer of the pipeline
(`/ask → /tau → {/surf | /scillm}`, and any skill) resolves to ONE unambiguous
`{code, cause, next_command}` from the shared catalog
(`skills/triage-error/failure_codes.json`).

- **How:** `skills/triage-error/run.sh classify --text "<err>" --layer <l>` (or
  import `triage_error.classify` in Python). It is language-agnostic — non-Python
  skills shell out to `run.sh classify`.
- **Ambiguous signals:** `run.sh triage` mints a deterministic code and can
  compose `/ticket` (drafts by default; `--file` publishes), `/agentic-evals`
  (`--scaffold-eval`), and `/memory` (stores the code). Grow the catalog when a
  minted `*_unclassified_*` code recurs.
- **Rollout is incremental**, like the runtime-self-improvement tier: pipeline
  skills first (`ask`, `surf`, `scillm`), then outward. Reference implementation:
  `skills/triage-error` itself, plus the `webgpt_attachment_bundle_rejected`
  classification wired into `ask` (issue #1531).
- A skill that emits a bare generic failure where a catalog code exists is a
  best-practices violation; add the classification or the catalog entry.

## Required structure

- A skill is a folder with a required `SKILL.md` at the root.
- `SKILL.md` must start with YAML frontmatter (no code fences).
- Frontmatter delimiters must be standalone lines: opening `---` on line 1 and closing `---` on its own line.
- Frontmatter must include `name` and `description`.
- The `description` should contain explicit trigger contexts (what users will say).
- Keep `SKILL.md` concise; move large content into `references/` or `scripts/`.
- Avoid extra docs (CHANGELOG) inside the skill folder.
- README.md is allowed for skills that declare `provides:` (composable primitives with human developer audiences). SKILL.md is for agents; README.md is for humans browsing the directory.

## Composition Frontmatter (Valence Shell)

Skills are like chemical elements — they bind to each other through defined interfaces.
The `provides:` and `composes:` frontmatter fields declare a skill's **valence shell**:
what it offers to others and what it needs from others.

### Required composition fields

```yaml
---
name: my-skill
description: >
  What this skill does and trigger phrases.
triggers:
  - natural language phrase users will say
  - another trigger phrase
provides:
  - capability-a       # What this skill outputs/offers
  - capability-b
composes:
  - memory             # Skills this delegates to (by name)
  - scillm
  - extractor
complies:
  - best-practices-skills
  - best-practices-python
---
```

### Field definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `triggers` | list[str] | **Yes** | Natural-language phrases users will say. Parsed at runtime by `skill-selector` extension for BM25-style matching. Skills without triggers are invisible to implicit routing. |
| `provides` | list[str] | Yes | Capabilities this skill makes available. Used by `/skill-lab` gap detector. |
| `composes` | list[str] | Yes | Skills this skill delegates to via subprocess/import. Empty list `[]` if self-contained. Parsed at runtime by `skill-selector` extension for dependency expansion — when a skill is selected, its `composes` deps are automatically included in context. |
| `complies` | list[str] | Yes | Best-practices or standards this skill must satisfy. This is audit metadata for `/skills-ci` and skill maintainers, not runtime delegation. Every skill must include `best-practices-skills`; add domain packs such as `best-practices-python`, `best-practices-scillm`, or `best-practices-react` when applicable. |
| `taxonomy` | list[str] | Recommended | Federated taxonomy bridge tags for multi-hop discovery via `/memory`. Uses standard vocabulary: `precision`, `resilience`, `fragility`, `corruption`, `loyalty`, `stealth`, plus domain tags. |

### Runtime consumption (skill-selector extension)

The `.pi/extensions/skill-selector.ts` extension reads frontmatter at session start:

- **`triggers`** → Built into an inverted token index. When users type natural language
  (no `/skill-name` ref), the extension scores the prompt against triggers+descriptions
  to select relevant skills. **Skills without triggers are invisible to implicit routing.**
- **`composes`** → Parsed into a dependency map. When a skill is selected (explicitly or
  via trigger match), all its `composes` dependencies are automatically pulled into context.
  This replaced a hardcoded static map (Feb 2026) — the extension now reads live frontmatter.
- **`provides`** → Used by `/skill-lab` for gap detection and capability graph traversal.
  Not yet consumed by skill-selector (future: reverse-index for "I need X capability" queries).
- **`complies`** → Used by `/skills-ci`, `/skill-maintainer`, and review workflows
  to select applicable best-practices checks for this skill. It does not pull
  skills into context and must not be used as a substitute for `composes`.

### Binding affinity rules

1. **Skills MUST declare all skills they delegate to** in `composes:`.
2. **Skills MUST declare what they output** in `provides:`.
3. **Skills MUST declare applicable audit standards** in `complies:`.
4. **Self-contained skills** (no external dependencies) use `composes: []`.
5. **Lab skills** (prompt-lab, gpt-lab, classifier-lab) are **catalysts** — they
   create new skills without being consumed. They `provide: [skill-creation]`.
6. **Composite skills** are molecules — stable combinations of existing skills
   wired together by a thin orchestrator.

### Capability vocabulary (standardized provides values)

| Capability | Skills that provide it |
|------------|----------------------|
| `llm-completion` | scillm, codex |
| `embedding` | embedding |
| `memory-recall` | memory |
| `memory-learn` | memory |
| `web-search` | brave-search, dogpile |
| `pdf-extraction` | extractor, review-pdf |
| `security-scan` | hack, security-scan |
| `skill-creation` | prompt-lab, gpt-lab, classifier-lab |
| `skill-validation` | skills-ci, best-practices-skills |
| `competitive-selection` | battle |
| `hardening` | anvil |
| `docker-isolation` | battle, hack |
| `human-interview` | interview |
| `task-planning` | plan |
| `task-orchestration` | orchestrate |
| `taxonomy-tagging` | taxonomy |
| `progress-tracking` | task-monitor |

New capabilities should be added to `references/capability_vocabulary.yml`.

### Graph Registration (Multi-Hop Discovery)

Skills SHOULD be registered in `/memory` as nodes in the knowledge graph.
This enables multi-hop traversal — when `/skill-lab` needs a capability,
it can traverse `composes` edges to find transitive dependencies, just like
`/memory` traverses `relates_to` edges for knowledge discovery.

```
skill:extractor ──composes──► skill:memory
                 ──composes──► skill:scillm
                 ──provides──► capability:pdf-extraction

skill:learn-datalake ──composes──► skill:extractor
                      ──composes──► skill:review-pdf
                      ──composes──► skill:memory
```

This is analogous to chemical bonding — the graph reveals which elements
naturally form molecules. `/taxonomy` tags provide the bridge keywords
that enable cross-domain discovery (a security skill and an extraction skill
might share `taxonomy:validation` tags).

Registration pattern:
```python
from common.memory_client import learn, MemoryScope

# Register skill as a knowledge node
learn(
    problem=f"What does {skill_name} provide?",
    solution=f"Provides: {', '.join(provides)}. Composes: {', '.join(composes)}",
    scope=MemoryScope.OPERATIONAL,
    tags=["skill_registry", skill_name] + provides,
)
```

### Machine-parseable rules

See `references/rules.yml` for the complete machine-parseable rule set
that `/skills-ci` and `/skill-lab` validate against.
See `references/composition_manifest.yml` for the schema `/skill-lab` uses
when planning new composite skills.
Run `./sanity.sh` in this skill to enforce the strict frontmatter gate across all skills.
Run `scripts/sync_skill_compliance.py --skills-root skills --check` from the
repository root to verify that every skill declares deterministic `complies:`
metadata for skill-maintainer and `/skills-ci`.

## Design patterns

1. **Progressive disclosure**
   - Layer 1: Frontmatter (`name`, `description`) for routing.
   - Layer 2: `SKILL.md` body for the workflow map.
   - Layer 3: `scripts/`, `references/`, `assets/` for details on demand.

2. **Guardrails vs freedom**
   - High-variance tasks: instructions only.
   - Fragile/repetitive tasks: scripts with parameters.
   - Mixed tasks: decision tree in `SKILL.md` + references/scripts.

3. **Single source of truth**
   - Put schemas, long examples, and variants in `references/`.
   - `SKILL.md` should point to references, not duplicate them.

4. **Project state transparency**
   - Every complex or multi-service skill SHOULD expose a state-at-a-glance/readiness report.
   - The report is a hallucination guard: it must say `NOT_TESTED`, `NOT_ESTABLISHED`,
     `NEEDS_ATTENTION`, or `BLOCKED` when evidence is missing.
   - Do not summarize skipped routes as success. Skipped required release checks are
     release blockers; skipped non-required checks are coverage gaps.

## LLM Data Validation (DEAL-KILLING, NON-NEGOTIABLE)

Any skill artifact that touches an LLM — compiled prompts, model/agent
responses, tool-call arguments, receipts derived from model output, or
pipeline-step data produced/consumed around a model call — MUST pass a
Pydantic model (boundary data) or typed dataclass with explicit `validate()`
(internal records) as the FIRST deterministic check, before any use,
persistence, or handoff. This is a deal-killing review requirement (operator
directive 2026-09-06): raw-dict poking or jsonschema-only prose errors on an
LLM seam fails the skill review outright. Steering must come from Pydantic
`errors()` data, not prose. A shared choke point (e.g. a DAG-step shim that
every pipeline step routes through) satisfies the rule for the steps that
route through it. Reference implementation:
`skills/persona-dream/scripts/pydantic_step_gate.py` wired into `dag_step.py`.
Cross-ref: `best-practices-python` rule `correctness-llm-io-typed-validation`.

## Typed Seam Contracts (Multi-Layer Skills, NON-NEGOTIABLE)

Any skill whose workflow crosses a boundary — into another skill, a runtime
(Tau), a transport (Surf), a copied worker script, or a subprocess — MUST
validate every artifact that crosses that boundary with a typed model at the
**producer** side, and the validation MUST be unignorable.

Derived from the 2026-07-31/08-01 /ask incident cluster: seven distinct
outages (agent-skills #1123, #1124, #1134–#1139) were all the same failure
class — layer N emitted something layer N+1 rejects or misreads, nothing
checked the seam, and the drift surfaced hours later as an unrelated symptom
(silent hour-long polls, wrong browser tab closed, unrecoverable seats).

Rules:

1. **One typed model per crossing artifact.** Pydantic models for package
   code; stdlib `@dataclass` with an explicit `validate()` for scripts that
   must stay copy-safe/self-contained. Ad hoc dict poking is not validation.
2. **Producer-side, not consumer-side.** The producer runs the check before
   emitting, so the violation is attributed to the code that drifted, with
   its context intact. Where feasible, run the **consumer's actual
   validator** (e.g. /ask runs installed Tau's `validate_dag_contract` on
   every emitted DAG before any browser opens).
3. **Unignorable: pass, self-heal, or raise.** Exactly three outcomes.
   A violation first gets a deterministic, narrow repair attempt derived
   from a known failure class; a successful repair is re-validated and
   recorded (`SELF_HEALED` + the exact repairs). Anything else raises /
   exits non-zero so the orchestrator fails the step closed. No advisory
   warnings — a drifting agent will ignore them.
4. **Stamp the pass.** A validated artifact carries a
   `seam_validation: {kind, status: PASS}` receipt so downstream readers can
   distinguish "validated" from "never checked".
5. **Cross-field truth checks belong in the model.** `READY` requires the
   artifacts that READY implies; `ok: true` requires `status: PASS`; ids
   must be shaped like the ids the consumer resolves. Field presence alone
   does not catch lying summaries.
6. **Emitted commands must be runnable.** Any artifact containing a command
   for a human or agent to run (recovery packets, `next_command`,
   `rebind_command`) is validated for runnability at emission: argv[0]
   exists and is executable, tool names exist in the installed target skill.
   A rejected command is preserved with its reason, never silently emptied.
7. **Copied code is a seam.** If a skill copies a worker/script into a run
   directory, the executor hash-compares the copy against the source before
   dispatch and refreshes stale copies, recording the swap.
8. **Test fixtures speak the real contract.** When a seam contract lands,
   fixtures that fabricated cross-boundary payloads must be upgraded to the
   production shape — the contract refusing old fixtures is the contract
   working, not a regression.
9. **Pydantic failures steer agents.** Skills and Pi extensions that validate
   agent output MUST pass through Pydantic `errors()` data (`type`, `loc`,
   `ctx`) as the repair signal. Do not require model-authored prose, prose
   status sections, regex text checks, or LLM judgment for the ecosystem to
   course-correct. Closed-world classifications use `Enum`/`Literal` or a
   catalog such as `/triage-error`; ambiguous free-text labels are invalid data.

Reference implementation: `skills/ask/src/ask/seam_models.py` (pydantic,
`enforce()`/`SeamViolation`) plus `HandoffContract`/`RecoveryPacketContract`
dataclasses in `skills/ask/scripts/tau_roundtable_worker.py`, wired at the
compile-return, lifecycle-write, execution-write, handoff-emission, and
recovery-packet seams.

## Project State / Readiness Report Standard

Skills that orchestrate other skills, external services, Docker stacks, or long-running
agent workflows SHOULD provide a machine-readable project state report and a human HTML
view. The goal is to make current project state inspectable at a glance and prevent
agents from hallucinating readiness that was not proven.

### Browser-oracle registry for reviewable skills

Complex, high-risk, UI-facing, security, compliance, orchestration, or subagent
skills SHOULD include a committed browser-oracle registry:

```text
<skill>/.ask/browser-oracles.yaml
```

The registry maps the skill directory to a WebGPT project so `$webgpt-review`,
`$ask webgpt`, and `$surf webgpt.submit` can resolve the correct browser
reviewer through `$browser-oracle` walk-up. The tab id and conversation URL
belong in the browser-oracle binding store, not in prompts or README prose:

```bash
skills/browser-oracle/run.sh bind <skill-project-name> \
  --backend webgpt \
  --tab-id <tab-id> \
  --url '<chatgpt-project-conversation-url>' \
  --manual \
  --json
```

Minimum committed registry shape:

```yaml
version: 1
webgpt:
  default: <skill-project-name>
```

This file is committed configuration, not proof of a successful review.
Readiness still requires actual `$webgpt-review` artifacts and local
deterministic evidence.

### Required report concepts

| Concept | Requirement |
|---------|-------------|
| Overall readiness | One of `READY`, `USABLE_WITH_GAPS`, `NOT_READY`, `NOT_ESTABLISHED` |
| Profile | Explicit profile such as `smoke`, `core-live`, or `release` |
| User attention | Missing config, credentials, review gates, or ambiguous decisions |
| Feature readiness | One row per user-facing feature, not only one row per command |
| Claim coverage | README/SKILL claims mapped to cases and evidence |
| Project knowledge | Skill-specific current-state document maintained by `/project-knowledge` |
| Execution status | Did the command run? |
| Assertion status | Did the expected checks pass? |
| Feature readiness | Is the user-facing feature usable? |
| Coverage gaps | Untested claims and skipped cases, separate from bugs |
| Artifact validation | Existence, schema, and status registration checks |
| Liveness | Event-tail/SSE/progress liveness, not only subprocess timeout |

### Required files

```text
<skill-artifacts>/readiness/<run-id>/
  report.json      # source of truth, schema-versioned
  index.html       # human view over report.json
  report.md        # optional text handoff
```

`index.html` is a view, not the source of truth. Other tools should consume
`report.json`.

### Recommended JSON shape

```json
{
  "schema": "skill.readiness_report.v1",
  "profile": "release",
  "overall_readiness": "not_ready",
  "release_readiness": "not_ready",
  "needs_attention": [
    {
      "reason": "missing_config",
      "safe_default": "do_not_claim_release_ready",
      "resume_hint": "./run.sh config init"
    }
  ],
  "features": [
    {
      "id": "argue",
      "readiness": "partial",
      "required_cases": 2,
      "passed_cases": 1,
      "coverage_gaps": ["No evidence-backed successful verdict case"]
    }
  ],
  "cases": [
    {
      "id": "argue-insufficient-evidence-fail-closed",
      "feature": "argue",
      "case_type": "negative-control",
      "execution_status": "pass",
      "assertion_status": "pass",
      "readiness_contribution": "safe_failure_only"
    }
  ]
}
```

### Profiles

| Profile | Purpose | Release implication |
|---------|---------|---------------------|
| `smoke` | Fast local sanity checks | Never establishes release readiness |
| `core-live` | Main interactive live paths | Can show usable-with-gaps only |
| `release` | Full user-facing readiness | No skipped required checks allowed |
| `feature:<name>` | Focused debug profile | Establishes only that feature |

Reports may run smaller profiles, but the top banner must still state release
readiness honestly. For example: `Release readiness: NOT_ESTABLISHED because
SPARTA and deployment checks were not run`.

### Configuration and human clarification

Complex skills SHOULD include a config layer:

```text
<skill>.config.yml.example   # documented defaults, no secrets
<skill>.config.yml           # local non-secret config, gitignored when appropriate
.env                         # secrets only
```

Required commands:

```bash
./run.sh config doctor --json      # non-interactive, CI-safe
./run.sh config init               # interactive; may call /interview
```

`config doctor` MUST NOT prompt. It returns `needs_attention` with a
`safe_default` and `resume_hint` when config is missing. `config init` MAY use
`/interview` to collect missing values from the human.

### Skill-specific project knowledge

Complex skills SHOULD maintain a skill-specific project knowledge document:

```text
docs/PROJECT_KNOWLEDGE.md
```

This document is the curated current-state projection for the skill: recent
architecture decisions, known gaps, active readiness blockers, companion skill
assumptions, deployment notes, and validation evidence. It prevents agents from
reconstructing project state from stale README text, stale memory snippets, or
optimistic inference.

Required practices:

- Sync it with `/project-knowledge` after durable readiness or architecture changes.
- Treat it as current-state context, not proof. Reports still require cases,
  artifacts, and logs.
- Include it in claim coverage: README/SKILL claims should not contradict
  `docs/PROJECT_KNOWLEDGE.md`.
- If it is missing for a complex skill, readiness reports should mark project
  state as `NOT_ESTABLISHED` or `NEEDS_ATTENTION`.

### Docker and deployment readiness

If a skill claims to be usable by other developers, release readiness SHOULD
include Docker deployment:

- Provide a `docker-compose.yml` or documented compose include.
- Include relevant companion services, not only the skill container.
- Mount host credentials explicitly and report missing credentials as
  `needs_attention`.
- Keep heavy data, model weights, logs, and generated outputs on `/mnt/storage12tb`
  or developer-configured external volumes.
- Prefer health checks and `config doctor` gates over optimistic startup logs.

### Anti-hallucination rules

- Never mark a feature `READY` because its command merely exited zero.
- Never turn a skipped expensive case into a bug unless it was required for the selected profile.
- Never claim compliance, safety, deployment, or release readiness without a case and artifact trail.
- Use retrieval language: `found`, `observed`, `executed`, `not established`.
- Surface missing human decisions as `needs_attention`, not inferred defaults.

## Agentic Evaluation Gate

All skills in `agent-skills` default to an explicit evaluation posture. Every
skill MUST list `agentic-evals` in `composes:` so skill selection, maintenance,
and CI can load the standard gate with the skill. Eval provider skills such as
`agentic-evals` and `eval-skills` are exempt to avoid self-composition.

Use `/agentic-evals` as the default gate when a skill claims durable agent
behavior beyond one-shot CLI output. This includes skills that orchestrate
agents, call multiple downstream skills, manage long-running workflow state,
score or review outputs, make readiness claims, or declare
`runtime_self_improvement: substantial`.

The minimum agentic eval contract is:

- A committed fixture such as `fixtures/agentic_eval.json`.
- At least three trials for non-trivial behavior.
- Positive, negative, and adversarial cases when the behavior has a safety or
  routing boundary.
- Deterministic assertions before optional LLM judges.
- A machine-readable receipt with `mocked`, `live`, `proof_scope`,
  `claims.proves`, and `claims.does_not_prove`.
- A readiness state using `READY`, `USABLE_WITH_GAPS`, `NOT_READY`, or
  `NOT_ESTABLISHED`.

Simple one-shot skills may still document an explicit `eval_not_required`
rationale for fixture depth, but that is not an exemption from composing
`agentic-evals`. Absence of an eval fixture is not an opt-out.

## Checklist (creation/review)

- Frontmatter is valid YAML (no markdown fences).
- Frontmatter has opening and closing `---` on standalone lines.
- `name` matches the directory name.
- `description` contains clear trigger phrases, uses YAML fold syntax (`>`) — **never inline**.
- **`triggers`** list contains natural-language phrases users will say. **Required** — skills without triggers are invisible to implicit routing via skill-selector.
- **`provides`** list declares capabilities this skill outputs. **Required.**
- **`composes`** list declares all skills this delegates to. **Required** (use `[]` if self-contained). Parsed at runtime for automatic dependency inclusion.
- **`complies`** list declares applicable best-practices standards. **Required.** Every skill includes `best-practices-skills`; add domain-specific standards only when they apply. This field is audit metadata, not runtime delegation.
- `run.sh` exists only if the skill needs execution.
- `sanity.sh` exists if the skill runs non-trivial scripts.
- `sanity.sh` for non-trivial skills MUST include behavioral acceptance gates,
  not only import/CLI smoke checks: at least one positive-control fixture, one
  negative-control/noise fixture, safety-boundary assertions for forbidden side
  effects, and concrete artifact/schema assertions for the skill's claimed
  outputs.
- Composite runtime skills that orchestrate three or more live downstream skills
  such as `memory`, `dogpile`, `ask`, `scillm`, or `surf` MUST also provide an
  opt-in live E2E gate (`sanity-live.sh`, `sanity-e2e.sh`, `sanity-webgpt.sh`,
  or `scripts/live_e2e.py`). The live gate must call the real downstream skill
  entrypoints, persist machine-readable proof artifacts, and fail closed when a
  required downstream receipt is missing. A generated request file is not a live
  proof.
- Multi-layer skills validate every boundary-crossing artifact with a typed
  model at the producer (see "Typed Seam Contracts"): pydantic in package
  code, `@dataclass` + `validate()` in copy-safe scripts; violations
  self-heal-with-record or raise — never warn-and-continue; validated
  artifacts carry a `seam_validation` receipt; emitted commands are checked
  runnable before emission.
- Skills that require evals list `agentic-evals` in `composes:` and provide
  `fixtures/agentic_eval.json`; scaffold fixtures are first posture only and
  must be strengthened with real-world positive, negative, and adversarial
  cases.
- Complex, high-risk, UI-facing, security, compliance, orchestration, or
  subagent skills include `.ask/browser-oracles.yaml` so `$browser-oracle`
  can resolve the correct WebGPT review project by directory walk-up.
- **CLI: Typer only** — all Python CLIs use `typer`. NEVER `argparse` or `click`.
- **No bespoke reimplementations** — if a helper skill exists, the new skill delegates to it.
- **PyYAML dependency** — any script that parses SKILL.md frontmatter MUST depend on
  `pyyaml` (not a fallback regex parser). The `>` and `|` YAML block scalars, nested
  objects, and multi-line strings are only reliably parsed by a real YAML parser.


See [PATTERNS.md](references/PATTERNS.md) for anti-patterns, runtime integration patterns, task-monitor, NDJSON streaming, self-correction, quality gates, memory integration, human-in-the-loop, and templates.

## Common Mistakes

### WRONG: Missing triggers in frontmatter (skill is invisible to implicit routing)
```yaml
---
name: my-skill
description: Does something useful
provides: [my-capability]
composes: [memory]
complies: [best-practices-skills]
---
```

### RIGHT: Include natural-language trigger phrases
```yaml
---
name: my-skill
description: Does something useful
triggers:
  - do the useful thing
  - run my-skill
provides: [my-capability]
composes: [memory]
complies: [best-practices-skills]
---
```

### WRONG: Accessing ArangoDB directly from a skill
```python
from arango import ArangoClient
client = ArangoClient(hosts="http://127.0.0.1:8529")
```

### RIGHT: Use /memory subcommands for all data access
```bash
.pi/skills/memory/run.sh recall --q "query" --collections lessons
.pi/skills/memory/run.sh learn --problem "X" --solution "Y"
```

### WRONG: Reimplementing functionality that an existing skill provides
```python
def custom_bm25_search(query, docs):  # /memory already does this
    ...
```

### RIGHT: Delegate to existing skills via composes
```yaml
composes:
  - memory  # use /memory recall for search
```

## Defensive Error Handling (Tiered by Complexity)

**Project agents in 2026 do not thoroughly read SKILL.md files.** Skills that expose HTTP
endpoints or APIs MUST implement server-side misuse detection with helpful error messages.
Documentation alone is insufficient — the API itself must teach correct usage.

### Skill Complexity Tiers

| Tier | Type | Examples | Misuse Handling |
|------|------|----------|-----------------|
| **1** | One-shot script | `/create-icon`, `/png-svg-converter` | None — fail fast, error is obvious |
| **2** | CLI with params | `/extractor`, `/embedding` | Typer handles it; add `--help` examples |
| **3** | Daemon/socket | `/memory`, `/inference` | Basic input validation in handler |
| **4** | HTTP API | `/scillm`, `/fetcher` | **Full misuse detection required** |
| **5** | Multi-agent orchestrator | `/orchestrate`, `/battle` | Full detection + state machine guards |

**Rule: If agents call it programmatically (not via slash command), it needs defensive handling.**

For Tier 4-5 skills, use the reusable template: `references/misuse_guard_template.py`

### Principle: The API is the Documentation

When a caller misuses your API, don't return a generic error. Return an error that:
1. **Explains what went wrong** — specific, not "Bad Request"
2. **Explains why it's a problem** — the consequence of the misuse
3. **Shows how to fix it** — include a code example if possible
4. **References SKILL.md** — for detailed reading (which they won't do, but it's there)

### Required Misuse Detection for HTTP Skills

| Misuse Category | Detection | Response |
|-----------------|-----------|----------|
| **Missing required params** | Presence check | 400 + list required params + example |
| **Wrong param types** | Type check | 400 + expected type + example |
| **Unknown params** | Schema validation | Warning log (don't reject, be tolerant) |
| **Batch overload** | Queue depth/concurrency | 429 + chunk size recommendation |
| **Timeout-prone input** | Size/complexity check | Warning header or 413 + size limits |
| **Provider mismatch** | Feature/provider compatibility | 400 + correct provider/format hint |
| **Service not running** | (client-side preflight) | Document in SKILL.md troubleshooting |

### Example: scillm Misuse Detection (Reference Implementation)

`/scillm` implements comprehensive misuse detection — use it as a template:

```python
# In your validation middleware or endpoint handler:

def validate_request(body: dict, model: str) -> None:
    """Validate request and return helpful errors."""
    
    # 1. Auto-fix common mistakes (tolerant)
    if isinstance(body.get("messages"), str):
        logger.warning("Auto-wrapping string messages as list")
        body["messages"] = [{"role": "user", "content": body["messages"]}]
    
    # 2. Strip problematic params with warning (tolerant)
    if "max_tokens" in body:
        logger.warning(f"Stripping max_tokens — causes empty output")
        del body["max_tokens"]
    
    # 3. Reject incompatible combinations (strict with guidance)
    if has_inline_data(body) and not model.startswith("gemini"):
        raise HTTPException(
            400,
            f"inlineData only works with Gemini. You used model='{model}'. "
            f"For other providers, use image_url format. See SKILL.md."
        )
    
    # 4. Detect resource exhaustion (early warning)
    queue_depth = get_queue_depth(provider)
    if queue_depth > 100:
        raise HTTPException(
            429,
            f"BATCH MISUSE: {queue_depth} requests queued. "
            f"Use chunked processing: process 4 at a time, wait, repeat. "
            f"Example: for chunk in chunks(items, 4): await gather(*chunk)"
        )
```

### Checklist for HTTP/API Skills

- [ ] **Missing/empty required params** → 400 + param name + expected format
- [ ] **Type mismatches** → Auto-fix if safe, else 400 + correct type
- [ ] **Unknown model/endpoint** → 400 + list valid options
- [ ] **Incompatible feature combinations** → 400 + which combos work
- [ ] **Batch/queue overload** → 429 + chunk size + code example
- [ ] **Timeout-prone requests** → Warning header or log
- [ ] **Repeated bad requests** → Temp block (abuse guard) + explain why
- [ ] **Service not running** → Document preflight check in SKILL.md

### Common Mistakes

### WRONG: Generic error that doesn't help the caller
```python
raise HTTPException(400, "Bad Request")
```

### RIGHT: Error that teaches correct usage
```python
raise HTTPException(
    400,
    f"Unknown model '{model}'. Available: text, vlm, local-text. "
    f"Usage: POST /v1/chat/completions with model='text'. "
    f"This is an HTTP API — call via httpx, not import."
)
```

### WRONG: Silently failing on invalid input
```python
if not valid:
    return None  # Caller has no idea what went wrong
```

### RIGHT: Explicit rejection with guidance
```python
if not valid:
    raise HTTPException(
        400,
        f"Invalid format. Expected: {expected_format}. "
        f"Got: {actual_format}. See SKILL.md examples."
    )
```

### WRONG: Letting batch operations timeout silently
```python
# 400 requests fire at once, most timeout after 5 minutes
results = await gather(*[call(x) for x in all_400_items])
```

### RIGHT: Detect and reject batch abuse early
```python
if queue_depth > THRESHOLD:
    raise HTTPException(429, f"Too many queued ({queue_depth}). Use chunking.")
```

### WRONG: Hardcoding all valid values (unmaintainable)
```python
# BAD: This list becomes stale as collections are added/removed
VALID_COLLECTIONS = {"sparta_qra", "lessons_v2", "personas", "checkpoints", ...}

def validate(collection):
    if collection not in VALID_COLLECTIONS:  # ← False negatives for new collections
        raise HTTPException(400, f"Unknown collection")
```

### RIGHT: Map only misuse patterns → corrections
```python
# GOOD: Only catches specific mistakes agents make, never false negatives
COLLECTION_CORRECTIONS = {
    "sparta_qras": "sparta_qra",     # plural → singular
    "sparta_control": "sparta_controls",  # singular → plural (this one IS plural)
    "lesons": "lessons_v2",           # typo
}

def validate(collection):
    if collection in COLLECTION_CORRECTIONS:
        correct = COLLECTION_CORRECTIONS[collection]
        raise HTTPException(400, f"'{collection}' is wrong. Use '{correct}'.")
    # Unknown collections pass through — actual existence checked by db.has_collection()
```

## Misuse Guard Architecture (Template, Not Shared)

**Do NOT create a shared misuse guard module imported across skills.** Skills should be
self-contained and portable. The correct pattern is **copy and adapt** from the template.

### Why NOT a shared import

| Concern | Problem with shared script |
|---------|---------------------------|
| **Coupling** | Skills should be self-contained and portable |
| **Different projects** | Skills may live in separate repos/directories |
| **Import paths** | `sys.path` hacks are fragile across containers/venvs |
| **Skill-specific validators** | Each skill has unique misuse patterns |
| **Versioning** | Change to shared breaks all skills simultaneously |

### Correct pattern: Template + Local Copy

```
~/.pi/skills/best-practices-skills/references/
└── misuse_guard_template.py   ← TEMPLATE (copy and adapt)

Each Tier 4-5 skill that needs it:
├── skill-a/src/.../app/_misuse_guard.py   ← local copy, skill-specific validators
├── skill-b/src/.../proxy/validation.py    ← inline validation (alternative)
└── skill-c/.../_misuse_guard.py           ← local copy, different validators
```

### What the template provides

The template at `references/misuse_guard_template.py` includes:

1. **`MisuseGuard` class** — Copy as-is, configure `skill_name` and thresholds
2. **Common validators** — Pick what applies to your skill:
   - `require_non_empty(field, example)` — Required param validation
   - `auto_wrap_string_as_list(field)` — Tolerant type coercion
   - `reject_incompatible(condition, message)` — Feature combination guards
   - `warn_and_strip(field, reason)` — Strip problematic params
   - `detect_batch_abuse(get_queue_depth, threshold)` — Queue overload detection
   - `correct_value(field, corrections)` — Map misuse patterns → corrections
3. **Abuse detection** — Track repeated bad requests, temp-block abusive clients
4. **Schema validation** — Type checking with helpful error messages
5. **Misuse event logging** — All errors logged to `/memory` for nightly analysis

### Misuse Event Logging (Cross-Skill Learning)

All misuse events are logged to the `misuse_events` collection in `/memory`. The
nightly `/monitor-misuse` job analyzes these events across all skills to:
- Detect new misuse patterns (cluster similar errors)
- Propose corrections (LLM-generated, human-reviewed)
- Track which skills need better docs

**Storage location:** `POST /store` with `collection: "misuse_events"`

**Two implementations depending on context:**

| Context | Implementation | Why |
|---------|---------------|-----|
| **Inside /memory service** | Direct ArangoDB write | No HTTP round-trip, already have db connection |
| **Other skills (template)** | httpx POST `/store` to memory socket | Standard API access |

```python
# Template version (for skills OUTSIDE /memory):
def log_misuse_event(skill, endpoint, error_type, sent_value, correct_value=None):
    import httpx
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=2.0) as client:
        client.post("/store", json={
            "document": {
                "_key": hashlib.sha256(f"{skill}:{endpoint}:{error_type}:{sent_value}".encode()).hexdigest()[:16],
                "skill": skill,
                "endpoint": endpoint,
                "error_type": error_type,
                "sent_value": sent_value,
                "correct_value": correct_value,
                "was_known": correct_value is not None,
                "ts": int(time.time()),
            },
            "collection": "misuse_events",
        })

# /memory version (direct ArangoDB, avoids HTTP):
def _log_misuse_event(endpoint, error_type, sent_value, correct_value=None):
    from ...arango_client import get_db
    db = get_db()
    coll = db.collection("misuse_events")
    # ... direct insert/update
```

**Event schema:**

| Field | Type | Description |
|-------|------|-------------|
| `_key` | str | Hash of skill:endpoint:error_type:sent_value (dedupes) |
| `skill` | str | Skill name (memory, scillm, fetcher) |
| `endpoint` | str | Endpoint path (/store, /v1/chat/completions) |
| `error_type` | str | Category (wrong_collection, missing_param, batch_abuse) |
| `sent_value` | str | What the caller sent |
| `correct_value` | str? | What they should have sent (None if unknown) |
| `was_known` | bool | True if we had a correction pattern |
| `ts` | int | Unix timestamp |
| `count` | int | Occurrence count (incremented on duplicates) |

### How to use in a new skill

```python
# 1. Copy template to your skill
cp ~/.pi/skills/best-practices-skills/references/misuse_guard_template.py \
   ./src/my_skill/_misuse_guard.py

# 2. Import and configure
from ._misuse_guard import MisuseGuard, require_non_empty, reject_incompatible

guard = MisuseGuard(skill_name="my-skill")

# 3. Add skill-specific validators
guard.add_validator("input", require_non_empty("input", "example text"))
guard.add_validator("no_conflicting_flags", reject_incompatible(
    lambda body: body.get("flag_a") and body.get("flag_b"),
    "flag_a and flag_b are mutually exclusive"
))

# 4. Define skill-specific schema
schema = {
    "input": {"required": True, "type": str, "example": "your input here"},
    "format": {"required": False, "type": str, "example": "json"},
}

# 5. Use in endpoint
@app.post("/v1/my-endpoint")
async def endpoint(body: dict):
    body = guard.validate(body, schema=schema)
    # ... rest of handler
```

### When to update the template

When you discover a new misuse pattern in any skill:

1. **Fix it locally** in that skill's `_misuse_guard.py`
2. **Generalize** the validator (make it reusable)
3. **Add to template** in `best-practices-skills/references/misuse_guard_template.py`
4. **Document** the pattern in this SKILL.md

This is the **copy-up pattern** — local innovation, then standardize for future skills.

### Automatic Pattern Discovery via /monitor-misuse

Misuse events are logged to the `misuse_events` collection. The `/monitor-misuse`
skill runs nightly to:

1. **Cluster unknown errors** — group similar misuses across all skills
2. **Propose corrections** — LLM generates fix suggestions
3. **Apply to skill files** — approved corrections update the skill's `_misuse_guard.py`

```
All skills with misuse guards
         │
         │ log_misuse_event()
         ▼
  misuse_events collection
         │
         │ nightly /monitor-misuse analyze
         ▼
  misuse_corrections collection
         │
         │ human review + /monitor-misuse apply
         ▼
  skill/_misuse_guard.py updated
```

**To enable auto-apply for your skill**, register it in `/monitor-misuse/scripts/skill_registry.py`:

```python
SKILL_GUARDS = {
    "memory": SkillMisuseGuard(
        skill_name="memory",
        guard_path=Path("/path/to/skill/_misuse_guard.py"),
        corrections_var="COLLECTION_CORRECTIONS",  # or MODEL_CORRECTIONS, etc.
    ),
}
```

This closes the loop: agents make mistakes → events logged → patterns detected →
corrections proposed → guards updated → future agents get helpful errors.

### Common Mistakes

### WRONG: Sharing a single misuse guard across skills via import
```python
# DON'T DO THIS
import sys
sys.path.insert(0, "/home/user/.pi/skills/shared-utils/")
from shared_misuse_guard import MisuseGuard  # Fragile, not portable
```

### RIGHT: Copy template and adapt locally
```python
# Each skill has its own copy with skill-specific validators
from ._misuse_guard import MisuseGuard, require_non_empty
guard = MisuseGuard(skill_name="this-skill")
```

### WRONG: Creating a pip package just for misuse guard
```python
# Overkill for the current skill ecosystem
from pi_skill_utils import MisuseGuard  # Adds dependency management overhead
```

### RIGHT: Simple template copy (no dependencies)
```bash
# Template is self-contained, just copy it
cp ~/.pi/skills/best-practices-skills/references/misuse_guard_template.py \
   ./my_skill/_misuse_guard.py
```

## Service Usage Audits (Tier 4-5 Infrastructure Skills)

Infrastructure skills that other projects call programmatically (scillm, memory, fetcher, etc.)
SHOULD provide an **`assess` capability** that audits external code for correct usage.

### Why This Matters

1. **Agents don't read SKILL.md** — they skim or skip to code examples
2. **Misuse patterns repeat** — same mistakes across many projects
3. **The service agent is the expert** — knows what breaks and why
4. **Catch errors before runtime** — don't wait for 5-minute timeout

### The Pattern

Each infrastructure skill documents:
- **API contracts** — correct usage patterns
- **Known misuse patterns** — what breaks and why (see Common Mistakes sections)
- **Machine-readable rules** — for automated checking

Then exposes an `assess` command that checks external code against these patterns.

### Implementation: `./run.sh assess <file>`

```bash
# scillm assess — checks LLM API usage
./run.sh assess /path/to/script.py
# Output:
# ✅ HTTP API (not import)
# ✅ Model aliases used (text, vlm)
# ✅ No max_tokens
# ✅ Chunked batching (CHUNK_SIZE=4)
# ⚠️ Missing response_format on JSON call (line 89)
# ⚠️ No preflight check before batch

# memory assess — checks memory API usage
./run.sh assess /path/to/script.py
# Output:
# ✅ Uses Unix socket transport
# ✅ Reads data["items"] (not "results")
# ⚠️ subprocess.run in loop (line 78) — use httpx client
# ⚠️ /store without tags (line 134) — multi-hop won't find it
```

### What to Check (by service)

| Service | Misuse Patterns to Detect |
|---------|--------------------------|
| **scillm** | Import instead of HTTP; fire-all-at-once batching; max_tokens; missing response_format; no preflight |
| **memory** | `data["results"]` instead of `items`; TCP instead of Unix socket; subprocess loops; raw AQL; /learn (deprecated) |
| **fetcher** | Missing timeout; no retry logic; blocking calls in async context |
| **embedding** | Wrong dimension (384 required); batch size too large; missing normalization |

### Checklist for Infrastructure Skills

- [ ] **Document misuse patterns** in Common Mistakes section of SKILL.md
- [ ] **Create `assess` subcommand** in run.sh that greps/parses external code
- [ ] **Return structured output** — JSON with file, line, pattern, severity, fix suggestion
- [ ] **Register with /monitor-misuse** for cross-skill pattern aggregation
- [ ] **Add to CI** — assess changed files that use your service

### Example: Minimal assess implementation

```python
# In run.sh, add: assess) python3 scripts/assess_usage.py "$2" ;;

# scripts/assess_usage.py
import re
import sys
import json
from pathlib import Path

PATTERNS = [
    {
        "name": "fire_all_at_once",
        "pattern": r"asyncio\.gather\(\*\[.*for.*in.*all_",
        "severity": "error",
        "message": "Fires all requests at once — use CHUNK_SIZE batching",
        "fix": "for i in range(0, len(items), CHUNK_SIZE): await gather(*chunk)"
    },
    {
        "name": "missing_response_format",
        "pattern": r'"model":\s*\w+.*"messages".*(?!"response_format")',
        "severity": "warning",
        "message": "JSON expected but response_format not set",
        "fix": 'Add "response_format": {"type": "json_object"}'
    },
]

def assess(file_path: str) -> list[dict]:
    content = Path(file_path).read_text()
    issues = []
    for p in PATTERNS:
        for m in re.finditer(p["pattern"], content, re.MULTILINE | re.DOTALL):
            line = content[:m.start()].count("\n") + 1
            issues.append({
                "file": file_path,
                "line": line,
                "pattern": p["name"],
                "severity": p["severity"],
                "message": p["message"],
                "fix": p["fix"],
            })
    return issues

if __name__ == "__main__":
    issues = assess(sys.argv[1])
    print(json.dumps({"issues": issues, "passed": len(issues) == 0}, indent=2))
```

### Cross-Project Usage

```bash
# CI workflow: assess all files that changed and use scillm
git diff --name-only main | xargs grep -l "localhost:4001\|SCILLM" | while read f; do
    ~/.pi/skills/scillm/run.sh assess "$f"
done

# Agent self-check before running batch
if ! ~/.pi/skills/scillm/run.sh assess scripts/generate_qras.py | jq -e '.passed'; then
    echo "Fix usage issues before running batch"
    exit 1
fi
```

### Reference Implementations

| Skill | Status | Location |
|-------|--------|----------|
| scillm | **Implemented** | `~/.pi/skills/scillm/scripts/assess_usage.py` |
| memory | **Implemented** | `~/.pi/skills/memory/scripts/assess_usage.py` |
| fetcher | Planned | — |
| embedding | Planned | — |
