# Proof — #1430 agentic-evals fail-closed runner

Branch `main`, primary checkout `/home/graham/workspace/experiments/agent-skills`.
No secondary worktree was created or used for this ticket.

## Changed
- `skills/agentic-evals/src/runner.py`
- `skills/agentic-evals/SKILL.md`
- `skills/agentic-evals/fixtures/runner_selftest.json` (new)

## Acceptance criteria

**1. A failed required trial makes `run` exit non-zero.**
`run` previously had no exit logic at all and always exited 0. Observed live the
same day: `FAST=0` and `LIVE=0` while the live suite was `USABLE_WITH_GAPS` with
3 failing cases.
```
$ agentic-evals/run.sh run failing.json ; echo $?
1
```

**2. `--report-only` emits the same report and exits zero.**
```
$ agentic-evals/run.sh run failing.json --report-only ; echo $?
0
```

**3. Cross-artifact `sessionId` equality without parsing stdout.**
`expected.artifacts[].json_pointer` + `equals_artifact`. Matching pair -> PASS,
mismatched pair -> FAIL with an exact message:
```
cross-artifact mismatch: a.json/sessionId='S-4417' != c.json/sessionId='S-9999'
```
Also supports `equals`, `absent`, `min_bytes`, `sha256`.

**4. A timed-out case terminates its process group; no child remains.**
`run_trial` used `subprocess.run(timeout=)`, which kills only the direct child.
Now `start_new_session=True` + `killpg`, then `/proc` is re-read and survivors
recorded in `orphan_pids_after_teardown` (non-empty fails the trial).
Case `sleep 300 & sleep 300` at `timeout_seconds: 3`:
```
orphans_after_teardown: []
$ pgrep -af 'sleep 300'   ->  no match   (verified independently, not from the runner's own field)
```

**5. Required BLOCKED cases do not contribute to READY.**
`blocked_when_stdout_contains` yields outcome `BLOCKED`; readiness is scored over
required cases only.
```
readiness: USABLE_WITH_GAPS  {'PASS': 2, 'FAIL': 2, 'BLOCKED': 1, 'NOT_TESTED': 0}
```

**6. Report records provenance.**
`agentic_evals.report.v2` with `run_id`, `case_id`, `trial_id`, exact `argv`,
`fixture_sha256`, `repo.sha`/`repo.ref`, and per-trial `artifact_hashes`.
Manifest `proof_scope`/`claims` are preserved instead of being overwritten with
the hardcoded "fixture wiring smoke" claim, and `live` is derived rather than
hardcoded false. Reports are written atomically via `os.replace`.

**7. Self-tests cover each fail-closed behavior.**
`fixtures/runner_selftest.json` (`eval_kind: runner_selftest`), 6 cases x 2 trials:
```
readiness READY {'PASS': 6, 'FAIL': 0, 'BLOCKED': 0, 'NOT_TESTED': 0}
  PASS 2/2  a-failed-required-case-makes-run-exit-non-zero
  PASS 2/2  report-only-exits-zero-on-the-same-manifest
  PASS 2/2  a-timed-out-case-leaves-no-child-process
  PASS 2/2  a-required-blocked-case-does-not-reach-ready
  PASS 2/2  cross-artifact-equality-is-asserted-without-stdout
  PASS 2/2  the-report-preserves-the-manifest-proof-scope
exit=0
```

## Backward compatibility
Real suite, unchanged fixture:
```
$ agentic-evals/run.sh run skills/ask/fixtures/agentic_eval.json ; echo $?
readiness READY, 47 PASS, live true, proof_scope from the manifest
0
```
All external callers in the primary checkout are documentation/reference. The two
that are gates (`ops-herdr` regression gate, `best-practices-skills/rules.yml`)
want fail-closed behavior.

## Non-goal honored
No DAP/VS Code/debugpy/LLDB semantics added. Assertions are generic
(JSON pointer, equality, existence, hash, cross-artifact).

## Worktree audit
`audit-worktrees.sh --repo . --json` returns `ok:false`: 125 worktrees, 1 `/tmp`,
37 dirty secondary, 0 prunable. All flagged paths are pre-existing environment
sprawl unrelated to this ticket; none was created, entered, or modified by this
work. Explicitly retained, not cleaned here — worktree reclamation is owned by
`/ops-worktrees` and is out of scope for #1430.

## Proof boundary
Live runs of the real runner against real fixtures, read back from the emitted
report JSON and, for teardown, from `/proc` independently of the runner. No
mocks. Does not prove anything about the skills being evaluated.
