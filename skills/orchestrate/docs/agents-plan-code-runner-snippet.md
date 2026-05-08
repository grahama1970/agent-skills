# Plan to Code-Runner Agent Rules

Use this snippet in another project's `AGENTS.md` when project agents are allowed to use the `/plan -> /review-plan -> /orchestrate -> /code-runner` pipeline.

## Pipeline Gate

Before using the pipeline in this repo, run:

```bash
env -u VIRTUAL_ENV python skills/orchestrate/pipeline_readiness.py --profile quick --require-clean
```

Before source-integrating work, run:

```bash
env -u VIRTUAL_ENV python skills/orchestrate/pipeline_readiness.py \
  --profile gates \
  --include-adoption-smoke \
  --include-code-runner \
  --require-clean
```

Do not proceed if readiness is `FAIL` or `WARN`.

## Code-Runner Scope

`runner: code-runner` is allowed only for bounded file/process-local code tasks with:

- narrow `allowlist`
- explicit `read_context`
- machine-checkable `definition_of_done`
- real `blind_tests`
- `dirty_worktree_policy: isolated_worktree`

Complete-task source integration requires:

```yaml
apply_to_source: true
commit_on_success: true
rollback_on_failure: true
```

## Prohibited

Do not route these through `code-runner`:

- live endpoint checks
- live server checks
- browser/CDP/Playwright/Cypress/Selenium checks
- public `tests` pretending to be `blind_tests`
- hidden tools or operational memory fields

Use a separate `runner: local` task for live/browser verification after source changes.

## Opaque Commands

Prefer direct commands such as:

```yaml
definition_of_done:
  command: "python -m pytest tests/test_target.py -q"
  assertion: "exit_code == 0"
```

`make`, `npm run`, and `scripts/*` checks require:

```yaml
dod_scope: worktree_local
requires_network: false
requires_live_server: false
browser_required: false
opaque_command_reviewed: true
```

## Stop Conditions

Stop and escalate if:

- `/plan` rejects the plan
- `/review-plan` rejects the plan
- readiness is not `PASS`
- the source worktree is dirty outside the intended allowlist
- `/orchestrate` writes a failure bundle or interview request
- a source commit was created and later blind/review gates fail

On retry exhaustion, `/orchestrate` should write failure and interview artifacts by default. It must not block on `/interview` unless `ORCHESTRATE_ENABLE_INTERVIEW_ESCALATION=1` is explicitly set outside CI/headless mode.

