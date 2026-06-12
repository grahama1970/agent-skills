# Project-Agent Quickstart for `$loop`

`$loop` is currently suitable for supervised one-artifact transactions. It is
not a scheduler, issue closer, or multi-artifact DAG engine.

Use this boundary:

> Scillm/project-agent owns multi-artifact DAGs; `$loop` owns one bounded
> artifact transaction.

## Supported Surface

- One target repo or worktree.
- One artifact or tightly scoped code change.
- Explorer first, then one producer, then a fresh read-only verifier.
- Bounded repair attempts, default 3.
- Deterministic checks recorded in the final receipt.
- Scope validation and receipt validation before any PASS claim.

## Not Supported

- Cron or scheduled autonomous repair.
- GitHub issue closure.
- Multi-artifact project planning.
- Arbitrary DAG scheduling inside `$loop`.
- Parallel write-capable workers in one worktree.
- Treating WebGPT or any external reviewer as deterministic proof.

## Prompt Template

```text
$loop <one concrete artifact task>.

Use explorer first to inspect:
- <spec or source files>
- <tests or acceptance docs>

Use <coder|technical-writer> as the producer.
Use code-reviewer as a fresh read-only verifier of the actual diff/artifact.

Repair until code-reviewer returns PASS or <N> attempts are used.
Stop early if blocked, ambiguous, or if required files/checks are unavailable.

Scope:
- allowed files: <glob>
- no unrelated cleanup

Required checks:
- <deterministic command>

Done means:
- code-reviewer returns PASS
- final receipt validates
- changed-file scope check passes
- required checks pass
- final receipt lists changed files, checks run, stop reason, attempts used,
  verifier verdict, and remaining risks
```

## Project-Agent Acceptance Gates

Run these from the target repo after `$loop` finishes:

```bash
python .agents/skills/loop/scripts/validate_loop_receipt.py \
  .loop/runs/<loop_id>/final-receipt.json \
  --print-summary

python .agents/skills/loop/scripts/check_changed_files.py \
  --include '<allowed-scope>' \
  --exclude '.loop/**' \
  --from-file .loop/runs/<loop_id>/attempts/<attempt>/changed-files.txt

<required deterministic checks>
```

Accept the node only when those gates pass and the verifier receipt reports
`PASS` with `edited_files: []`.

## Project-Agent Result Record

Record at minimum:

- target repo/worktree path
- baseline git SHA or package digest
- launch command
- loop id and final receipt path
- changed files
- checks run and results
- stop reason
- rollback command
- remaining risks
