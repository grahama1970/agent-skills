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
  - goal-drift
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

Failure is the normal path for complex agentic pipelines, not an exceptional
edge case. A multi-step pipeline with agents, providers, browsers, memory,
schedulers, and generated artifacts should be assumed to fail during execution;
self-repair is the mechanism that lets the pipeline continue correctly after the
failure is fixed.

Use it from complex sequential skills such as `persona-dream` and
`monitor-opportunities`, where failures are expected and must not become status
reports, blind retries, skipped steps, or duplicate GitHub issues.

## Rule

A required step failure must not advance to the next step. It must run this
branch:

```text
STEP_FAILED
-> read immutable goal with goal-drift; fail preflight if no human-registered goal exists
-> classify raw signal with triage-error
-> compare the failure/repair category to the immutable goal and record goal_hash
-> compute stable category_key / failure_category_id
-> append replay ledger event
-> recall memory for prior fixes and graph-neighbor clues
-> search GitHub issues, including open, closed, blocked, and depends-on tickets
-> ask WebGPT for comprehensive analysis from the full project-agent context when an outside review is needed
-> convert WebGPT findings into focused ticket candidates only, never free-form work guidance
-> bind/update/reopen/create one category ticket
-> route eligible repair through project-watchdog
-> project agent monitors push/pull receipts across Ask, tickets, watchdog, Pi async runs, and the ledger
-> require retained agentic-evals coverage for the repair
-> rerun the SAME failed step from its checkpoint/input receipt
-> advance to the next pipeline step only after that step passes and the ledger validates
```

## Sequential pipeline execution contract

This skill is not only a failure logger. It is the required control loop for a
sequential pipeline. The pipeline does not succeed by avoiding failures; it
succeeds by detecting each required-step failure, repairing it with evidence,
rerunning the failed step, and then continuing.

For every required pipeline step:

```text
1. Run the next required step in order.
2. Read back the step receipt and produced artifacts.
3. If the step passed, append/retain the pass receipt and move to the next step.
4. If the step failed, blocked, timed out, or produced an invalid receipt:
   a. stop the pipeline immediately;
   b. call `record-failure` with the step receipt, run id, checkpoint, immutable
      goal project, and any provider-effect evidence;
   c. fail preflight if `$goal-drift goal --project <goal-project>` has no
      human-registered immutable goal;
   d. compare the repair category to the immutable goal and record the goal_hash;
   e. repair the category through the triage/ticket/watchdog/eval branch;
   f. rerun the same failed step from the same checkpoint or a declared
      superseding checkpoint;
   g. repeat repair/rerun until the step passes, attempts are exhausted, or a
      real human/provider blocker is recorded.
5. Never skip a required step because it is expected to fail.
6. Never repair work that does not compare against the immutable goal; that is
   goal drift, not self-repair.
7. Never continue to step N+1 while step N has an open blocking repair category.
8. Never mark the pipeline complete until `validate-ledger --require-agentic-eval`
   passes and the pipeline-specific final proof receipt passes.
```

Expected failures are not exceptions to this rule. They are exactly why the
self-repair branch exists: expected failure still creates a blocking category,
gets repaired or explicitly blocked, then the failed step is rerun before the
pipeline advances.

## Why this exists

Complex pipelines fail by design: providers change, browser tabs stale, source
feeds drift, schedulers run stale revisions, and generated media misses visual
requirements. A bare failure message tells the next agent nothing. This skill
records the failure as data, searches prior memory and issue history, deduplicates
repair work, and blocks unsafe forward progress until proof exists.

## Commands

Run from the repo root or the skill directory.

### Run one `$memory` hardening cycle

Use this when the anti-kludge goal is to turn comprehensive context review into
bounded repair work without manual prose translation:

```bash
skills/pipeline-self-repair/run.sh hardening-cycle \
  --memory-repo ${HOME}/workspace/experiments/memory \
  --ledger <optional-replay-ledger.jsonl> \
  --ticket-ref grahama1970/agent-skills#1533 \
  --output-dir <cycle-output-dir> \
  --json
```

Default mode is safe and local: it reads the scorecard, finds the latest
response-surface receipt, summarizes supplied ledgers, writes a comprehensive
WebGPT ticket-only prompt, projects ticket/watchdog/monitor commands, and emits
`pipeline_self_repair.hardening_cycle.v1` at
`<output-dir>/hardening-cycle-receipt.json`. It does not call WebGPT or create
GitHub issues unless explicitly allowed.

After a WebGPT response exists, parse it into focused work items:

```bash
skills/pipeline-self-repair/run.sh hardening-cycle \
  --webgpt-response <response.md> \
  --output-dir <cycle-output-dir> \
  --json
```

Mutation flags are explicit:

```bash
  --execute-ask    # run cd skills/ask && ./run.sh webgpt "<ticket-only prompt>"
  --apply-ticket   # create projected ticket candidates through $ticket
```

