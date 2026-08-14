# Proof For agent-skills#1402

Ticket: https://github.com/grahama1970/agent-skills/issues/1402

Closure bar, quoted:

> Closure requires live portable watch/control/resume evidence with exact Tau
> readback and no duplicate accepted work; a shell wrapper around process
> signals or a TUI-only demo is not closure proof.

## The design constraint

Tau owns settlement. It exposes `workflow-resume` and `workflow-repair`; it
exposes **no steer or cancel seam**. Wrapping process signals and calling that
control is exactly what the closure bar rules out, so unsupported operations
report `unsupported` truthfully and mutate nothing.

## Live canary (required proof 10)

`./scripts/runs_control_live_e2e.sh` — real multi-node Ask/Tau run, non-mocked:

```
== 1. start a live multi-node run ==
run_dir=.../ask-tau-reply-with-exactly-the-word-cana-36107dc004ee

== 2. observe through runs watch (jsonl) ==
{"event":"node_stage_changed","node_id":"handler-gpt-5-5-high","to":"SETTLED","evidence_admitted":true}
{"event":"node_stage_changed","node_id":"join","to":"SETTLED","evidence_admitted":true}
{"event":"run_settled","lifecycle":"PASS"}

== 3. steer, recording the truthful outcome ==
   steer outcome=rejected reason=node_already_terminal delivered=False

== 4. guidance that would widen scope is refused before delivery ==
   widening outcome=rejected violations=['ignore the goal', 'escalate']

== 5. the run settled; resume must duplicate nothing ==
   already_accepted=['handler-gpt-5-5-high', 'join']
   would_rerun=[]
   no accepted node is scheduled for rerun

PASS
```

## The two separations that carry the honesty

**A cancellation request is not a cancellation** (proof 4). The request is
recorded with `acknowledged: false` and the explanation says plainly that the
run must not be read as CANCELLED. Verified live: after a cancel request the
projection still reads `PLANNED`.

```
cancel outcome=requested acknowledged=False reason=no_tau_cancel_seam
show   lifecycle=PLANNED  (not CANCELLED)
```

**Resume never reruns accepted work** (proof 7). The plan is computed from
`node-receipt.json` evidence admission, not terminal scrollback (proof 8).
`test_resume_never_reruns_accepted_work` asserts the accepted creator appears
in `already_accepted` and never in `would_rerun`.

## Required proofs

1. CLI tests across list/latest/show/watch/steer/cancel/resume in human, JSON
   and JSONL — 21 tests.
2. `show`/`watch` consume #1401 — `test_watch_events_are_derived_from_the_projection`
   asserts every event's stage equals the projection's.
3. Ctrl-C detaches without cancelling — `watch` performs no writes
   (`test_watch_has_no_side_effects`), and the CLI prints "the run is still
   active" on interrupt.
4. Cancel request vs acknowledgement — above.
5/6. Steering a settled node, an unknown node, or a live node all fail honestly
   with `delivered: False` and zero mutation.
7/8. Resume duplication and journal-sourced plan — above.
9. Scope-widening guidance rejected **before** delivery, with violations named.
10. Live canary — above.

## Not proven

Proof 5's stronger form — an exact run/node/attempt-bound receipt for a
*successfully delivered* steer — cannot be demonstrated, because no Tau steer
seam exists to deliver through. Every steer path therefore terminates in
`rejected` or `unsupported`. When Tau grows a control seam this becomes real
work, not a doc change.

Resume execution delegates to `tau workflow-resume`; the canary exercised the
plan path on a settled run, so `--execute` against a genuinely checkpointed
failure is covered by unit tests rather than a live failure injection.

Commit: fee22455da
