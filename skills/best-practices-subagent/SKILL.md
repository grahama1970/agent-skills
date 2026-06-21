---
name: best-practices-subagent
description: >
  Canonical contract, tool-policy vocabulary, memory/ToM-lite rules, helper
  delegation, receipt requirements, and retry budgets for Scillm/OpenCode/$loop
  subagents and persona workers.
allowed-tools:
  - Bash
  - Read
  - Grep
triggers:
  - subagent best practices
  - create subagent
  - review subagent
  - validate persona
  - tool policy
  - subagent tools
  - theory of mind tags
  - tom-lite
  - inner loop retries
metadata:
  short-description: Standard subagent contracts, tool policy, memory policy, ToM-lite, and retries
  version: "0.1.0"
provides:
  - subagent-schema
  - tool-policy-contract
  - memory-routing-contract
  - persona-tom-lite-contract
  - helper-delegation-contract
  - retry-policy-contract
  - persona-contract-validation
composes:
  - memory
  - agents-registry
  - skills-ci
  - loop
  - scillm
complies:
  - best-practices-skills
  - best-practices-subagent
taxonomy:
  - agents
  - orchestration
  - safety
  - composition
  - memory
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CREATING, REVIEWING, OR ROUTING A SUBAGENT.

# Best Practices: Subagents

This skill defines the canonical contract for role-bounded subagents. It is a
contract skill, not just a style guide. A subagent contract must declare:

1. what the subagent owns,
2. what it does not own,
3. which tools and skills it may call,
4. which memory endpoints, profiles, and collections it may use,
5. whether it is persona-attached and ToM-lite aware,
6. which helper skills it may request,
7. what artifacts and receipts prove completion,
8. how many retries are allowed and when to stop.

Retry budgets must be finite. A subagent must not run an unbounded `while true`
loop, silently increase its own retry budget, or continue searching/repairing
without a named verifier defect or coverage gap. Unless a skill-specific
contract says otherwise, bounded iterative work defaults to **3 attempts**.
Only the human or the outer project agent may override that default, and the
override must include an explicit maximum attempt count, a reason, and an
updated stop condition.

## Architecture Boundary

Use the strict harness boundary:

```text
Scillm / Project Agent = outer project DAG harness
$loop                  = inner artifact-completion harness for one DAG node
Subagent               = role-bounded worker/reviewer/persona within a node
Memory                 = context, routing, ToM-lite, provenance, and post-proof learning
```

If a task spans multiple independent artifacts, dependencies, or promotion
choices, it belongs to Scillm/project-agent. If a task is trying to finish one
artifact with inspect -> produce -> verify -> repair, it may belong to `$loop`.

Subagents do role-bounded work. They do not decide global project completion.

## Required Contract Sections

Every subagent SHOULD declare these sections:

```yaml
schema: oc_subagent.persona.v1
id: example-subagent
kind: persona | worker | reviewer | researcher | assurance | curator | monitor
display_name: Example Subagent

role: >
  What this subagent owns.

does_not_own:
  - global_project_completion
  - final_merge_decision
  - memory_promotion_without_receipt

dag_spec:
  schema: subagent_dag.v1
  mode: single_node # single_node | bounded_dag | bounded_loop
  description: >
    The exact DAG/run-spec this subagent expects before doing work. Simple
    subagents use a one-node DAG. Autonomous generation or retry workers use a
    multi-node DAG with explicit retry, mutation, and stop conditions.
  inputs_required: []
  nodes:
    - id: perform_role
      kind: read_only_review
      receipts: [request.json, response.json]
      stop_conditions: [receipt_written, blocked_with_reason]
  edges: []
  receipt_policy:
    per_node_receipt_required: true
    final_receipt_required: true
  start_gate:
    require_dag_spec_before_work: true
    reject_prose_only_work_orders: true

primary_skills:
  - memory
  - best-practices-subagent

tool_policy: {}
memory_policy: {}
persona_memory_policy: {}      # required when persona_attached=true
delegated_access_skills: []
turn_contract: {}
status_reporting: {}
help_policy: {}
retry_policy: {}
output_contract: {}
artifact_contract: {}
proof_tasks: []
```

Use `does_not_own`, `forbidden_actions`, `forbidden_behavior`,
`tool_policy.denied`, and `memory_policy.denied_endpoints`. Do not introduce vague
fields such as `cannot:` unless the schema is intentionally extended.

## DAG / Run-Spec Contract

Every subagent requires a `dag_spec` before doing work. This is a consistency
rule, not a requirement that every subagent run a complex workflow.

