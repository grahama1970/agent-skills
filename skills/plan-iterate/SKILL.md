---
name: plan-iterate
description: Evidence-gated phase iteration for implementation plans. Use when a task must proceed phase by phase with deterministic artifacts, validation logs, named external reviewer verdicts, default scillm GPT-5.5 high review, optional reviewer comparison, blocker tracking, and fail-closed acceptance before advancing; especially for security, correctness, deployment, or report-hardening work.
---

# Plan Iterate

Use this skill to control implementation phases:

```text
define phase -> implement -> validate locally -> package evidence -> external review -> patch blockers -> accept -> advance next phase or stop blocked
```

It does not replace `/plan`, `/review-plan`, `/orchestrate`, `$hack`, or `review-extraction`. It verifies whether an implemented phase satisfied its contract with evidence.

## Parent Role

`$plan-iterate` is the parent phase controller. Domain review skills run inside
the phase; they do not replace the phase ledger or acceptance gate.

## Deterministic Outer Loop Contract

`$plan-iterate` must be implemented as a state machine, not as an instruction
to a project agent to "keep going." A project-agent message is never a terminal
condition. Only the `$plan-iterate` controller can make the phase terminal, and
it may emit `PASS`/`accepted` only when both the stored aggregation gate and the
deterministic validation/evidence gates pass.

Canonical control flow:

```text
while overall goals remain unmet:
  select next runtime-ready phase from the plan graph
  if no runtime-ready phase exists but an agent-actionable blocked/failing phase exists: resume that phase
  if no runtime-ready or agent-actionable phase exists: stop only with proven BLOCKED or HUMAN_REQUIRED
  while iteration < externally_configured_max_iterations:
    project agent applies exactly one patch iteration
    project agent writes project-agent-result.json
    deterministic validators run and write logs/artifacts
    relevant $review-* skills build read-only bundles/artifacts
    $scillm gpt-5.5 high aggregates those bundles into review_result.json
    controller reads review_result.json
    if PASS: mark phase complete/accepted when deterministic evidence also passes, then immediately advance to the next runtime-ready phase
    if NEEDS_CHANGES: create the next patch iteration plan and continue
    if BLOCKED or INSUFFICIENT_EVIDENCE: stop and ask/interview human
    if max iterations reached: stop and ask/interview human
```

### Cross-Phase Continuation Contract

When the human has supplied clear overall goals and a plan graph or active phase
sequence exists, `$plan-iterate` continues across phase boundaries until one of
the explicit stop states occurs. `accepted` is terminal only for the current
phase. It is not permission for the project agent to yield, summarize, or wait
for another prompt when the next phase is runtime-ready.

After a phase reaches `accepted`, the controller must inspect the active plan
graph and do exactly one of the following:

1. start the next runtime-ready phase in the same run/session;
2. mark all overall goals complete only when there is no remaining phase or
   unmet acceptance contract item, and project knowledge does not name
   remaining executable work; or
3. stop with `BLOCKED`, `MAX_ITERATIONS_REACHED`, or `HUMAN_REQUIRED` and write
   the exact missing runtime fields, repeated blocker, exhausted iteration
   limit, or human decision needed to proceed.

If no later phase exists but `PROJECT_KNOWLEDGE.md` names a current blocker,
unmet goal, or `Next agent-executable candidate`, the controller must not emit
`OVERALL_COMPLETE`. For agent-executable remaining work it emits
`decision=PROJECT_GOALS_REMAIN`, `should_continue=true`, and
`next_action.type=create_next_phase_from_project_knowledge`. For unmet work
that lacks an agent-executable next candidate, it stops with `HUMAN_REQUIRED`.

Do not ask the human to say "proceed" between accepted phases when the next
phase has clear goals, runtime readiness, and no unresolved blocker. A handoff
sentence such as "Next phase is ..." is not a controller terminal state and must
not replace actually starting the next phase. The externally configured maximum
iteration count limits patch attempts inside a phase; it does not convert a
successful phase acceptance into a whole-plan stop.

### Non-Ambiguous Continuation And Stop Taxonomy

`$plan-iterate` decisions are mechanical. The project agent must never infer a
stop from phase prose, a ledger label, or an accepted current phase.

Controller decision meanings:

```text
CONTINUE                The agent must keep working. No final response is allowed.
PROJECT_GOALS_REMAIN    The agent must create/resume a phase from project knowledge.
OVERALL_COMPLETE        A final response is allowed only after guard-final also permits it.
BLOCKED                 A final/blocking response is allowed only with repeated escalated stop evidence.
MAX_ITERATIONS_REACHED  A final/blocking response is allowed only when the configured iteration cap is exhausted.
HUMAN_REQUIRED          A final/blocking response is allowed only for a named human-only dependency.
```

`HUMAN_REQUIRED` must not be used for:

