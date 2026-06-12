# Project-Agent Failure Contract for `$loop`

Project agents must fail closed. A missing or invalid proof is a blocked node,
not a successful `$loop` run.

## Failure States

| Condition | Required status |
| --- | --- |
| Required custom agent is missing | `BLOCKED_MISSING_AGENT` |
| Scope is ambiguous | `BLOCKED_SCOPE_AMBIGUOUS` |
| Required files cannot be found | `BLOCKED_REQUIRED_FILES_MISSING` |
| Tests or checks cannot run | `BLOCKED_TESTS_UNAVAILABLE` |
| Final receipt is missing | `BLOCKED_RECEIPT_MISSING` |
| Final receipt is invalid | `BLOCKED_RECEIPT_INVALID` |
| Scope checker fails | `BLOCKED_SCOPE_VIOLATION` |
| Verifier returns `NEEDS_CHANGES` and attempts remain | retry producer |
| Verifier does not return `PASS` by the cap | `MAX_ATTEMPTS` |
| Timeout occurs | `BLOCKED_TIMEOUT` |
| Unrelated dirty worktree prevents attribution | `BLOCKED_DIRTY_WORKTREE` |
| WebGPT is unavailable or fails | `EXTERNAL_REVIEW_BLOCKED` |

`PASS` is allowed only when the final verifier owns the PASS and local
deterministic gates also pass.

## Rollback Requirements

Every project-agent `$loop` run must record:

- baseline git SHA
- branch or worktree path
- changed files
- rollback command
- whether rollback was executed

For proof runs, prefer a throwaway repo or isolated worktree. If the run occurs
in a dirty checkout, the proof must list the dirty files and explain why they are
out of scope.

## GitHub And Scheduler Safety

Project-agent reliability proofs must record:

- `scheduler_enabled=false`
- `closure_attempted=false`
- `destructive_writes=[]`
- `lease_released=true` or `no_lease_needed=true`

No project-agent proof may close an issue, merge a branch, or enable a scheduled
run from WebGPT opinion alone.

## External Review

External review is useful but not authoritative. If WebGPT or another reviewer
is used, save the request bundle and response artifacts. Treat review failures
as findings to reconcile against local evidence, not as automatic project state.