```text
Simple reviewer / answerer / researcher   -> single-node DAG
Artifact worker                           -> bounded DAG
Autonomous generator / classifier loop    -> bounded loop DAG
```

The DAG contract prevents role drift by making the expected inputs, node order,
receipts, retry budgets, and stop conditions explicit before tools or APIs run.
If a caller supplies only prose for a non-trivial task, the subagent should
return `BLOCKED` or ask the project agent for a concrete DAG/run-spec instead of
inferring its own workflow.

Minimum `dag_spec`:

```yaml
dag_spec:
  schema: subagent_dag.v1
  mode: single_node # single_node | bounded_dag | bounded_loop
  description: "One-sentence bounded job."
  inputs_required:
    - request.json
  nodes:
    - id: perform_role
      kind: read_only_review
      receipts:
        - response.json
      stop_conditions:
        - receipt_written
        - blocked_with_reason
  edges: []
  receipt_policy:
    per_node_receipt_required: true
    final_receipt_required: true
  start_gate:
    require_dag_spec_before_work: true
    reject_prose_only_work_orders: true
```

For any DAG node that spends external API calls, performs LLM prompting, or
generates paid artifacts, include a preflight packet before the spend node runs:

```yaml
prompt_preflight:
  required: true
  packet_fields:
    - full_prompt_payload
    - source_fixture
    - expected_result
    - response_schema
    - validation_command
    - rejection_criteria
    - batch_or_cost_context
```

For autonomous generation/classification loops, the DAG must also declare:

```yaml
loop_policy:
  max_attempts: 20
  max_cost_usd: 2.00
  mutation_policy:
    allowed_mutations:
      - prompt_template
      - provider_parameters
    denied_mutations:
      - target_label
      - persona_voice_id_without_approval
  classifier_gate:
    expected_labels: []
    reject_labels: []
    weak_classification_action: abstain
  stop_conditions:
    - target_accept_count_reached
    - max_attempts_reached
    - max_cost_reached
    - same_failure_repeated_twice
    - human_interview_required
```

Loop workers may ask for `$interview` only after the DAG's deterministic gates
are exhausted or the classifier abstains with no safe mutation remaining.

## Tool Policy

Do not let `has bash` imply `has every skill`. Bash is transport; skills are
capabilities. Prefer a policy-gated `skill.call` dispatcher.

```yaml
tool_policy:
  allowed:
    - memory.intent
    - memory.recall
    - memory.answer
    - memory.clarify
    - memory.deflect
    - read
    - grep
    - skill.call

  denied:
    - memory.store
    - memory.upsert
    - memory.query_raw
    - broad_bash
    - git_push
    - auto_merge
    - direct_arango
    - direct_qdrant

  bash:
    tier: bash.none # bash.none | bash.readonly | bash.check | bash.scoped_mutate | bash.system
    allowed_commands: []
    denied_commands:
      - rm -rf
      - git push
      - docker compose down
      - systemctl
      - crontab

  filesystem:
    read:
      allowed_globs: []
      denied_globs: []
    write:
      allowed_globs: []
      denied_globs: []

  skill_calls:
    mode: dispatcher_only # none | dispatcher_only | direct
    allowed_skills: {}
    denied_skills: []
```

### Bash Tiers

```text
bash.none          No shell.
bash.readonly      pwd, ls, rg, cat, git status, git diff.
bash.check         tests, validators, linters, receipt checks.
bash.scoped_mutate formatters/codegen/repair commands restricted by allowed_globs.
bash.system        docker/services/cron/install/network mutation. Project-agent only.
```

## Memory Policy

Most subagents need scoped memory recall. Most subagents must not write memory.

```yaml
memory_policy:
  allowed_endpoints:
    - intent
    - recall
    - answer
    - clarify
    - deflect

  denied_endpoints:
    - store
    - upsert
    - delete
    - raw_query

  allowed_collections: []
  preferred_collections: []
  denied_collections: []
  allowed_recall_profiles: []

  write_policy:
    default: denied
    exceptions: []

  response_modes:
    answer:
      use_when:
        - memory_confidence_is_sufficient
        - source_or_context_is_unambiguous
        - subagent_has_answer_authority
    clarify:
      use_when:
        - target_or_scope_missing
        - multiple_memory_items_conflict_or_compete
        - memory_confidence_low_or_should_scan_true
    deflect:
      use_when:
        - request_belongs_to_another_owner
        - request_violates_subagent_role
        - tool_or_collection_permission_denied
```

### Endpoint Roles

