# GitHub Actions And Watchdog State

`project-watchdog` should coordinate local cron and GitHub Actions through
durable issue state, not through hidden process state.

## State Gate

Before scanning or dispatching, the watchdog reads:

```text
registry/projects.json
registry/state.json
```

If global state is `paused` or `stopped`, no project dispatch happens. If a
project state is `paused` or `stopped`, that project is skipped except for
status reporting.

## GitHub Actions Direction

Use GitHub Actions for cloud-safe work:

- lint
- tests
- build checks
- read-only review
- schema validation

Use local cron/watchdog for local-only work:

- WebGPT browser sessions
- local models
- mounted storage
- private credentials
- desktop/browser verification
- project-local services

## Labels

The expected routing labels are:

```text
agent-work
agent-active
agent-done
agent-blocked
next:<agent>
executor:github-actions
executor:local
executor:either
next:human
```

Only one live lease should own mutation for an issue at a time.

## Required Behavior

When GitHub Actions cannot perform a local-only step, it should comment a valid
handoff and route to `executor:local`.

When local cron sees a cloud-safe step and the project config allows a workflow,
it may dispatch GitHub Actions. It must record the workflow dispatch URL or run
ID in its receipt.

If routing is ambiguous, the watchdog must not guess. It should label the issue
for human routing and write a refusal receipt.
