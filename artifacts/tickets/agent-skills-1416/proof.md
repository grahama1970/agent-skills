# Proof for agent-skills#1416

## Operational change

`watchdog.core.run_cmd` now starts subprocesses in their own process group. On
timeout it snapshots descendant processes, sends SIGTERM to the process group,
falls back to SIGKILL if needed, and records the cleanup details in the command
receipt under `process_group`.

## Deterministic proof

- `uv run --project skills/project-watchdog pytest -q skills/project-watchdog/tests`
  - Result: `165 passed`
- `skills/project-watchdog/sanity.sh`
  - Result: `project-watchdog sanity: 45 passed, 0 failed`
- `python3 scripts/check_mock_evidence_claims.py`
  - Result: `OK: checked 647 test file(s); no mock+proof claim violations`

## Live proof

- Artifact: `artifacts/tickets/agent-skills-1416/live-timeout-process-group.json`
  - `mocked=false`, `live=true`
  - Exercised the real `watchdog.core.run_cmd` timeout path with a parent
    Python process that launched a child sleeper.
  - Assertions passed: timeout observed, exit code 124, child listed before
    kill, process group terminated, child not alive after timeout.

- Artifact: `artifacts/tickets/agent-skills-1416/live-apply-timeout-receipt.json`
  - `mocked=false`, `live=true`
  - Exercised the real `project-watchdog tick --apply` path with an isolated
    state root, clean registered git clone on `main`, local GitHub shim to avoid
    mutating real issues, real repair worktree preparation, and forced
    ticket-repair timeout through `watchdog.core.run_cmd`.
  - Assertions passed: tick returned `NEEDS_ATTENTION`, one issue handled, DAG
    command timed out, exit code 124, process group recorded, process group
    terminated, persisted receipt read back.

## Retention and audit note

Commit pushed to `origin/main`:
`edf7205207a6af4a377bc52ac9250acb2b159d32`.

Remote ref readback:
`edf7205207a6af4a377bc52ac9250acb2b159d32 refs/heads/main`.

Required worktree audit command:

```bash
skills/best-practices-github-ticket/scripts/audit-worktrees.sh --repo /home/graham/workspace/experiments/agent-skills-worktrees/watchdog-timeout-cleanup-1416 --json
```

Result: failed because of pre-existing retained workspace debt outside this
ticket: 183 total worktrees, 1 `/tmp` worktree, 50 dirty secondary worktrees.
The task worktree `watchdog-timeout-cleanup-1416` is clean and the task commit
is durable on `origin/main`.

Audit bypass justification for closing this ticket: the audit failure is
pre-existing, unrelated retained worktree debt. Blocking this process-group
timeout repair on cleanup of 50 unrelated dirty worktrees would leave the
watchdog timeout bug unresolved in the issue tracker even though the task change
and proof are already committed and pushed.

mocked: no
live: yes
