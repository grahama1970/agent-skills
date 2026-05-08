# `/code-runner` adversarial pytest tranche

This is the first executable red/green spine for the `/code-runner` reliability suite.

It is intentionally adversarial. Some tests are expected to fail against the current pasted implementation until the runner is hardened.

## What this tranche targets

1. Patch-only success leaves source byte-for-byte unchanged.
2. Patch-only failure leaves source byte-for-byte unchanged.
3. Runtime failure removes the disposable worktree.
4. `output_dir` inside source is rejected before writing artifacts.
5. Bad allowlist paths are rejected.
6. `CODE_RUNNER_SOURCE_CWD` cannot be used to mutate source from `run_command`.
7. Symlink writes cannot escape the disposable worktree.
8. Complete-task dirty allowlist fails before source apply.
9. Complete-task source apply starts only after isolated DoD passes.
10. Source DoD failure rolls back allowlisted paths only.
11. `commit_on_success` commits only allowlisted paths.
12. Fake `/scillm` HTTP/stream failures produce diagnostic artifacts and cleanup.

## How to use

From your repo root:

```bash
unzip code_runner_adversarial_tests.zip
pytest -q code_runner_adversarial_tests/tests
```

If your package is not at `.agents/skills/code-runner/src`, set:

```bash
export CODE_RUNNER_SRC=/absolute/path/to/.agents/skills/code-runner/src
pytest -q code_runner_adversarial_tests/tests
```

## Notes

- `.hunk.md` is treated as the contract-level artifact.
- `.patch` is treated as an implementation detail because the current implementation writes it and `result.patch_artifact` points to it.
- Preflight failure artifacts are intentionally tested separately from runtime artifacts.
- The tests do not import the runner's own path/patch safety logic as the oracle.
