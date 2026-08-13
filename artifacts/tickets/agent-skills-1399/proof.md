# Proof For agent-skills#1399

Ticket: https://github.com/grahama1970/agent-skills/issues/1399

## Diagnosis

The goal hash was never missing — it was never propagated.

- `dag.json` carried `goal.goal_hash: sha256:8ba6db7f3c3cb026...`
- `request.json`, the file workers read as `start`, carried only
  `immutable_goal` (a string) with **`goal: null`**

`_handoff()` does `goal = start.get("goal", {})`, found nothing, and had no
hash to stamp on the handoff or its evidence. `HandoffContract.validate()`
therefore raised at the JOIN node — the terminal node, after all provider
spend, on a run whose handler had already answered.

Evidence read before any change:
`execution-status.json` → `degraded_join.stderr_excerpt`:

```
_run_join (line 4646) -> _handoff (line 5328) -> validate (line 3142)
SeamContractError: seam 'tau.agent_handoff.v1' violated:
  ['goal.goal_hash is required', 'evidence[0..3] missing goal_hash']
```

The join command spec confirms it: no `--goal-hash` argument exists, and the
worker accepts none. The goal could only arrive via the request payload.

## Change

The goal object was built inline in two DAG builders and written into neither
file the workers read. `_goal_object()` now derives it once; the DAG and
`request.json` both use it, so they cannot drift again.

## Proof

Live compile, non-mocked:

```
request.goal.goal_hash: sha256:b7b1368a0d31366f6e85b7edc543c445a6d75fb8437b3a23a025c5665a26fe8c
dag.goal.goal_hash    : sha256:b7b1368a0d31366f6e85b7edc543c445a6d75fb8437b3a23a025c5665a26fe8c
MATCH                 : True
```

The exact contract that raised in #1399, fed the compiled goal:

```
SEAM VALIDATES with the compiled request goal
pre-fix payload still fails (as in #1399): ['goal.goal_hash is required', 'evidence[0] missing goal_hash']
```

The second line matters: the seam has not been made permissive to pass.

## Regression Coverage

`skills/ask/tests/test_request_carries_goal_hash_1399.py` — 5 tests: the goal
object exists, request and DAG agree, the real `HandoffContract` accepts it, a
goalless payload still fails, and the hash is stable across compiles.

Agentic evals, so this cannot regress silently:

- `compiled-request-carries-the-goal-hash-1399`
- `join-seam-never-fails-after-provider-spend` (compiles a live DAG and asserts
  the two artifacts agree)

```
readiness: READY
cases: 18 | red: 0
  compiled-request-carries-the-goal-hash-1399   3/3
  join-seam-never-fails-after-provider-spend    3/3
```

Full suite: 665 passing. The 6 remaining failures are pre-existing and were
verified against HEAD with the change stashed.

## Not Proven

This fixes the join seam's missing goal. It does not fix the separate WebGPT
handler degradation visible in the same run (`browser_submitted_no_response_proof_requires_recover`),
which is provider-side transport, not the goal contract.

Commit: 6f6b6ec37a

## Worktree Audit

Closure used `GH_TICKET_SKIP_WORKTREE_AUDIT=1`. The reason is recorded here
rather than left as a silent override.

This ticket created **no worktree**. All work was done in the primary checkout
`~/workspace/experiments/agent-skills` on `main`, which is what the retention
rule asks for. The audit nonetheless fails, because it is repo-wide:

```
total: 171 | tmp: 8 | detached: 60 | dirty_secondary: 47
```

Those 47 dirty secondary worktrees belong to other lanes — `battle-ux-cleanup`,
`issue-1394-hermetic-runner`, `ticket-1397-push`, watchdog repair worktrees,
and older pushes. Committing or removing them would destroy another lane's
uncommitted work, and `audit-worktrees.sh` offers no per-path retain flag, so
the documented skip is the only route that does not put someone else's work at
risk.

The sprawl is a real, separate problem and remains open. It is not a property
of this fix, and this fix does not add to it.
