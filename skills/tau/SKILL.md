---
name: tau
description: >
  Operate and verify the local T'au project at ${HOME}/workspace/experiments/tau.
  Use for Tau loop, harness, watchdog cron, GitHub issue orchestration, TUI,
  Memory-first chat, and E2E proof/status tasks. This skill is a light wrapper
  around the Tau repo and must report mocked/live proof boundaries explicitly.
triggers:
  - tau
  - t'au
  - tau loop
  - tau harness
  - tau watchdog
  - tau tui
  - tau chat
  - verify tau
  - tau e2e sanity
provides:
  - task-orchestration
  - progress-tracking
  - ticket-lease-routing
  - proof-based-closure
composes:
  - memory
  - project-watchdog
  - test-interactions
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-subagent
  - best-practices-react
runtime_self_improvement: basic
taxonomy:
  - validation
  - resilience
  - orchestration
---

# Tau

Use this skill as the operator entrypoint for the local T'au project:

```text
${HOME}/workspace/experiments/tau
```

Do not duplicate Tau implementation in this skill. Use the scripts here to
locate the repo, run known proof commands, inspect receipts, and summarize gaps.

## Commands

Currently implemented in this skill wrapper:

```bash
skills/tau/run.sh doctor
skills/tau/run.sh status
skills/tau/run.sh sanity
skills/tau/run.sh proof-status
skills/tau/run.sh e2e
skills/tau/run.sh watchdog-status
skills/tau/run.sh latest-proofs
```

`doctor` checks whether this operator wrapper can resolve and invoke the local
Tau checkout. `status` reports current repo, GitHub issue, watchdog cron, and
latest receipt state. `sanity` runs bounded checks that do not mutate GitHub.
`proof-status` runs the same bounded sanity check plus repo/proof inspection and
states explicit non-claims. `e2e` is a compatibility alias for `proof-status`;
it is not a claim of full browser/provider/GitHub production E2E coverage.

Tau runtime lanes that may exist in the Tau repo, depending on checkout/version:

```bash
uv run tau dag-run
uv run tau herdr-cleanup
uv run tau dag-expansion-validate
uv run tau dag-expansion-policy
uv run tau dag-expansion-apply
uv run tau dag-route-memory-candidates
uv run tau dag-route-memory-sync
uv run tau dag-branch-locks-validate
uv run tau dag-motif-validate
```

Planned or recommended next runtime lanes. Do not claim these from this skill
unless `doctor`, `status`, or a local receipt proves they are present:

```bash
uv run tau doctor
uv run tau research-source-receipt
uv run tau github-redact-projection
uv run tau proof-index build
```

## Tau Runtime Lanes

### Local DAG Lane

Use local `tau.dag_contract.v1` DAGs for deterministic creator/reviewer loops,
repair loops, goal-guardian gates, reviewer joins, and non-provider stress
checks. Proof comes from DAG receipts, command-loop receipts, and focused test
commands, not from prose.

### Herdr-Visible Provider DAG Lane

Use Herdr-visible provider DAGs when the work must run in visible panes or
provider-specific surfaces. Herdr workspace, pane, and visible log output are
observability evidence. The canonical gate remains Tau work orders, work-order
hashes, provider readiness receipts, node receipts, cleanup receipts, and DAG
receipts.

### Adaptive DAG Lane

Adaptive DAG changes must follow:

```text
signal -> candidate -> validation -> policy -> apply-new-artifact -> rerun
```

Do not mutate a running DAG in prose. Do not silently add nodes. Expansion,
branch-lock, route-memory, and rerun claims require explicit receipts.

### Route-Memory Lane

Route-memory candidates are advisory until a quality-gated sync receipt and
readback artifact exist. Model confidence is not route proof. Positive route
signals should come from validators, reviewer receipts, and deterministic proof
artifacts.

### Branch-Lock Lane

Provider or mutating concurrent branches require explicit branch-lock metadata
and approval/provenance before they can become schedulable. Without branch-lock
proof, keep concurrent ready-node scheduling local-only and non-mutating.

### External Research / Paper Evidence Lane

Research is design input, not closure proof. ArXiv, Dogpile, WebGPT, Brave,
video, paper, or manual research must become a source-bearing receipt, route
through research-auditor/reviewer validation, and then be reconciled into local
artifacts and deterministic tests.