- a failed validator with an obvious diagnostic;
- a missing artifact the agent can regenerate;
- a reviewer `needs_changes` finding;
- `external_review_blocked` without repeated escalated blocker evidence;
- a later phase that is blocked/failing but still agent-actionable;
- missing runtime fields when the agent can create or supersede the phase from
  the known product goal.

`external_review_blocked` and `local_validation_failed` are recovery states by
default. They become hard stops only when the phase ledger proves all of the
following:

- the active blocker repeated across at least two focused loops;
- the blocker is marked `escalated:true`;
- `$dogpile` or a recorded not-applicable rationale has been evaluated when
  outside research could plausibly help;
- the stop record names the exact credential, admin action, policy decision,
  unavailable client/device, or product-scope decision that the agent cannot
  discover or safely assume.

After an accepted phase, the controller must check, in order:

1. later runtime-ready phases;
2. later agent-actionable `local_validation_failed` or
   `external_review_blocked` phases;
3. `PROJECT_KNOWLEDGE.md` for `Next agent-executable candidate` or equivalent
   remaining work;
4. non-actionable repeated/escalated blockers;
5. only then `OVERALL_COMPLETE`.

Any final response that claims completion, readiness, blocked status, or human
need before this ordering has been evaluated is invalid.

Required project-agent result shape:

```json
{
  "iteration": 2,
  "status": "patch_applied | blocked | needs_human",
  "files_changed": [],
  "commands_run": [],
  "remaining_blockers": [],
  "requires_human": false
}
```

Required controller terminal states:

```text
PASS
BLOCKED
MAX_ITERATIONS_REACHED
HUMAN_REQUIRED
```

`done`, `looks good`, `ready`, empty output, stopped output, or any other
project-agent prose must be ignored as closure evidence. If the project agent
stops without a gate terminal state, the controller records a non-status event
or blocker reason. This record is not a `PHASE_STATUS.status` value:

```json
{
  "event_state": "needs_attention",
  "phase_status": "external_review_blocked",
  "reason": "project_agent_stopped_without_terminal_verdict",
  "safe_default": "do_not_mark_complete",
  "resume_hint": "Resume from review_result.json blockers."
}
```

The maximum iteration count must be supplied by the caller/plan graph. Do not
hardcode a max iteration value inside prompts or project-agent instructions.

Before any final response or handoff summary, run the continuation guard against
the active repo ledger:

```bash
/home/graham/workspace/experiments/agent-skills/skills/plan-iterate/run.sh guard-final --repo-root . --message-file /tmp/final-message.txt
```

The guard emits `plan_iterate.continuation_guard.v1`. If `block_final=true`,
do not send the final response. If `should_continue=true`, no final response is
allowed at all: continue execution and use only non-final progress updates while
tools are still running. Do not downgrade to `BLOCKED`,
`MAX_ITERATIONS_REACHED`, or `HUMAN_REQUIRED`. Those stop labels are allowed
only when the guard also says `should_continue=false` and the message names the
exact non-agent dependency. A Codex Stop hook calls the same guard, so this is a
required preflight, not optional documentation.

`guard-final` must also block final responses when all phase ledgers are
terminal but `PROJECT_KNOWLEDGE.md` names agent-executable remaining work. In
that case the only valid action is to create or resume the next phase; a summary
may be emitted only as a non-final progress update.

### Fixable Work Is Not A Stop

Do not treat `local_validation_failed`, `external_review_blocked`, a failed
canary, a network diagnostic failure, a missing artifact, or a reviewer
`needs_changes` finding as permission to yield. Those are phase ledger states,
not proof that the project agent is blocked.

A project agent may stop only when the controller state is one of the explicit
hard stops and the stop record proves why the agent cannot take the next
action:

1. `HUMAN_REQUIRED`: a credential, policy choice, external account/admin
   action, unavailable client device, or product-scope decision cannot be
   discovered or safely assumed.
2. `MAX_ITERATIONS_REACHED`: the externally configured phase iteration limit is
   exhausted and the current unresolved issues are recorded.
3. `BLOCKED`: the same blocker survived the required focused implementation or
   validation loops, the `$dogpile` escalation was evaluated when applicable,
   and the phase ledger records the repeated blocker, occurrence count,
   escalation evidence, and exact human decision or external dependency.

If the blocker is first-pass, has an obvious next diagnostic, has an alternate
implementation path, or can be worked around without violating the product
contract, it is agent-actionable. Continue debugging, patch the implementation,
or create/supersede a phase that proves the same product goal through the
fastest acceptable path. For example, if a Tailscale/Funnel route is failing
but the product goal is "client can use Sparta Chat within five days", the
agent must either continue Tailscale diagnostics or record a superseding
client-access phase for another authenticated route; it must not stop merely
because the original route failed.

Use this routing by default:

