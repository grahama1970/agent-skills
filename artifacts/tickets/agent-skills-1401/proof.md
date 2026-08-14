# Proof For agent-skills#1401

Ticket: https://github.com/grahama1970/agent-skills/issues/1401

Closure bar, quoted from the ticket:

> Closure requires cross-mode deterministic projection fixtures plus at least
> one live non-mocked Tau run whose CLI JSON and timeline read back the same
> authoritative node and settlement states; documentation or a mode-specific
> status adapter alone is not closure proof.

Both halves are below.

## Half 1 — cross-mode deterministic fixtures

Ten committed fixtures under `skills/ask/tests/fixtures/run_projection/`:
one_handler, roundtable_partial, compete, creator_reviewer, argue, deep_review,
team_plan, natural_ask_dag, mixed_targets, local_non_agentic_blocked.

Shapes are taken from the 1695-run live corpus, not invented. That mattered:
real DAG nodes carry `agent: "handler-webgpt"` with no separate `handler`
field, and matching on a prefix had mislabelled all 1744 browser seats in the
corpus as plain models.

`build_fixtures.py` regenerates them byte-identically (asserted by the eval
`run-projection-fixtures-regenerate-byte-identically`).

Each fixture encodes a hard case rather than a happy path:

- **roundtable_partial** — a settled seat, a rate-limited seat, a seat that
  produced nothing at all, and a degraded join. Proof 5:

```
roundtable_partial  DEGRADED  (execution-status.json)
  nodes: 4 | settled: 1 | admitted: 1
    handler-webgpt       SETTLED       browser_seat
    handler-webclaude    ACKNOWLEDGED  browser_seat   browser_provider_rate_limited
    handler-webkimi      COMPILED      browser_seat   node never created a worker directory
    join                 ACKNOWLEDGED  join           degraded_join
```

- **natural_ask_dag** — confident provider output that nothing admitted.
  Proofs 4 and 9: stage is `CANDIDATE`, `admitted_node_count` is 0, and the
  run does not project `PASS`.
- **local_non_agentic_blocked** — request, goal, plan and failure detail all
  survive though provider execution never began (proof 6).

## Half 2 — live non-mocked Tau run

```bash
cd skills/ask
./run.sh tau-dag "Reply with exactly the word PROJECTION and nothing else." \
  --repo local/agent-skills --target ticket-1401-live-proof \
  --immutable-goal "Prove ask.run_projection.v1 reads back the same node and settlement states as the live run" \
  --handler gpt-5.5-high --topology sequential --execute --json
```

```
execution status: PASS | ok: True | live: True | mocked: False | provider_live: True
run_dir: /mnt/storage12tb/skills/ask/outputs/.ask_artifacts/tau-dag-runs/ask-tau-reply-with-exactly-the-word-proj-328e8e7ffed3
```

Read back against the authoritative receipts:

```
lifecycle: PASS | terminal: True | goal_hash: sha256:69db71222a08713fb

  node                     receipt.ok  proj.ok  stage    timeline.settled  agree
  handler-gpt-5-5-high     True        True     SETTLED  True              True
  join                     True        True     SETTLED  True              True

ALL THREE AGREE: True
```

The comparison is against `node-receipt.json` -- the authoritative artifact --
not against the projection's own output, so this is a read-back rather than a
self-report.

## Required proofs

1. Cross-mode fixtures — 10 modes, committed, byte-identical regeneration.
2. Compiled-but-never-started node appears — `test_a_compiled_node_that_never_ran_still_appears`.
3. Dispatched with no receipt is typed — `test_a_dispatched_node_with_no_receipt_is_typed_not_dropped`.
4. Transport success without admitted evidence is not success — `test_a_favorable_provider_answer_cannot_manufacture_pass`.
5. Partial roundtable enumerates every seat and cause — `test_a_partial_roundtable_names_every_seat_and_its_cause`.
6. Blocked preflight retains request/goal/plan/failure — `test_a_blocked_preflight_keeps_request_goal_and_failure`.
7. Byte-stable canonical JSON; the payload carries no observation timestamp at
   all, so the documented-exclusion branch does not apply.
8. Human text, JSON, and timeline consume one projection —
   `render_text()` and `to_timeline()` are pure functions of it and
   `status.py` calls `render_text`; `test_all_three_consumers_agree`
   covers all ten modes.
9. Negative tests — `test_the_timeline_never_reports_settlement_the_projection_denies`.
10. Backward compatible — `--projection` is additive; existing `status`
    behaviour is unchanged.

## Scale evidence

1695 real run directories projected, zero exceptions, deterministic across
repeat projections. Surfaces 1290 nodes that never created a worker directory
and 37 that left output with no receipt — all previously invisible.

## Not proven

The legacy `status --run` path still reads a different artifact family and has
its own shape. It is backward compatible and untouched, but it is not yet fed
by this projection; unifying it is follow-on work.

A projection is not a claim that any task was performed correctly — only a
faithful read of what the artifacts assert.

Commits: c17dd315fd, 5d4df9d471
