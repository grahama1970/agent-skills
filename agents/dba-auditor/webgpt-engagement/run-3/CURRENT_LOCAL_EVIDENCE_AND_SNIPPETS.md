# Current Local Evidence And Snippets

## Routing Correction

The project agent previously submitted the R3 bundle through
`skills/ask/run.sh webgpt-review`, which is a routing failure for
`$create-architecture`. This round must use `$ask webgpt` creation framing:
clarifying questions first if needed, then a finished solution zip.

## Current Local Attempt

A local project-agent patch attempt exists in:

- `memory/scripts/validation/monitor_sparta.py`

Treat it only as evidence of one attempted direction. It is not a WebGPT
solution zip and has no live mutating `repair-cycle` proof.

## Non-Mutating Proof Already Run

- `python -m py_compile scripts/validation/monitor_sparta.py` -> exit 0
- `uv run pytest /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py` -> 19 passed

Evidence honesty:

- mocked: yes, Dewey tests use a fake monitor
- live: no, no mutating `SPARTA_MONITOR_MUTATION_ENABLED=1 repair-cycle` run was performed

## Relevant Current Repair-Cycle Shape

The target function is `repair_cycle()` in
`memory/scripts/validation/monitor_sparta.py`.

The repair-cycle currently:

1. Runs baseline `health --json`.
2. Optionally applies SPARTA repair manifests.
3. Runs `scripts/migrate_arango_embeddings_to_qdrant.py` for
   `embedding_gaps` / `inline_embedding_policy`.
4. Runs `health --fix`, then a fresh `health --json`.
5. Starts `create_qras_backfill` for QRA coverage dimensions.
6. Waits for monitor workers.
7. Runs final `health --json`.

R3 must make the JSON output diagnose why the cycle does or does not improve
the health dimensions:

- every step should expose `eligible_count`, `changed_count`, `skip_reason`
  where applicable
- embed output should explain `processed=200 synced=200 dropped=200` while
  health still reports 170 missing
- health fix should include per-dimension before/after status and affected count
- worker wait should report worker start, still-running/completed state, and
  enough state/log paths to diagnose delayed QRA workers
- QRA lane contract must be explicit and aligned with Dewey's
  `UNFIXABLE_DIMENSIONS`

## Required WebGPT Output

If material ambiguity remains, return only numbered clarifying questions.

If no material ambiguity remains, return one solution zip named:

`sparta-dewey-r3-diagnostics-solution.zip`

The zip must contain:

- `MANIFEST.json`
- `ARCHITECTURE.md`
- `prompt_improvements.md`
- finished repo-relative source/test files needed for the R3 slice
- exact commands to sanity-check and port the solution

Do not return PASS/NEEDS_CHANGES/BLOCKED. Do not return prose-only files.

## Completed R3 Result

WebGPT completed the requested creation flow in Sparta Explorer tab `837356331`
at:

`https://chatgpt.com/g/g-p-6a22b674b76881918809ceac4396a409-sparta-explorer/c/6a3c2db3-a390-83ea-bec5-82d8f295ce14`

Downloaded solution zip:

- `webgpt-engagement/run-7/sparta-dewey-r3-diagnostics-solution.zip`
- SHA256: `3d89ec00a9fb361abe459aaea9e8387ae934870cd2bf6d53a6cc3d1474fb8b31`

Ported files:

- `memory/scripts/validation/monitor_sparta_r3_diagnostics.py`
- `memory/scripts/validation/monitor_sparta.py`
- `agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py`
- `/home/graham/workspace/experiments/fixtures/dewey_r3/*.json`

Verification:

- mocked: yes, isolated helper tests and existing Dewey tests include fixture/mock coverage.
- live: yes, real `health --json` and guarded `repair-cycle` ran against the local stack.

Commands/results:

- `python -m py_compile scripts/validation/monitor_sparta.py scripts/validation/monitor_sparta_r3_diagnostics.py` -> PASS.
- `uv run pytest -q agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py` -> 5 passed.
- `uv run pytest -q agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py` -> 19 passed.
- `uv run python scripts/validation/monitor_sparta.py health --json` -> 24/29 PASS.
- `SPARTA_MONITOR_MUTATION_ENABLED=1 uv run python scripts/validation/monitor_sparta.py repair-cycle --json --wait --wait-timeout-s 300 --embed-batch-limit 200` -> exit 1 because failures remain; R3 receipt shape assertions PASS.

Live R3 receipt facts:

- Step ids: `sparta_qdrant_embed_batch`, `monitor_health_fix`, `qra_coverage_operator_lane`.
- No `create_qras_backfill` step was emitted.
- `worker_wait.status` is `no_workers`.
- `r3_diagnostics.contract` is `Option B: QRA coverage is operator/review-gated and remains unfixable by Dewey`.
- Remaining failures: `embedding_gaps`, `description_completeness`, `qra_coverage_per_control`, `inline_embedding_policy`, `sparta_explorer_page_purpose`.