| Phase Surface | Domain Loop / Reviewer | Deterministic Evidence |
|---------------|------------------------|------------------------|
| UI / UX / visual design | `$review-design` | `$test-interactions`, `$surf` screenshots/CDP |
| Code implementation | `$review-code` | tests, typecheck, lint, build, runtime smoke |
| Prompt contract | `$review-prompt` | validators, expected-response fixtures, consumer smoke |
| Security / extraction / compliance | domain-specific review skill | raw proof artifacts and domain validators |

For design phases, `$review-design` should own the design reviewer loop, and
`$test-interactions` should run inside that loop as the deterministic live-DOM
verifier and focused screenshot source. `$plan-iterate` records the resulting
validation logs, screenshots, reviewer receipts, blocker ledger, and acceptance
decision.

For `$review-design iterate`, `$review-code` loops, and `$review-prompt` loops,
the main project agent must treat reviewer calls as read-only unless the human
explicitly authorizes an isolated implementation worker with a clear write
scope. The reviewer batch may write review artifacts and suggested changes, but
it must not edit production code, mutate the implementation, or mark the phase
accepted. `$plan-iterate` records each loop as `domain_review_loops[]` with
`mutates_production=false`, the reviewer `persona`, immutable goal, context
artifact, relevant `best-practices-*` skill inputs, discrete `end_state`,
pointers to `state.json`, `events.jsonl`, `aggregate_verdict.json`, and a
human-facing matrix.

Each domain review iteration must also create or update three project-agent
plan artifacts:

- implementation/patch plan: what the main project agent will change or
  intentionally decline to change;
- validation/evidence plan: deterministic commands, screenshots, fixtures,
  validators, or smoke checks that will prove the next state;
- review/escalation plan: which read-only reviewer loop runs next, what it will
  inspect, and when `$dogpile`, `$ask`, WebGPT, or human clarification is
  required.

These are not three separate phase plans. They are per-round control artifacts
inside the current `$plan-iterate` phase so a reviewer loop cannot silently
become an implementation owner.

For code phases, `$review-code` may run a code reviewer loop, but tests,
typecheck, lint, build, runtime smoke, and any required rendered verification
still decide whether implementation evidence is admissible. Reviewer patches or
diffs are suggestions to the main project agent, not repository ownership.

For prompt phases, standalone `$review-prompt` may own a coded
prompt-improvement loop over an explicit workspace or candidate artifacts. When
embedded inside `$plan-iterate`, `$review-prompt` is read-only against
production scope and may mutate only candidate artifacts or a temporary
workspace. If the human authorizes a mutating worker, record that as a separate
project-agent patch iteration or implementation-worker artifact, not as a
`domain_review_loops[]` reviewer entry. The main project agent applies any
prompt, schema, fixture, validator, or consumer-smoke changes to production
files. `$plan-iterate` records the terminal audit and blocks acceptance when
deterministic prompt gates fail. Model findings cannot override validator,
fixture, expected-response, schema, or consumer-smoke failures.

## Core Rules

- Do not mark a phase done from prose, status text, or absence of errors.
- Keep raw artifacts, validation logs, and reviewer responses in the phase directory.
- Treat scillm/WebGPT/external review as a bounded checkpoint, not an outsourced reasoning loop.
- Give `$scillm` bounded, replayable progress context on repeated reviews; do not rely on hidden CLI transcript state.
- Name the adjudicator for every review result: `webgpt`, `scillm`, `human`, or `deterministic_verifier`.
- A reviewer verdict is a receipt, not closure. Only the `$plan-iterate`
  controller may close a phase, and only after both the stored aggregation gate
  and deterministic validation/evidence gates pass.
- Domain reviewer/subagent calls must be read-only: they may critique and suggest
  changes to the main project agent, but the main project agent owns all file
  edits, Memory-significant mutations, deterministic validation, and phase state.
- Domain review loops must leave a machine-readable and human-readable trace:
  `state.json`, `events.jsonl`, `aggregate_verdict.json`, a context artifact,
  a relevant `best-practices-*` skill list, three per-iteration plan artifacts,
  and a matrix suited to the surface: screenshot-to-finding for design,
  file/diff-to-finding for code, or prompt-fixture/gate-to-finding for prompts.
  Every loop event must end in a discrete state such as `verified`,
  `needs_patch`, `blocked`, `failed`, or `skipped`.
- Canonical `domain_review_loops[].end_state` values are `verified`,
  `needs_patch`, `blocked`, `failed`, and `skipped`. Domain skills may keep
  local states, but must map them into this enum before phase aggregation:
  `satisfied -> verified`, `needs_changes -> needs_patch`,
  `insufficient_evidence -> blocked`, `halted with blockers -> blocked`,
  `waiting_review/running -> failed`, and non-applicable skip artifacts with
  verified applicability -> `skipped`.
- Do not call heuristic classification, label copy, or report generation a review unless a named reviewer actually reviewed replayable evidence.
- Use reviewer comparison when the phase crosses a trust boundary or prior solo iteration produced a false green.
- Escalate before closure when raw evidence disagrees with report claims, a blocker repeats twice, or the human disproves a green claim.
- When a blocker repeats after two focused implementation/review loops, run
  `$dogpile` for source-derived outside insight before another solo patch
  attempt, unless the blocker is provably local-only and external research has
  no plausible value. Record the dogpile query, report path, useful findings,
  and any "not applicable" rationale in phase progress context.