The command is intentionally a cycle boundary, not an auto-repair oracle. It
stops after producing receipts, parsed ticket candidates, ticket projections,
watchdog status, and project-agent push/pull monitoring commands. The project
agent then files/binds the accepted ticket(s), runs `$triage-error` for any
`TRIAGE_REQUIRED` candidate, and dispatches `$project-watchdog` only after a
focused ticket exists.

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
  --goal-project persona-dream \
  --repo grahama1970/agent-skills \
  --json
```

Default behavior is safe: it first reads the immutable goal via `$goal-drift`,
fails preflight if no human-registered goal exists, writes the ledger, and drafts
ticket commands. It does not publish a GitHub issue or run watchdog. Add explicit
flags when the pipeline is allowed to mutate external systems:

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

### Monitor the repair branch

The project agent owns orchestration and monitoring. Use this command to emit the
push/pull monitoring plan and read back the artifacts the CLI can inspect:

```bash
skills/pipeline-self-repair/run.sh monitor \
  --ledger <run-root>/replay_ledger.jsonl \
  --ask-run-dir <ask-run-dir> \
  --ticket-ref grahama1970/agent-skills#1234 \
  --subagent-run-id <pi-async-run-id> \
  --watchdog-project agent-skills \
  --json
```

`monitor` reports:

- **push monitoring** the Pi parent must arm, such as
  `subagent_wait({"id":"...","nonBlocking":true})` for owned async runs;
- **pull monitoring** commands for Pi fleet/status, Ask projections, ticket
  lookup, project-watchdog status, and ledger inspection;
- ledger open-failure counts and category state;
- ticket/watchdog/Ask readback status when those artifact refs are supplied.

The shell CLI cannot arm Pi wake subscriptions itself. The project agent must do
that from the parent Pi session, then keep pulling receipts until the category is
`CATEGORY_GREEN`, `CLOSED`, or explicitly blocked for a human/provider decision.

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

This fails if any blocking failure lacks immutable-goal comparison, triage,
category, ticket disposition, or retained eval proof.

### Run the agentic-evals remediation projection for a complete eval report

```bash
skills/pipeline-self-repair/run.sh agentic-eval-remediate \
  --report <agentic_evals.report.v2.json> \
  --category-map <skill>/fixtures/category_map.json \
  --fixture <skill>/fixtures/agentic_eval.json \
  --ledger <run-root>/replay_ledger.jsonl \
  --goal-project persona-dream \
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
  "goal_hash": "sha256:...",
  "goal_alignment": {"status": "PASS_COMPARED_TO_IMMUTABLE_GOAL", "project": "persona-dream"},
  "category_key": "persona-dream/phase-11-kling-submit/<triage-code>/skills-persona-dream/v1",
  "failure_category_id": "agentic-evals:agent-skills:persona-dream-phase-11-kling-submit-...",
  "memory_recall": {"status": "PASS|SKIPPED|FAILED", "found": true},
  "github_issue_search": {"status": "PASS|SKIPPED|FAILED", "matches": []},
  "ticket": {"action": "bind_existing|create_draft|created|needs_reopen|blocked_by_upstream"},
  "repair_state": "TICKETED|NEEDS_TRIAGE|NEEDS_HUMAN|WATCHDOG_DISPATCHED",
  "blocking": true
}
```

## WebGPT analysis to focused ticket boundary

WebGPT is useful here because it can inspect a comprehensive context packet and
return high-quality outside analysis. The output boundary is still `$ticket`, not
prose. When the project agent invokes `$ask webgpt` for hardening or process
repair, the prompt must require one of these forms for every finding:

```text
TICKET
Type: bug|feature|optimization|maintenance|triage
Title: <focused issue title>
Target: <file, skill, service, or workflow>
Current state: <observed failure, limitation, or missing capability>
Requested outcome: <one concrete behavior or artifact>
Route: <canonical ticket route>
Requested repair agent: <agent id or unknown>
Scoped files: <paths or explicit unknown>
Non-goals: <what must stay out of scope>
Required proof: <live E2E proof plus retained agentic-evals guard>
Failure code: <triage-error code or TRIAGE_REQUIRED>
```

or:

```text
NO_TICKET: <why this observation is not independently actionable>
```

The project agent then files or binds one focused `$ticket` per accepted ticket
candidate. `$triage-error` owns ambiguous or generic failures before they become
tickets. `$project-watchdog` owns eligible repair dispatch. The project agent
monitors the whole loop and runs `$brave-search` or `$dogpile` only when local
receipts leave an external fact, upstream behavior, provider change, or root
cause unresolved. Do not branch into unrelated cleanup while a blocking category
is open.

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
immutable goal readback and goal_hash
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
- immutable-goal preflight through goal-drift
- triage interface
- category key convention
- memory and GitHub search events
- WebGPT-to-focused-ticket boundary
- ticket upsert/disposition rules
- watchdog handoff rules
- project-agent push/pull monitoring plan
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
