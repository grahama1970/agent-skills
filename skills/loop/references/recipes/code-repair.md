# Code Repair Recipe

Use this recipe when the artifact is a focused source-code change in one repo.

## Prompt shape

```text
$loop implement <objective>.

Use explorer to inspect the relevant source, tests, and constraints.
Use coder to make the smallest focused patch.
Use code-reviewer as a fresh read-only verifier of the actual diff.

Repair until code-reviewer returns PASS or 3 attempts are used.

Scope:
- allowed files: <paths>
- no broad refactors
- no unrelated cleanup

Done means:
- code-reviewer returns PASS
- required tests/checks pass
- final receipt lists changed files, checks run, stop reason, attempts used, and remaining risks
```

## Node sequence

```text
explorer(read_only) -> coder(write) -> code-reviewer(read_only)
```

The `coder -> code-reviewer` edge may repeat until verifier PASS, BLOCKED, or
max attempts.

## Concurrency

No write-capable node may run concurrently in the same worktree. The default
code-repair recipe is sequential.

## Verifier rule

Only `code-reviewer` may approve the implementation. A producer/coder receipt
is never sufficient for PASS.

## Receipt type

Use the existing code-repair loop receipt validated by:

```bash
python .agents/skills/loop/scripts/validate_loop_receipt.py .loop/runs/<loop_id>/final-receipt.json --print-summary
```