- If the same blocker repeats after applying or evaluating `$dogpile` findings,
  stop execution instead of continuing solo iteration. Set the phase to
  `external_review_blocked` or `local_validation_failed` as appropriate, write
  the repeated blocker and dogpile summary into phase progress context, and ask
  the human concise clarifying questions tied to the unresolved decision or
  missing evidence.
- Run canaries before batching: one positive, one negative, one ambiguous/insufficient-evidence, one expected failure, and one regression fixture.
- For security-sensitive work, require raw proof artifacts, command logs, manifest hashes, and post-patch verification before accepting closure claims.

## Phase States

Use only these states:

```text
planned
implementing
local_validation_failed
ready_for_review
external_review_blocked
external_review_passed
accepted
superseded
abandoned
```

A phase is complete only when its status is `accepted`.

## CLI

Run commands from the repository root that owns the phase work:

```bash
skills/plan-iterate/run.sh init --phase phase-01-report-cleanup
skills/plan-iterate/run.sh record-skill-context --phase phase-01-report-cleanup --context /tmp/headless-skill-context.md
skills/plan-iterate/run.sh record-context --phase phase-01-report-cleanup --context /tmp/phase-context.md
skills/plan-iterate/run.sh record-plan-graph --phase phase-01-report-cleanup --graph /tmp/phase-plan.dag.json
skills/plan-iterate/run.sh inspect-plan-graph --phase phase-01-report-cleanup --graph /tmp/phase-plan.dag.json
skills/plan-iterate/run.sh continue --phase phase-01-report-cleanup
skills/plan-iterate/run.sh package --phase phase-01-report-cleanup --output /tmp/phase-01-review.zip
skills/plan-iterate/run.sh record-review --phase phase-01-report-cleanup --verdict blocked --review scillm-gpt55-review.md
skills/plan-iterate/run.sh status
```

Use `--root DIR` when the phase state should live outside the current repository. The default root is `.plan-iterate`.

`continue` is the controller-owned cross-phase decision command. It emits a
machine-readable `plan_iterate.continue_decision.v1` JSON object with
`decision`, `controller_terminal_state`, `stop`, `should_continue`,
`active_phase`, and `next_action`. After an `accepted` phase, it refuses to
treat the plan as yielded when a later runtime-ready phase exists or when
`PROJECT_KNOWLEDGE.md` names an agent-executable next candidate. Later
runtime-ready phases return `decision=CONTINUE` and name the next phase.
Project-knowledge continuations return `decision=PROJECT_GOALS_REMAIN` and
`next_action.type=create_next_phase_from_project_knowledge`. It returns a
stopping decision only for explicit controller states such as `BLOCKED`,
`HUMAN_REQUIRED`, or `MAX_ITERATIONS_REACHED`. Project agents should invoke
`$interview` only when `continue` returns a stopping decision that requires
human input or the agent is genuinely blocked/confused.

Run the medium-complexity local sanity before relying on the skill after edits:

```bash
skills/plan-iterate/sanity.sh
```

The sanity creates a temporary git repo, proves missing skill context fails
closed, records headless skill context, records progress context, packages a
review ZIP, records two distinct passing reviewer receipts against the same
bundle, and closes reviewer comparison.

## Phase Status Contract

Each phase owns:

```text
.plan-iterate/<phase-id>/
  PHASE_STATUS.json
  PHASE_REVIEW_REQUEST.md
  reviews/
```

`PHASE_STATUS.json` must use schema `plan_iterate.phase_status.v1` and include:

```json
{
  "schema": "plan_iterate.phase_status.v1",
  "phase_id": "phase-03-evolution-decision-log",
  "plan_id": "",
  "status": "ready_for_review",
  "implementation_summary": "...",
  "acceptance_contract": [],
  "changed_files": [],
  "validation_commands": [],
  "evidence_artifacts": [],
  "progress_context_artifacts": [],
  "skill_context_artifacts": [],
  "plan_graph_artifacts": [],
  "active_plan_graph_artifact": "",
  "domain_review_loops": [],
  "review_artifacts": [],
  "known_caveats": [],
  "claims": [],
  "blockers": [],
  "memory_context": {
    "collection": "plan_iterate_phase_context",
    "keys": []
  },
  "reviewer_policy": {
    "required": true,
    "comparison_required": false,
    "closure_rule": "deterministic_validation_and_external_review"
  },
  "review_results": [],
  "review_comparison": {
    "agreement": "pending",
    "closure_allowed": false,
    "reason": ""
  },
  "review_status": "pending"
}
```