```text
memory.intent   Determine route/type/profile.
memory.recall   Retrieve scoped context and source anchors.
memory.answer   Produce memory-grounded user-facing answer when authority exists.
memory.clarify  Ask one useful question or return structured ambiguity.
memory.deflect  Route outside-scope work to the owning persona/skill.
memory.store    Project-agent or memory-curator only after proof.
memory.upsert   Project-agent or memory-curator only after proof.
```

## Persona Memory and ToM-Lite Policy

Persona-attached subagents must use ToM-lite. ToM-lite is a small, stable
retrieval annotation vocabulary. It is not a claim that the model possesses or
correctly infers human mental states.

Use ToM-lite to make persona memory traversable and rankable without confusing
subagents or inviting hallucinated graph links.

```yaml
persona_memory_policy:
  required_when_persona_attached: true
  persona_id_field: active_domain_persona

  allowed_collections:
    - personas
    - persona_memory
    - persona_memory_edges
    - persona_states
    - user_agent_relationships
    - user_lessons
    - tom_edges

  tom_lite:
    controlled_vocabulary: true
    freeform_tom_tags: denied
    max_tom_kinds_per_memory: 2
    max_affect_labels_per_memory: 1
    require_source_anchor: true

    tom_kind:
      - emotion
      - belief
      - goal
      - preference
      - boundary
      - relationship
      - knowledge_gap
      - unresolved_thread

    affect:
      - angry
      - sad
      - anxious
      - confused
      - happy
      - neutral

    intensity:
      - low
      - medium
      - high
      - extreme

  graph_policy:
    graph_connections_remain: true
    traversal_owner: memory_service
    direct_graph_access: denied
    direct_graph_edge_creation_by_subagent: denied
    require_source_paths: true
    max_hops_default: 2
    max_hops_without_project_agent_approval: 3

  intensity_policy:
    use_for:
      - retrieval_reranking
      - graph_traversal_weight
      - salience
      - response_tone
      - continuity_priority
    must_not_use_for:
      - truth_claims
      - evidence_sufficiency
      - compliance_approval
      - permission_to_act

  classifier_policy:
    optional: true
    output_is_advisory: true
    weak_classification_action: abstain
    local_llm_or_classifier_may_suggest: true
    durable_memory_write_requires_curator_or_project_agent: true
```

### ToM-Lite Semantics

| Field | Values | Purpose |
|---|---|---|
| `tom_kind` | emotion, belief, goal, preference, boundary, relationship, knowledge_gap, unresolved_thread | What type of persona/user memory this is. |
| `affect` | angry, sad, anxious, confused, happy, neutral | Simple emotional label for tone/ranking. |
| `intensity` | low, medium, high, extreme | Salience/ranking weight, not truth. |

Examples:

```yaml
tom_kind: preference
affect: neutral
intensity: high
source_quote: "simpler ... don't want to overly hallucinate graph connections"
```

```yaml
tom_kind: boundary
affect: angry
intensity: high
source_quote: "do not create evidence cases directly"
```

```yaml
tom_kind: knowledge_gap
affect: confused
intensity: medium
source_quote: "what does this YAML field mean?"
```

## ToM-Lite Annotation Pipeline

A small local LLM or encoder classifier may annotate persona-memory records, but
it must not directly create trusted graph edges.

Recommended overnight pipeline:

```text
persona_memory / journals / session summaries
  -> local LoRA/QLoRA ToM-lite annotator or classifier
  -> controlled labels + source_quote + candidate edges
  -> validator
  -> staging collections
  -> promote high-confidence source-grounded tags
  -> quarantine ambiguous or weak edge candidates
```

Promotion policy:

```yaml
tom_lite_promotion_policy:
  promote_tags_when:
    tom_kind_confidence_min: 0.80
    affect_confidence_min: 0.70
    intensity_confidence_min: 0.65
    source_quote_required: true

  promote_edges_when:
    edge_confidence_min: 0.85
    source_quote_required: true
    both_nodes_must_exist: true
    deterministic_edge_key_required: true
    max_edges_per_record: 2

  quarantine_when:
    - confidence_below_threshold
    - source_quote_missing
    - unknown_target_node
    - more_than_two_edge_candidates
    - freeform_tom_label
    - sensitive_boundary_or_safety_record
```

## Helper Delegation

Subagents may request helper work only through a bounded helper protocol.

```yaml
delegated_access_skills:
  - skill: create-evidence-case
    owner: assurance
    access_mode: helper_request_and_artifact_consumption
    allowed_use: >
      Request and consume a CAE/QRA artifact, evidence_case, entity_context, or
      cae_tree. Do not assign verdict, approve, promote, or declare readiness
      unless this subagent is the owning Assurance worker.
    required_request_form: "$ask assurance to build evidence case with create-evidence-case@v1 on <artifact>"
    forbidden_actions:
      - create_evidence_case_directly
      - assign_evidence_case_verdict
      - approve_evidence_case
      - promote_evidence_case
      - declare_qra_readiness
```

