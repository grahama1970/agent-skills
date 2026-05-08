# Plan to Code-Runner Readiness

This is the portable contract for using the `/plan -> /review-plan -> /orchestrate -> /code-runner` pipeline from another project.

## Supported Use

Use the pipeline for bounded code tasks that can be verified without a live browser, live server, or network endpoint:

- `runner: code-runner`
- narrow `allowlist`
- file/process-local `definition_of_done`
- real `blind_tests`
- `dirty_worktree_policy: isolated_worktree`
- complete-task source integration only when all three fields are explicit:
  - `apply_to_source: true`
  - `commit_on_success: true`
  - `rollback_on_failure: true`

Do not route live browser/server/API workflows to `/code-runner`. Use a source-tree edit task plus a separate `local` verification task for those.

## Readiness Command

From the `agent-skills` repository:

```bash
python skills/orchestrate/pipeline_readiness.py --profile quick
```

For the full local contract gate:

```bash
python skills/orchestrate/pipeline_readiness.py --profile gates
```

To include the heavier `/code-runner` adversarial non-soak gate:

```bash
python skills/orchestrate/pipeline_readiness.py --profile gates --include-code-runner
```

Use JSON output for automation:

```bash
python skills/orchestrate/pipeline_readiness.py --profile quick --json
```

`WARN` means the pipeline shape is present but the repo has dirty worktree state. `FAIL` means required files, tools, CI jobs, or gates are missing.

## Required Gates

PR or pre-merge gates should include:

- `/plan` sanity
- `/plan` code-runner contract tests
- `/review-plan` sanity
- `/review-plan` code-runner fail-closed tests
- `/orchestrate` context boundary tests
- `/orchestrate` full pipeline mock E2E
- `/code-runner` adversarial non-soak

Nightly/manual gates should include:

- complete-task source apply, source commit, blind-failure revert, scratch preservation, clean-index checks
- live `/scillm` smoke
- `/code-runner` adversarial soak
- failure artifact capture

## Complete-Task Rules

Complete-task mode is useful because it lands a source commit after the isolated worktree DoD and source DoD pass. It must remain explicit and gated.

`/code-runner` owns:

- disposable worktree creation
- allowlist-scoped patch generation
- isolated DoD
- source apply
- source DoD
- allowlist-only commit

`/orchestrate` owns:

- plan/review front gates
- retrieval context
- retry policy
- blind/review gates
- reverting a created source commit when later gates fail
- artifact-first human escalation

Use `ORCHESTRATE_FORCE_PATCH_ONLY=1` to strip source-apply authority in review-only or high-risk environments.

## Native Worker Adapters

Native worker adapters are experimental untrusted patch generators behind the same `/code-runner` envelope. They do not own DoD, source apply, allowlist enforcement, rollback, artifacts, or retries.

Supported adapter backend names:

- `codex-exec`
- `claude-code`
- `gemini-cli`
- `opencode`

Each adapter is disabled unless its command is explicitly configured:

```bash
export CODE_RUNNER_CODEX_EXEC_COMMAND="codex exec --some-safe-flags"
export CODE_RUNNER_CLAUDE_CODE_COMMAND="claude --print"
export CODE_RUNNER_GEMINI_CLI_COMMAND="gemini --prompt"
export CODE_RUNNER_OPENCODE_COMMAND="opencode run"
```

The command receives the bounded prompt on stdin and must return proposed file changes as `### FILE:` fenced blocks. `/code-runner` runs the adapter in a temporary directory, parses those blocks, and applies them only through the bounded write tools against the allowlist.

## Known Remaining Hardening

Opaque commands are the main remaining validator risk:

```text
npm run ci
make test
scripts/check.sh
python tools/check.py
```

The current validators fail closed on common opaque command shapes. Long term, move to approved DoD command templates or explicit metadata such as:

```yaml
dod_scope: worktree_local
requires_network: false
requires_live_server: false
browser_required: false
```