Validation command entries must include `command`, `exit_code`, and optional `log`.
Claims must cite evidence artifacts. Blockers with two or more occurrences must be marked `escalated: true`.
Project agents may create a DAG JSON and record it with `record-plan-graph`.
The graph is the replayable plan input; `PHASE_STATUS.json` is the ledger. A
recorded graph must include `exec_graph_version`, `graph_id`, `graph_goal`,
positive integer `self_improvement_iterations`, optional
`review_iteration_limits` with integer `review_code`, `review_design`, and
`review_prompt` maxima, `review_fanout_limits` with integer `review_code`,
`review_design`, and `review_prompt` maxima, and a non-empty `nodes[]` list.
Newly recorded graphs must also have a `plan_id`. If the source graph omits
`plan_id`, `record-plan-graph` generates one from `graph_id`, writes it into the
stored graph copy, records it in `PHASE_STATUS.plan_id`, and records it on the
matching `plan_graph_artifacts[]` entry. Existing older ledgers without
`plan_id` remain readable history and should not be invalidated solely because
they predate this field.
When `review_iteration_limits` is omitted, each domain inherits
`self_improvement_iterations`. Review fanout nodes must include
`review_scopes[]`; each scope must name `scope`, `model`, `agent`, `contract`,
`review_level`, and `proof_level`.
`active_plan_graph_artifact` must point at an entry in `plan_graph_artifacts`.
For cross-phase traceability, `record-plan-graph` also maintains a plan index:

```text
.plan-iterate/plans/<plan-id>/
  PLAN_STATUS.json
  phases.json
```

`PLAN_STATUS.json` and `phases.json` map the durable `plan_id` to every phase
ledger that has recorded a graph for that plan. The phase ledger remains the
source of truth for phase acceptance; the plan index answers which phases
belong to the same overall plan and which phase was most recently updated.
Recording a graph also writes a sibling
`runtime_readiness_artifact` with schema
`plan_iterate.graph_runtime_readiness.v1`. The readiness artifact is the
human/project-agent surface for missing execution fields. It lists every node,
the adapter that would be used, required fields, present fields, missing fields,
inferred fields, and whether the graph can be compiled to runtime execution.
`inspect-plan-graph` prints the same report without recording it.

Recording a graph must also write a sibling `plan_ascii_artifact`, normally
`plan-graphs/<timestamp>-<graph-id>-plan-ascii.md`. This artifact is the
always-available human-readable execution map. It must show:

- the graph id, graph goal, active phase ledger status, and legend;
- every plan node in dependency order;
- which nodes are completed, active, pending, blocked, manual, or runtime-ready;
- which groups are sequential and which same-depth dependency lanes may run
  concurrently;
- missing runtime fields and the next action for nodes that are blocked or
  manual.

The ASCII artifact is informational, not closure evidence. It may mark a node
completed only from explicit node completion fields, an accepted matching phase
ledger, or another deterministic status source recorded in the phase. Unknown
or unproven work stays pending/manual/blocked; do not infer completion from
intent, proximity, or reviewer prose.

Semantic node execution readiness is fail-closed:

- `review-code` needs review context, files, and `review_scopes[].scope`,
  `model`, `agent`, `contract`, `review_level`, and `proof_level`.
  Files may be inferred from
  `PHASE_STATUS.changed_files`; context is never inferred.
- `review-design` needs a persona plus screenshots or a test-interactions
  manifest.
- `test-interactions` needs a manifest, or a URL plus persona, and an output
  directory.
- `review-prompt` needs the prompt/template, concrete fixture/context, expected
  response, validator or smoke command, and consumer/schema.
- `project-agent` nodes are manual until they include an explicit command,
  handoff, or task plus acceptance evidence.
- Runtime `scillm.exec` nodes (`local_command`, `scillm_call`, `scillm_batch`,
  `codex_exec`, `claude_print`, deterministic render/verifier) must include the
  command, model, prompt, items, or manifest required by their runtime type.

`domain_review_loops` entries must include `skill`, `persona`,
`immutable_goal`, `context_artifact`, non-empty `best_practice_skills`,
`state_artifact`, `events_artifact`, `aggregate_artifact`, `matrix_artifact`,
`iteration_plans`, `end_state`, and `mutates_production:false`.
`best_practice_skills` entries must name `best-practices-*` skills that were
available to the reviewer loop. `matrix_artifact` is the human-facing ledger for
the domain loop: screenshots/findings for design, files/diffs/findings for code,
or prompt fixtures/gates/findings for prompt contracts.

Each `iteration_plans[]` entry must include a positive `round` and exactly these
three phase-relative artifacts:

- `implementation_plan_artifact`
- `validation_plan_artifact`
- `review_plan_artifact`

