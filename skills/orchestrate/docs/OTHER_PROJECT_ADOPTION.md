# Other Project Adoption Contract

Use this checklist before another project agent relies on the `/plan -> /review-plan -> /orchestrate -> /code-runner` pipeline to integrate changes.

## Baseline

Adopt from `agent-skills` commit `4d91538f` or later.

Before use, run:

```bash
env -u VIRTUAL_ENV python skills/orchestrate/pipeline_readiness.py --profile quick --require-clean
```

Before enabling complete-task source commits, run:

```bash
env -u VIRTUAL_ENV python skills/orchestrate/pipeline_readiness.py \
  --profile gates \
  --include-adoption-smoke \
  --include-code-runner \
  --require-clean \
  --json
```

The result must be `PASS`. `WARN` is not enough for adoption because it usually means dirty source state or incomplete CI wiring.

## Supported Task Shape

Use `runner: code-runner` only for bounded file/process-local code tasks:

```yaml
runner: code-runner
backend: codex
mode: iterative
prompt: "Modify only src/target.py. Make answer() return 42."
allowlist:
  - src/target.py
read_context:
  - src/target.py
  - tests/test_target.py
dirty_worktree_policy: isolated_worktree
definition_of_done:
  command: "python -m pytest tests/test_target.py -q"
  assertion: "exit_code == 0"
blind_tests:
  - command: "python -m pytest tests/test_target.py -q"
```

Complete-task source integration requires all three fields:

```yaml
apply_to_source: true
commit_on_success: true
rollback_on_failure: true
```

`/code-runner` creates and removes the disposable worktree, proves the visible DoD, applies only allowlisted files to source, reruns source DoD, and commits only on success. `/orchestrate` owns blind/review gates and reverts the source commit when a later gate fails.

## Prohibited Task Shape

Do not use `code-runner` for live endpoint, live server, or browser checks:

```yaml
definition_of_done:
  command: "curl -fsS http://localhost:3000/health"
```

```yaml
definition_of_done:
  command: "npx playwright test tests/ui.spec.ts --project chromium"
```

Use a source-edit task plus a separate `runner: local` verification task for those workflows.

Do not use public `tests` as the information barrier. `blind_tests` must exist.

Do not pass operational tools or orchestration-only fields into `code-runner` tasks:

```text
hidden_tests, tools, tool_surface, skills, memory, memory_query,
planner, reviewer, backend_racing, predecessor_patches
```

Prompt-only retrieval context is allowed only through `/orchestrate`:

```text
memory_context, dogpile_context, web_context
```

Those fields must not reach the generated `/code-runner` spec.

## Opaque DoD Commands

Prefer explicit commands:

```yaml
definition_of_done:
  command: "python -m pytest tests/test_target.py -q"
  assertion: "exit_code == 0"
```

Opaque commands such as `make test`, `npm run ci`, or `scripts/check.sh` are rejected unless the plan declares the audited local-only contract:

```yaml
dod_scope: worktree_local
requires_network: false
requires_live_server: false
browser_required: false
opaque_command_reviewed: true
```

This metadata is a contract assertion, not a capability grant. The command still runs only inside the bounded worktree/source-apply path.

## Required Proof For Adoption

The external adoption smoke must prove all of the following:

- `/plan --validate` accepts a good structured plan and rejects a bad one.
- `/review-plan review` accepts the good plan and rejects the bad one.
- `/orchestrate run` calls the real `/code-runner/run.sh` entrypoint.
- Generated code-runner spec contains only allowed fields.
- Retrieval context is prompt/audit-only and not `read_context`.
- Complete-task success creates a source commit touching only allowlisted files.
- Blind failure after source commit creates a revert commit.
- Scratch/untracked source files survive.
- The source index is clean.
- No stale code-runner worktree remains registered.

Run it directly:

```bash
env -u VIRTUAL_ENV bash skills/orchestrate/tests/run_external_project_adoption_smoke.sh
```

## AGENTS.md Snippet

Copy `skills/orchestrate/docs/agents-plan-code-runner-snippet.md` into projects that want agents to use this pipeline.