### GitHub Apply-Gate Lane

GitHub transport is dry-run by default. Live mutation requires explicit apply
authorization, target preflight, policy checks, redaction when public comments
are involved, and a transport receipt with exact commands and results.

### Proof Bundle / Run-Status Lane

Use `proof-status`, Tau run-status, and committed proof receipts to state what
was exercised and what remains unverified. A status page, latest-proof list, or
unit test is not an end-to-end claim unless the required live lane receipts are
present.

## Proof Rules

- State `mocked` and `live` boundaries for every result.
- Unit tests are not E2E proof.
- Loop and harness claims require fresh command-loop/watchdog receipts.
- TUI claims require targeted Textual/TUI checks.
- Chat UI claims require browser/CDP screenshot verification from the host app.
- Chat UI interaction manifests must follow `test-interactions`: live DOM
  `[data-qid]` selectors only, deterministic assertions, and no fake fixtures
  for production claims.
- React chat changes must follow `best-practices-react`: interactive elements
  need `data-qid`, `data-qs-action`, `title`, and host action registration.
- Subagent handoffs must use `tau.agent_handoff.v1`.
- Human goal changes must use `tau.human_goal_change.v1`; non-human agents may
  propose but not apply immutable goal changes.

## Default Project-Agent Interface: DAG Contracts

For multi-step project-agent work, communicate with Tau by DAG contract by
default. Direct `tau.agent_handoff.v1` packets are still the node-level
subagent protocol and remain acceptable for trivial one-step work, but creator
/ reviewer loops, repair loops, provider work, goal-guardian gates, reviewer
joins, and any workflow with retry or iteration policy should be represented as
a DAG.

Project agents should not encode orchestration policy in prose, issue comments,
or ad hoc prompt instructions when a DAG can express the work. The DAG contract
is the durable instruction; Tau owns dispatch, receipt validation, route
continuity, resume behavior, timeout/max-attempt handling, immutable-goal
enforcement, and fail-closed drift detection.

Default flow:

```text
project agent -> tau.dag_contract.v1
Tau -> node-level tau.agent_handoff.v1 turns + receipts
subagents -> artifacts + receipts
Tau -> DAG receipt/verdict
```

Minimum DAG contract fields:

- `schema`: `tau.dag_contract.v1`
- `dag_id`: stable workflow id for receipts and resume
- `goal.goal_id`, `goal.goal_version`, `goal.goal_hash`
- `target`: repo, issue/PR/artifact, or local target scope
- `nodes`: bounded subagent/provider/human steps
- `edges`: allowed route graph
- `entry_node`: first node to dispatch
- `terminal_nodes`: usually `human`, `releaser`, or an explicit blocked node
- `limits`: max attempts, timeouts, and whether resume is allowed
- `required_evidence`: DAG-level proof requirements
- `fail_closed_on`: invariant violations Tau must block

Authoring rules for project subagents:

- Use stable node ids. Node ids are graph addresses; agent names are roles.
- Keep `goal.goal_hash` identical across every node, receipt, and rerun.
- Put retry policy in `nodes[].max_attempts` and `limits.max_total_attempts`,
  not in prose.
- Put allowed transitions in `edges[]`, not in prompt instructions.
- Put proof requirements in `required_evidence`, not only in task summaries.
- Use `executor: local` for local command-spec nodes, including local adapter
  nodes that invoke provider machinery. Use provider-specific executors such as
  `codex`, `opencode`, or `scillm` only when the active Tau runner explicitly
  supports that route. Do not use `executor: provider`; it is not a valid
  `tau.agent_handoff.v1` executor.
- Include `command_spec` for executable local nodes unless the node is an
  explicit virtual/control node such as `start` or `human`. Relative
  `command_spec` paths resolve relative to the DAG contract file; use absolute
  paths or store the DAG contract where the relative paths are valid.
- Include a `human` terminal node unless the workflow has a different explicit
  terminal boundary.
- Include every invariant Tau should block in `fail_closed_on`.
- Do not add new goals, targets, provider branches, mutating branches, or
  command specs through adaptive expansion unless a separate validated
  expansion/branch-lock receipt allows it.

### Simple Example: One Local Creator/Reviewer Loop

Use this shape when a project agent wants a coder/reviewer loop with one bounded
repair attempt.