The referenced context, state, event, aggregate, matrix, and iteration-plan
artifacts must be listed in `evidence_artifacts`, `review_artifacts`, or
`progress_context_artifacts`.
`external_review_passed` and `accepted` cannot include unresolved loop end
states: `needs_patch`, `blocked`, or `failed`.
`review_results` must cite stored `review_artifacts` with response/request/bundle/receipt hashes, `phase_subject_sha256`, `skill_context_sha256`, invocation metadata, and `recorded_at`.
For repeated reviews, `review_results` after the first must include `progress_context_sha256`, and the phase must include `progress_context_artifacts` or Arango-backed `memory_context.keys`.
Normalized `review_results[].verdict` values are `pass`, `needs_changes`,
`blocked`, `insufficient_evidence`, `conditional_pass`, `malformed`, and
`no_verdict`. `accepted` fails closed on any unresolved non-`pass` review result
or stale-subject `pass`. Every prior non-`pass` or stale-subject result must
have `resolution_status` before the controller may emit `accepted`.
When a repeated review passes after a prior `blocked`, `needs_changes`, or
`insufficient_evidence`, `conditional_pass`, `malformed`, or `no_verdict`
result, keep the earlier result as audit history and mark it with
`resolution_status: "resolved_by_later_pass"` plus the resolving reviewer and
timestamp. Do not delete or rewrite the earlier reviewer artifact.
When a repeated review passes after an earlier PASS that was bound to an older
phase subject, keep the earlier PASS as audit history and mark it with
`resolution_status: "superseded_by_later_pass"` plus the resolving reviewer and
timestamp. The latest unsuperseded PASS is the closure evidence.
Implementation claims may cite only deterministic `evidence_artifacts`, not reviewer receipts.
`accepted` always requires hashed changed file bytes, hashed deterministic
evidence artifacts, hashed validation logs bound to the current phase subject,
at least one claim covering the acceptance contract, and passing deterministic
validation/evidence gates. If `reviewer_policy.required=false`, only external
review/comparison is waived; deterministic validation is never waived. For
review-gated `$plan-iterate` phases, `accepted` additionally requires
`review_comparison.closure_allowed=true` and a current stored aggregation gate
`PASS`.
`phase_subject_sha256` binds the acceptance contract, changed file paths and hashes, deterministic evidence, validation commands, claims, reviewer policy, known caveats, blockers, progress context references, skill context references, and memory context references.

## Review Bundle

`package` creates a ZIP containing:

```text
PHASE_STATUS.json
PHASE_REVIEW_REQUEST.md
changed-files.diff
manifest.json
validation-logs/
evidence-artifacts/
progress-context/
skill-context/
domain-review-loops/
plan-graphs/*-plan-ascii.md
reviews/
```

The package fails closed when claims lack artifacts, evidence files are missing, progress context files are missing, skill context files are missing, validation commands lack exit codes, accepted validation logs lack current hashes, review results lack named adjudicators/provenance, review artifact hashes do not match current bytes, repeated reviews lack progress context, accepted phases have unresolved non-`pass` review results or stale-subject passes, repeated blockers are un-escalated, reviewer comparison does not allow closure for review-gated phases, or accepted phases lack passing validation and deterministic evidence.

## External Reviewer Loop

Use external reviewers only at phase checkpoints, canaries, or escalation triggers:

```text
project agent implements phase
plan-iterate packages evidence
domain review skill bundles the phase completion for review
scillm/WebGPT/human reviews the domain bundle and phase evidence
project agent records verdict
project agent patches exact blockers
repeat until pass or stop
```

Preserve reviewer outputs as `reviews/<timestamp>-<reviewer>-response.md` through `record-review`.

## Repeated Blocker Research Escalation

`$plan-iterate` should not keep cycling through the same local hypothesis when
a blocker survives two focused patch/validation/review attempts. At that point,
run `$dogpile` as the default research escalation before the next patch attempt.

Use `$dogpile` to search for:

- upstream library issues, examples, and implementation patterns;
- similar GitHub bugs, PRs, and code paths;
- current documentation or migration notes;
- known UI, browser, accessibility, or framework edge cases;
- design precedents when the blocker is product/UX clarity rather than code.

The dogpile output is advisory, not closure. The project agent still owns the
patch, deterministic validation, screenshots, tests, and reviewer loop. Store
the dogpile report or partial-result artifacts in the phase as progress context
and cite only deterministic evidence for acceptance claims.

If `$dogpile` returns an ambiguity handoff, ask the human or narrow the query
from phase context before spending more review cycles. If provider lanes degrade,
record the degraded provider status and use successful sources; do not treat a
partial dogpile failure as total research failure.

If the blocker still repeats after `$dogpile` has been evaluated, stop the loop.
Do not run another implementation pass from the same hypothesis. The stop record
must include:

- the blocker text and occurrence count;
- the validation/review artifacts showing the repeated failure;
- the dogpile query, report path, and relevant findings or degraded sources;
- what was tried after dogpile;
- the exact human clarification needed to proceed.

Ask at most three concise questions. Each question should map to a decision that
cannot be resolved from code, deterministic evidence, reviewer receipts, or
dogpile results.

Each phase completion review should use the domain-appropriate bundle:

