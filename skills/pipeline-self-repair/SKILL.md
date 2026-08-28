---
name: pipeline-self-repair
description: >
  Executable self-repair control plane for complex sequential pipelines that are
  expected to fail. Use when a skill pipeline such as persona-dream,
  monitor-opportunities, watchdog jobs, provider media generation, scheduler
  sweeps, or multi-step agentic workflows needs failure-to-repair behavior:
  replayable ledger, triage-error classification, memory/GitHub issue search,
  ticket upsert, project-watchdog handoff, agentic-evals regression coverage,
  checkpoint resume, and fail-closed closure.
triggers:
  - pipeline self repair
  - self repair a pipeline failure
  - replayable repair ledger
  - triage a failed pipeline step
  - create ticket from pipeline failure
  - watchdog repair pipeline failure
  - prevent pipeline retry loops
provides:
  - pipeline-self-repair
  - repair-ledger
  - failure-category-routing
  - checkpoint-resume-gate
composes:
  - memory
  - triage-error
  - ticket
  - project-watchdog
  - agentic-evals
  - phart-dag-chart
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-delivery-proof
runtime_self_improvement: substantial
taxonomy:
  - resilience
  - fragility
  - precision
---

# Pipeline Self Repair

This is an executable skill, not a prose checklist. It turns a required pipeline
step failure into a replayable repair branch.

Use it from complex sequential skills such as `persona-dream` and
`monitor-opportunities`, where failures are expected and must not become status
reports, blind retries, or duplicate GitHub issues.

## Rule

A required step failure must not advance to the next step. It must run this
branch:

```text
STEP_FAILED
-> append replay ledger event
-> classify raw signal with triage-error
-> compute stable category_key / failure_category_id
-> recall memory for prior fixes and graph-neighbor clues
-> search GitHub issues, including open, closed, blocked, and depends-on tickets
-> bind/update/reopen/create one category ticket
-> route eligible repair through project-watchdog
-> require retained agentic-evals coverage for the repair
-> resume only after category-green and required full-suite/checkpoint proof
```

## Why this exists

Complex pipelines fail by design: providers change, browser tabs stale, source
feeds drift, schedulers run stale revisions, and generated media misses visual
requirements. A bare failure message tells the next agent nothing. This skill
records the failure as data, searches prior memory and issue history, deduplicates
repair work, and blocks unsafe forward progress until proof exists.

## Commands

Run from the repo root or the skill directory.

### Record one failed step and start the repair branch

```bash
skills/pipeline-self-repair/run.sh record-failure \
  --pipeline persona-dream \
  --step-id phase_11_kling_submit \
  --run-id <pipeline-run-id> \
  --receipt <failed-step-receipt.json> \
  --layer kling \
  --target skills/persona-dream \
  --run-root <run-root> \
  --ledger <run-root>/replay_ledger.jsonl \
  --repo grahama1970/agent-skills \
  --json
```

Default behavior is safe: it writes the ledger and drafts ticket commands, but
it does not publish a GitHub issue or run watchdog. Add explicit flags when the
pipeline is allowed to mutate external systems:

```bash
  --apply-ticket          # create a category ticket when no prior issue exists
  --dispatch-watchdog     # run one bounded project-watchdog tick after ticketing
```

For paid providers such as Kling, pass effect evidence whenever it exists:

```bash
  --request-body request.json \
  --provider-task-id <task-id> \
  --provider-response provider_response.json \
  --media-url https://... \
  --local-artifact output.mp4 \
  --spend-state unknown
```

`spend-state=unknown` blocks resubmission. The next legal action is reconcile or
poll, not another paid submit.

### Inspect a ledger

```bash
skills/pipeline-self-repair/run.sh inspect \
  --ledger <run-root>/replay_ledger.jsonl \
  --json
```

### Validate a ledger before closure or checkpoint resume

```bash
skills/pipeline-self-repair/run.sh validate-ledger \
  --ledger <run-root>/replay_ledger.jsonl \
  --require-agentic-eval \
  --json
```

This fails if any blocking failure lacks triage, category, ticket disposition, or
retained eval proof.

### Run the agentic-evals remediation projection for a complete eval report

```bash
skills/pipeline-self-repair/run.sh agentic-eval-remediate \
  --report <agentic_evals.report.v2.json> \
  --category-map <skill>/fixtures/category_map.json \
  --fixture <skill>/fixtures/agentic_eval.json \
  --ledger <run-root>/replay_ledger.jsonl \
  --repo grahama1970/agent-skills \
  --json
```

Add `--execute` only when ticket publication is authorized.

## Ledger model

The ledger is append-only JSONL. Each event carries a hash of the previous event
so missing or edited events are visible.

Important fields:

```json
{
  "schema": "pipeline_self_repair.event.v1",
  "event_type": "step.failed",
  "pipeline": "persona-dream",
  "run_id": "...",
  "step_id": "phase_11_kling_submit",
  "triage": {"code": "...", "cause": "...", "next_command": "..."},
  "category_key": "persona-dream/phase-11-kling-submit/<triage-code>/skills-persona-dream/v1",
  "failure_category_id": "agentic-evals:agent-skills:persona-dream-phase-11-kling-submit-...",
  "memory_recall": {"status": "PASS|SKIPPED|FAILED", "found": true},
  "github_issue_search": {"status": "PASS|SKIPPED|FAILED", "matches": []},
  "ticket": {"action": "bind_existing|create_draft|created|needs_reopen|blocked_by_upstream"},
  "repair_state": "TICKETED|NEEDS_TRIAGE|NEEDS_HUMAN|WATCHDOG_DISPATCHED",
  "blocking": true
}
```

## Ticket rules

- One ticket per stable `category_key`.
- Search GitHub before creating anything.
- Search open and closed issues.
- Inspect `blocked-by:` / `depends-on` links before creating a duplicate.
- If an old blocked ticket exists and its upstream is now closed, unblock/reopen
  that ticket instead of filing a new one.
- If a closed ticket lacks proof, treat recurrence as false closure.
- If the same category recurs after proof, reopen the category and require a
  stronger `agentic-evals` regression.

## Agentic-evals rule

Every repair must leave retained eval coverage. A patch, reviewer PASS,
watchdog PASS, or GitHub close is not enough.

Required repair evidence:

```text
triage_code
category_key
GitHub ticket ref or explicit human/provider blocker
retained agentic-evals case or regression mapping
category-green proof
full-suite or checkpoint replay proof when the failure affects pipeline closure
```

## External-effect rule

For provider, publication, outbound message, or paid-call failures, record the
intent and effect state before any retry.

Kling-specific hard gate for `persona-dream`:

```text
request body hash
task id if any
provider response body/hash
spend/effect state
media URLs and expiry when known
local artifact hashes
next legal command
```

If task status is unknown, reconcile or poll first. Do not resubmit until an
explicit new authorization event exists.

## Shared versus pipeline-specific

Shared by this skill:

- event envelope and hash chain
- triage interface
- category key convention
- memory and GitHub search events
- ticket upsert/disposition rules
- watchdog handoff rules
- agentic-evals remediation projection
- ledger validation before closure

Owned by each pipeline:

- step ids and invariants
- checkpoint snapshot format
- provider/publication capsules
- hard versus soft gates
- pipeline-specific category maps
- final closure proof

## Validation

```bash
skills/pipeline-self-repair/sanity.sh
```

The sanity gate runs Python tests and a real dry-run `record-failure` command
that writes and inspects a replay ledger.
