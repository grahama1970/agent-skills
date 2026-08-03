# Dreamer Self-Improvement Loop

This is the steering contract for Dreamer after every substantial
Persona-Dream run or repair session. It converts orchestration failures into
deterministic next-run behavior.

## Loop Boundary

Dreamer is the Persona-Dream orchestrator. Its self-improvement loop may update
or propose updates to local Dreamer knowledge and candidate memory records, but
it must not mutate canonical memory, submit live provider jobs, delete
superseded evidence, or mark provider readiness without gate receipts.

## Inputs

Each substantial Dreamer run must produce a receipt JSON or report JSON with
these fields:

- `active_request`
- `memory_recall_summary`
- `project_knowledge_summary`
- `upstream_revision_summary`
- `stale_artifact_summary`
- `phase_receipts_summary`
- `panel_work_order_summary`
- `panel_repair_loop_summary`
- `provider_boundary_summary`
- `completed_task_assessment`
- `what_i_learned`
- `changed_or_recommended_agent_contract_rules`
- `project_knowledge_update_candidates`
- `memory_upsert_candidates`
- `next_run_checklist_delta`
- `external_research_used_or_not_needed`

## Deterministic Gate

Until a dedicated verifier script exists, the project agent must verify that
the receipt path exists, parses as JSON, and contains every required field
above before claiming a Dreamer handoff is consumable.

Target verifier shape:

```bash
python agents/dreamer/scripts/verify_self_improvement.py \
  --receipt <dreamer-run-receipt.json> \
  --print-json
```

The verifier should return:

- `PASS` when every required section is present and non-empty.
- `NEEDS_CHANGES` when the receipt is parseable but missing loop fields.
- `BLOCKED` when the receipt cannot be parsed or the target is missing.

## Steering Steps

1. Preflight: verify the receipt path exists and parses as JSON.
2. Measure: check every required self-improvement field.
3. Gate: fail if any required field is absent or empty.
4. Adjust: if the gate fails, the next Dreamer response must add the missing
   fields before any readiness or handoff claim.
5. Persist: update or propose updates to:
   - `agents/dreamer/PROJECT_KNOWLEDGE.md`
   - `agents/dreamer/memory-upsert-candidates.jsonl`
6. Handoff: if a finding requires repository repair, prepare an exact target,
   owner, default repair action, rollback artifact, verification command, and
   non-claims.

## Per-Phase Blocker Resolution Contract

Dreamer must not treat phase blockers as report content. For every phase in the
Persona-Dream DAG, Dreamer runs a contract loop:

1. Preflight the phase inputs, source hashes, stale-artifact state, and required
   tools.
2. Execute or delegate the phase work order.
3. Measure emitted artifacts with deterministic checks and owning reviewers.
4. If blockers remain and repair is write-capable, compile one scoped `$loop`
   node with allowed globs, required checks, and max attempts.
5. Consume `.loop/runs/<run_id>/final-receipt.json`; do not use chat prose as
   proof.
6. Repeat only through the coded loop budget. Do not hand-simulate retries.
7. Advance only when the phase contract is `PASS` and
   `unresolved_blockers == 0`.
8. If the loop exhausts or an external dependency blocks repair, stop the run at
   that phase and record exact unresolved findings, attempted strategies,
   affected artifact paths, and rollback or supersession state.

This applies to idea, dream substrate, story, producer, references, script,
voice, panels, gate, and provider dry-run. Panel repair is the strictest case:
all image and text blockers must be resolved before provider readiness can be
claimed.

## Stop Conditions

- `PASS`: receipt can be consumed by the project agent.
- `NEEDS_CHANGES`: project agent must repair the receipt or rerun Dreamer with
  the missing sections named by the verifier.
- `BLOCKED`: missing receipt, invalid JSON, denied permission, source evidence
  unavailable, or provider boundary requires human authorization.

## Non-Claims

Passing this loop proves only that Dreamer emitted the required
self-improvement steering fields. It does not prove panel correctness, provider
readiness, phase closure, Kling submission authorization, or canonical memory
upsert.