- `$review-design` bundle or loop artifacts for UI/UX phases. It must include
  fresh rendered screenshots and, when interaction matters, `$test-interactions`
  results plus focused/container screenshot evidence. For `$review-design
  iterate`, include the loop `state.json`, `events.jsonl`,
  `aggregate_verdict.json`, per-section verdicts, and the screenshot/review
  matrix, immutable goal, context artifact, relevant best-practice skills, and
  three per-round plans so the main project agent can evaluate the loop without
  reading raw model transcripts.
- `$review-code bundle` for code phases. It must include the current scoped
  diff, relevant tests/checks, expected contracts, non-goals, known caveats,
  blockers, progress context, and headless skill context. For `$review-code`
  loops, include `state.json`, `events.jsonl`, `aggregate_verdict.json`,
  per-round reviewer verdicts, applied/rejected patch records, test results,
  immutable goal, context artifact, relevant best-practice skills, three
  per-round plans, and a file/diff-to-finding matrix. The project agent applies
  patches and deterministic tests/checks decide closure.
- `$review-prompt` final audit bundle for prompt-contract phases. It must
  include prompt templates, concrete fixtures, expected responses, validators,
  smoke output, scoring/keep decisions, and any `$ask`/WebGPT final gate
  artifacts. For `$review-prompt` loops, include `state.json`, `events.jsonl`,
  `aggregate_verdict.json` or terminal `audit.json`, per-round model requests
  and responses, score/decision artifacts, validator/smoke outputs, and a
  prompt-fixture/gate-to-finding matrix, immutable goal, context artifact,
  relevant best-practice skills, and three per-round plans. Deterministic gates
  and keep/revert decisions decide whether a prompt candidate is admissible.

The default reviewer path for phase-level semantic review is the
domain-appropriate bundle -> `$scillm` `gpt-5.5` high reasoning. The reviewer
may critique the phase; the project agent still owns code changes, prompt
changes, UI changes, and deterministic validation.

For mixed phases, build all applicable domain review bundles concurrently:

```text
$review-code bundle/artifacts   -> code findings
$review-design bundle/artifacts -> visual/interaction findings
$review-prompt final audit      -> prompt-contract findings or skipped_fail_closed with verdict not_applicable_verified
```

Then send the relevant bundle set plus deterministic evidence to `$scillm`
`gpt-5.5` with top-level `reasoning_effort: "high"` and no `max_tokens`.
The `$scillm` response is the phase gate artifact and must answer:

```json
{
  "verdict": "PASS | NEEDS_CHANGES | BLOCKED | INSUFFICIENT_EVIDENCE",
  "goals_met": false,
  "highest_severity": "critical | high | medium | low | none",
  "issues": [],
  "next_plan": [],
  "human_questions": []
}
```

Any unresolved `medium`, `high`, or `critical` issue means the controller must
create the next project-agent patch plan or stop for human input; the phase
cannot be accepted.

Default reviewer:

- `scillm:gpt-5.5-high`: default external reviewer for targeted phase/code/contract review. Use `$scillm` with `model: "gpt-5.5"` and top-level `reasoning_effort: "high"`, preferably streaming for long review bundles. It is replayable, scriptable, and exposes machine-readable reasoning proof.

Escalation and comparison reviewer use:

- `webgpt`: optional escalation for strategy, taxonomy decisions, report
  clarity, cross-project process review, or an independent human-facing
  judgment check using the real `$ask` WebGPT route (`$ask webgpt` or
  `--oracle-backend webgpt`). `$surf` is only the browser transport owned by
  `$ask`; do not call it directly for review work, and do not make WebGPT the
  default when `$scillm` can review the same bundle.
- `scillm:gpt-5.5-high`: hard semantic or multimodal canaries; expensive, not for broad batches.
- `scillm:claude-sonnet-high`: adversarial plan, prompt, and implementation critique.
- `scillm:gemini-flash-high`: long-context PDF/report review when latency and cost matter.
- `scillm:oc-kimi`: bounded visual batches after canaries prove the prompt, schema, and image attachment contract.
- `scillm:opencode-deepseek`: text-only code or schema review; do not use for visual bbox decisions.
- `human`: policy, semantic, or residual ambiguity that the project agent and reviewers cannot resolve.

Record the default scillm GPT-5.5 high review:

Use a replayable request JSON that includes `model: "gpt-5.5"` and top-level
`reasoning_effort: "high"`. For long bundles, prefer SSE streaming and preserve
the request JSON, SSE/raw response, extracted review markdown, and final
`scillm_reasoning` proof. Do not set `max_tokens`; reasoning models can consume
internal reasoning tokens and low caps can produce empty output.

For headless reviewers and subprocess agents, record a compact skill context
artifact before packaging review evidence. Treat headless calls as skill-blind
unless the request explicitly includes the relevant skill names, absolute
`SKILL.md` paths, runtime entrypoints, artifact protocol, and role boundaries.
The skill context should state which component is orchestrator, reviewer,
implementer, memory store, and human escalation path.

