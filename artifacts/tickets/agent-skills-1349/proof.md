# agent-skills#1349 proof

## Scope

Replace `monitor-codebase` blanket docstring autofix with a proposal-first,
evidence-backed workflow. Source mutation requires reviewed candidates and
hash-bound apply validation.

## What changed

- `skills/monitor-codebase/autofix_docstrings.py` now emits read-only
  `monitor_codebase.docstring_candidate.v1` JSONL candidates.
- `apply-docstrings` applies only approved candidates and rejects stale source,
  missing proposed text, unsupported claims, contract mismatches, syntax errors,
  and non-docstring AST changes.
- `skills/monitor-codebase/run.sh scan --fix` now writes proposal artifacts
  instead of directly mutating source.
- `skills/monitor-codebase/SKILL.md` documents the proposal/apply workflow.
- `skills/monitor-codebase/sanity.sh` compiles the docstring workflow module.

## Proof Commands

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1349 uv run pytest skills/monitor-codebase/tests/test_docstring_proposals.py -q
```

Result: `12 passed in 0.14s`.

```bash
bash skills/monitor-codebase/sanity.sh
```

Result: `25 passed, 0 failed, 1 warnings`.

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1349-clean python3 skills/monitor-codebase/scripts/prove_docstring_proposals.py --live --out /tmp/monitor-codebase-docstring-proof-clean
```

Result: `status=pass`, `mocked=no`, `live=yes`.

## Live Proof Artifact

- `artifacts/tickets/agent-skills-1349/live-proof-summary.json`
- SHA-256: `656191122b949cd24c7a6053d56fab7370f2d8545a6e78cc1ffdb1fac8504230`

The live proof creates real local Python source files, runs the proposal CLI,
applies reviewed candidates, and checks stale, malformed, unsupported, and
AST-changing proposals fail closed.