Helper calls should require target artifacts, terminal events, and receipts.

## Retry Policy

Retry budgets are part of the safety contract. Keep the inner loop boring.

Distinguish these retry types:

```text
tool_retry        Retry a transient tool failure.
helper_retry      Retry a delegated helper request.
inner_loop_retry  Repair attempt inside $loop for one artifact.
outer_dag_retry   Re-run/recompile a Scillm node after consuming receipt.
```

Default retry budgets:

| Retry type | Default | Hard max without project-agent approval | Owner |
|---|---:|---:|---|
| Tool transient retry | 1 | 2 | Subagent/tool dispatcher |
| Memory recall retry | 0-1 | 1 | Subagent |
| Memory clarify retry | 0 | 1 | Outer agent after user context |
| Helper request retry | 1 | 2 | Requesting subagent |
| Bounded iterative research/review | 3 total | 4 total | Research/reviewer subagent under project-agent control |
| Inner `$loop` attempts | 3 total | 4 total | `$loop` node |
| Outer Scillm node retry | 0-1 | 2 | Project agent |
| Persona response schema repair | 1 | 1 | Persona subagent |
| Reviewer pass | 1 | 1 | Reviewer |

Retry only when the next attempt has new information: a concrete verifier defect,
actionable test output, a narrowed memory query, corrected user input, or a
transient infrastructure error. Do not retry for missing requirements,
insufficient evidence, denied permissions, or repeated same failures.

### Bounded Iterative Retry Contract

Use this contract for research, review, search, extraction, or evaluation loops
that are not `$loop` code-repair nodes but still repeat until a rubric passes:

```yaml
retry_policy:
  bounded_iterative:
    applies_to:
      - research_loop
      - review_loop
      - search_and_evaluate_loop
      - extraction_evaluation_loop
    default_max_attempts: 3
    absolute_max_attempts: 4

    override_allowed_by:
      - human
      - project_agent
    override_requires:
      - explicit_max_attempts
      - reason
      - updated_stop_condition
    subagent_self_override: denied
    unlimited_retries: denied

    retry_requires_one_of:
      - evaluator_found_named_coverage_gap
      - verifier_found_named_defect
      - required_visual_or_source_evidence_missing
      - narrowed_query_or_scope_from_prior_attempt
      - transient_tool_or_api_failure

    stop_immediately_on:
      - pass
      - missing_or_ambiguous_requirements
      - denied_tool_or_collection_required
      - source_evidence_missing_for_required_claim
      - same_gap_repeated_twice
      - max_attempts_reached
      - no_final_receipt
```

For research loops, the final receipt must state attempts used, pass/fail
coverage buckets, amended queries or scope changes, sources used, remaining
gaps, and the next recommended owner. A subagent may recommend more research
only by naming the exact failed bucket and the amended query/scope that would
make the next attempt different.

### Inner Loop Retry Contract

```yaml
retry_policy:
  inner_loop:
    applies_to: one_artifact_transaction
    default_max_attempts: 3
    absolute_max_attempts: 4
    explorer_runs_once: true
    reviewer_must_be_read_only: true

    retry_requires_one_of:
      - deterministic_check_failure_with_actionable_output
      - verifier_needs_changes_with_specific_issue
      - changed_files_scope_violation_that_can_be_repaired
      - artifact_schema_violation_with_clear_schema

    stop_immediately_on:
      - missing_or_ambiguous_requirements
      - denied_tool_or_collection_required
      - helper_receipt_missing
      - source_evidence_missing
      - memory_grounding_failed_for_required_persona_or_domain
      - same_failure_repeated_twice
      - out_of_scope_file_change
      - reviewer_attempted_write
      - no_final_receipt
```

Outcomes:

```text
PASS          Outer DAG may consume receipt.
NEEDS_CHANGES Outer DAG may recompile or retry node if budget remains.
BLOCKED       Outer DAG must clarify, delegate, or repair infrastructure.
```

## Output and Artifact Contracts

Every subagent should emit machine-readable result fields. User-facing prose is
allowed only when the subagent is explicitly an answer surface.

### Project-Agent Status Reporting

Every subagent must report status back to the project agent. No exceptions. The
project agent owns the outer DAG and timeout diagnosis; the subagent owns
execution receipts. A project agent must not be forced to infer liveness or
progress from files appearing on disk.