Record headless skill context:

```bash
skills/plan-iterate/run.sh record-skill-context \
  --phase phase-01-report-cleanup \
  --context /tmp/headless-skill-context.md
```

For the default phase-review loop, the context should mention at minimum
`$plan-iterate`, `$review-code`, `$scillm`, `$memory`, and `$interview`. Add
`$code-runner` or `$subagent-runner` only when that phase actually uses them.

For repeated reviews, include a bounded progress context artifact and store the
same compact context in ArangoDB through `$memory` using the
`plan_iterate_phase_context` collection. ArangoDB `$memory` is the default source
of progress history; local `progress-context/` files are hashable mirrors for
bundle replay, not the primary history store. The context should be source-derived:
prior reviewer findings, blocker ledger, decision log, current delta, and
artifact hashes. Store only compact progress context in ArangoDB; keep large
raw artifacts on disk and reference them by path/hash.

Record progress context before a non-first review:

```bash
skills/plan-iterate/run.sh record-context \
  --phase phase-01-report-cleanup \
  --context /tmp/phase-01-progress-context.md \
  --memory-key phase-01-review-002
```

`record-context` copies the context into `progress-context/`, records its
SHA-256 in `progress_context_artifacts`, and adds the ArangoDB key to
`memory_context.keys`. By default it writes the compact context to `$memory`
via `/upsert`. Use `--skip-memory-upsert` only for isolated tests or when memory
is operationally unavailable; report that gap because repeated reviews should
not depend only on hidden CLI state or local fallback files.

```bash
skills/plan-iterate/run.sh record-review \
  --phase phase-01-report-cleanup \
  --reviewer scillm-gpt55-high \
  --adjudicator-kind scillm \
  --verdict needs_changes \
  --review /tmp/scillm-gpt55-review.md \
  --review-request /tmp/scillm-request.json \
  --review-bundle /tmp/phase-review.zip \
  --invocation-command "curl /v1/chat/completions model=gpt-5.5 reasoning_effort=high" \
  --invocation-receipt /tmp/scillm-http-response.json \
  --model gpt-5.5
```

Record an optional WebGPT escalation review:

```bash
skills/ask/run.sh ask "Review the phase bundle at /tmp/phase-review.zip. Return PASS, NEEDS_CHANGES, or BLOCKED with specific fixes." \
  --oracle \
  --oracle-backend webgpt \
  --webgpt-tab-id 837343233 \
  --ask-id phase-01-webgpt-review \
  --json

skills/plan-iterate/run.sh record-review \
  --phase phase-01-report-cleanup \
  --reviewer webgpt \
  --adjudicator-kind webgpt \
  --verdict passed \
  --review .ask_artifacts/runs/phase-01-webgpt-review/review.md \
  --review-request .ask_artifacts/runs/phase-01-webgpt-review/phase-01-webgpt-review.request.json \
  --review-bundle /tmp/phase-review.zip \
  --invocation-command "ask webgpt --webgpt-tab-id 837343233 --deep-review-target /tmp/phase-review.zip" \
  --invocation-receipt .ask_artifacts/runs/phase-01-webgpt-review/phase-01-webgpt-review.status.json
```

When `reviewer_policy.comparison_required=true`, `record-review --verdict passed` stores each reviewer receipt without marking the phase externally passed. After all required distinct reviewers are recorded, set the comparison explicitly:

```bash
skills/plan-iterate/run.sh record-comparison \
  --phase phase-01-report-cleanup \
  --agreement agree \
  --closure-allowed \
  --reason "scillm GPT-5.5 high and comparison reviewer both passed the same bundle."
```

## Reviewer Comparison

Set `reviewer_policy.comparison_required=true` when:

- the phase changes correctness, extraction, security, compliance, deployment, memory, or user-facing verification;
- the human disproved an earlier green claim;
- a blocker survived two implementation attempts;
- the phase combines code, prompt, schema, data, and UI/report judgment.

Comparison is explicit state, not an implied mood:

```json
{
  "review_comparison": {
    "agreement": "agree",
    "closure_allowed": true,
    "reason": "scillm GPT-5.5 high and comparison reviewer agree; deterministic validation passed."
  }
}
```

Use only these agreement values:

```text
pending
agree
partial
disagree
insufficient
```

If reviewers disagree, duplicate the same reviewer, return `conditional_pass`, return `partial`, or evidence is insufficient, set `status=external_review_blocked`, keep `closure_allowed=false`, patch the blocker, and rerun the relevant validation/review. Do not batch or accept the phase from a split review.
`review_comparison.closure_allowed=true` is valid only when `agreement=agree`.
Comparison-required phases require all passing reviewers to reference the same `review_bundle_sha256`, and every review result must match the current `phase_subject_sha256` computed from the acceptance contract, changed file paths and hashes, deterministic evidence, validation commands, and claims.