```yaml
schema: tau.dag_contract.v1
dag_id: tau-issue-47-script-contract
goal:
  goal_id: tau-issue-47
  goal_version: 1
  goal_hash: sha256:0000000000000000000000000000000000000000000000000000000000000047
target:
  repo: grahama1970/tau
  target: issue#47
  allowed_paths:
    - src/tau_coding/persona_dream_dream_packet_agent.py
    - tests/test_persona_dream_dream_packet_agent.py
    - experiments/goal-locked-subagents/agent-command-specs/script-writer/**
    - experiments/goal-locked-subagents/agent-command-specs/script-reviewer/**
entry_node: script-writer
terminal_nodes:
  - human
limits:
  resume: true
  default_timeout_seconds: 240
  max_total_attempts: 4
nodes:
  - id: script-writer
    agent: script-writer
    executor: local
    max_attempts: 2
    command_spec: experiments/goal-locked-subagents/agent-command-specs/script-writer/tau-dispatch-command.json
    required_evidence:
      - script_contract.json
      - timed_transcript.json
      - timed_beats.json
      - entity_environment_script_table.json
    emits:
      - tau.agent_handoff.v1
      - tau.subagent_receipt.v1
  - id: script-reviewer
    agent: script-reviewer
    executor: local
    max_attempts: 2
    command_spec: experiments/goal-locked-subagents/agent-command-specs/script-reviewer/tau-dispatch-command.json
    required_evidence:
      - validate_script_contract.json
      - script-reviewer-verdict.json
    emits:
      - tau.agent_handoff.v1
      - tau.subagent_receipt.v1
  - id: human
    agent: human
    executor: human
edges:
  - from: script-writer
    to: script-reviewer
  - from: script-reviewer
    to: script-writer
    condition: reviewer_status_blocked_and_attempts_remaining
  - from: script-reviewer
    to: human
    condition: reviewer_status_pass_or_attempts_exhausted
required_evidence:
  - command-loop receipt or DAG receipt
  - writer receipt
  - reviewer verdict
  - validator receipt
fail_closed_on:
  - goal_hash_mismatch
  - target_changed
  - unexpected_node
  - unexpected_edge
  - missing_required_evidence
  - max_attempts_exceeded
  - malformed_handoff
```

### Medium Example: Provider-Backed DAG Node

Use this shape when Tau should dispatch one provider-backed node and preserve
provider evidence, cleanup receipts, and resume metadata.

```yaml
schema: tau.dag_contract.v1
dag_id: tau-provider-dag-one-pass
goal:
  goal_id: tau-provider-sanity
  goal_version: 1
  goal_hash: sha256:active-goal
target:
  repo: grahama1970/tau
  target: scratch-provider-proof
entry_node: provider-task
terminal_nodes:
  - human
limits:
  resume: true
  default_timeout_seconds: 600
  max_total_attempts: 2
nodes:
  - id: provider-task
    agent: coder
    executor: local
    command_spec: experiments/goal-locked-subagents/agent-command-specs/provider-task/tau-dispatch-command.json
    provider:
      adapter: generic-provider-dag-node
      allowed_providers:
        - codex
        - opencode
      cleanup_mode: apply
    max_attempts: 1
    required_evidence:
      - runtime_manifest
      - events_jsonl
      - provider_readiness_receipt
      - orchestration_evidence_receipt
      - herdr_cleanup_receipt
    emits:
      - tau.generic_dag_node_receipt.v1
  - id: human
    agent: human
    executor: human
edges:
  - from: provider-task
    to: human
required_evidence:
  - provider_live:true
  - work_order_sha256
  - cleanup.post_verified_absent_count
fail_closed_on:
  - goal_hash_mismatch
  - target_changed
  - invalid_provider_receipt
  - missing_work_order_sha256
  - cleanup_apply_without_absence_proof
```

### Complex Example: Parallel Branches With Reviewer Join

Use this shape when two branches can be locally valid but must be reconciled
before completion.