Declare `status_reporting` in every subagent contract:

```yaml
status_reporting:
  required: true
  recipient: project_agent
  cadence:
    - after_start
    - after_each_phase
    - before_tool_or_api_call
    - after_tool_or_api_call
    - on_deterministic_bug_found
    - after_repair_attempt
    - before_blocked_or_final_response
  stream_modes:
    - sse_json_if_runtime_supports
    - jsonl_event_stream
    - phase_receipt_json
    - final_response_json
  event_fields:
    - subagent_run_id
    - phase
    - current_artifact
    - command_or_api
    - evidence
    - bug_or_blocker
    - next_step
    - stop_condition
  timeout_diagnostics:
    heartbeat_interval_seconds: 30
    stale_after_seconds: 120
    include_last_started_command: true
    include_last_completed_command: true
    include_current_artifact_path: true
```

When a runtime supports Server-Sent Events, prefer an SSE stream of JSON status
events so the project agent can distinguish slow work from a timed-out or stuck
subagent. If SSE is unavailable, write append-only JSONL events and phase
receipt JSON files. The final response is not a substitute for status streaming.

Each status event must include these fields:

```json
{
  "subagent_run_id": "string",
  "phase": "string",
  "current_artifact": "/absolute/path/or/url-or-null",
  "command_or_api": "exact command, tool, endpoint, or null",
  "evidence": {
    "counts": {},
    "paths": [],
    "status_code": null,
    "duration_seconds": null
  },
  "bug_or_blocker": null,
  "next_step": "concrete next action",
  "stop_condition": "what ends the current phase"
}
```

The project-specific skill may add phase names and domain fields, but it must
not remove these fields or weaken the recipient/cadence requirement.

```yaml
output_contract:
  format: json_only_unless_user_answer_requested
  success_fields:
    - subagent_run_id
    - status
    - response_mode
    - memory_recall_attempted
    - memory_query
    - memory_collections
    - memory_confidence
    - memory_should_scan
    - helper_calls
    - artifacts
    - verified
  error_fields:
    - subagent_run_id
    - status
    - error
    - gaps
    - verified

artifact_contract:
  required_per_turn:
    - request.json
    - response.json
  recommended_per_turn:
    - memory-recall.json
    - helper-receipt.json
    - verification.json
```

## Lint Rules

A contract linter should fail when:

- required sections are missing,
- `dag_spec` is missing, has no nodes, has a node without receipts, or has a
  node without stop conditions,
- `dag_spec.start_gate.require_dag_spec_before_work` is not true,
- autonomous loop DAGs lack max attempts, mutation policy, classifier gate, and
  explicit stop conditions,
- generation/model/API-spend DAG nodes lack a prompt/API preflight packet with
  expected output, schema, validation, and rejection criteria,
- `cannot:` is used instead of approved boundary fields,
- Bash is present without a bash tier,
- `status_reporting` is missing, not required, lacks project-agent recipient,
  lacks timeout diagnostics, or omits required status event fields,
- memory access has no `allowed_endpoints`,
- memory recall has no `allowed_collections`, `preferred_collections`, or `allowed_recall_profiles`,
- persona-attached subagents lack `persona_memory_policy`,
- free-form ToM tags are allowed,
- subagents can directly create graph edges,
- helper access lacks owner/access_mode/forbidden_actions,
- helper access does not require receipts,
- memory writes are allowed without verified receipt requirements,
- reviewer has write access,
- retry loops are unbounded, allow subagent self-overrides, or omit default
  max attempts,
- bounded iterative retry defaults above 3 without explicit human/project-agent
  override policy,
- bounded iterative retry absolute max exceeds 4 without explicit exception,
- inner loop max attempts exceeds 4 without explicit exception,
- direct Arango/Qdrant/raw AQL access is allowed for normal subagents.

## Research Notes

ToM-lite is deliberately modest. Current ToM-in-LLMs literature warns against
claiming that a model “has ToM” merely because it matches behavior on benchmark
items. Treat ToM tags as operational, source-grounded retrieval annotations.
Recent GraphRAG work supports preserving explicit graph paths for multi-hop
retrieval instead of relying only on nearest-neighbor snippets. LoRA/QLoRA local
models can help annotate records overnight, but all durable tags and graph edges
must pass schema, source, confidence, and promotion checks.

See `docs/RESEARCH_NOTES.md` for citations and design consequences.

## Commands

```bash
# Lint one contract
./run.sh lint examples/cyber-analyst-subagent.yaml

# Lint all examples
./run.sh lint examples/*.yaml

# Print schema path
./run.sh schema
```