```yaml
schema: tau.dag_contract.v1
dag_id: tau-feature-with-research-and-code
goal:
  goal_id: tau-feature
  goal_version: 3
  goal_hash: sha256:active-goal
target:
  repo: grahama1970/tau
  target: issue#123
entry_node: start
terminal_nodes:
  - human
limits:
  resume: true
  default_timeout_seconds: 300
  max_total_attempts: 6
nodes:
  - id: start
    agent: goal-guardian
    executor: scheduler
    max_attempts: 1
  - id: researcher
    agent: research-auditor
    executor: local
    max_attempts: 1
    command_spec: experiments/goal-locked-subagents/agent-command-specs/research-auditor/tau-dispatch-command.json
    required_evidence:
      - source_summary
      - citations_or_local_artifacts
  - id: coder
    agent: coder
    executor: local
    max_attempts: 2
    command_spec: experiments/goal-locked-subagents/agent-command-specs/coder/tau-dispatch-command.json
    required_evidence:
      - changed_files
      - focused_tests
  - id: join-review
    agent: reviewer
    executor: local
    max_attempts: 1
    command_spec: experiments/goal-locked-subagents/agent-command-specs/reviewer/tau-dispatch-command.json
    join:
      requires_completed:
        - researcher
        - coder
      reconciles_evidence: true
    required_evidence:
      - review_verdict
      - test_verification
      - unresolved_monitor_alerts:none
  - id: human
    agent: human
    executor: human
edges:
  - from: start
    to: researcher
  - from: start
    to: coder
  - from: researcher
    to: join-review
  - from: coder
    to: join-review
  - from: join-review
    to: human
required_evidence:
  - dag_monitor_receipt
  - reviewer_join_receipt
  - no_unresolved_block_or_reroute_alerts
fail_closed_on:
  - goal_hash_mismatch
  - target_changed
  - unexpected_node
  - unexpected_edge
  - missing_required_join
  - branch_goal_hash_divergence
  - branch_target_divergence
  - unresolved_block_alert
```

### Bad Example: Prose Workflow Masquerading As A DAG

Do not send Tau a loose task object, a chat plan, or a handoff with routing
instructions hidden in prose. This is not a valid Tau DAG because it has no
immutable goal hash, no explicit nodes/edges, no retry limits, no terminal
boundary, no required evidence contract, and no fail-closed invariants.

```yaml
task: fix issue 47
goal: make the script pipeline good
steps:
  - have a writer write the files
  - have a reviewer check it
  - if it looks bad, try again
  - otherwise close the issue
notes: use judgment and add more agents if needed
```

Correct the bad shape by creating a `tau.dag_contract.v1` with:

- `goal.goal_hash` copied from the immutable goal packet;
- one node per bounded role;
- explicit `edges` for retry and terminal paths;
- `max_attempts` and timeout limits;
- exact required evidence names;
- `fail_closed_on` entries for goal drift, target drift, unexpected routes,
  missing evidence, malformed handoffs, timeout, and max-attempt exhaustion.

## Maintainer Handoff Pattern

For agent-skills maintenance, Tau is the lease and handoff boundary between
reporters and repair workers:

1. Reporter skills such as `monitor-skill-health` and `monitor-sparta` create
   normalized findings, manifests, or `$ticket` work items.
2. A maintainer identity such as `agent-skill-maintainer` leases one item at a
   time.
3. Repair and verification are separate bounded subagent handoffs using
   `tau.agent_handoff.v1`.
4. Closure requires deterministic proof attached to the ticket or manifest.

Tau status or watchdog receipts prove the harness state only. They do not prove
that a specific maintenance ticket was repaired unless the ticket proof names
the exercised commands and artifacts.

## Key Artifacts

```text
${HOME}/.local/state/project-watchdog/logs/cron.log
${HOME}/.local/state/project-watchdog/logs/project-watchdog.log
${HOME}/.local/state/project-watchdog/receipts/
${HOME}/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/
${HOME}/workspace/experiments/tau/ui/tau-chat-contract.json
```

Use `agents/tau` for Tau-specific bounded worker turns when a global watchdog or
project agent needs a named subagent identity.

## Project Knowledge

Read `${HOME}/workspace/experiments/tau/PROJECT_KNOWLEDGE.md` before making
claims about current Tau coverage. It records which proof lanes have local
evidence and which remain pending.

When a Tau implementation branch exists, do not stop at a "remaining non-claims"
list if that branch can be deterministically exercised. Continue into the next
local proof command or ask for the exact side-effect target before ending the
turn. For side-effecting proof such as Memory `/upsert`, state the target
collection before executing and preserve both the write receipt and readback
artifact.
