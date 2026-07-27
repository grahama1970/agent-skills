---
name: project-watchdog
description: >
  Global cross-project watchdog registry and cron dispatcher that scans
  registered GitHub repos for routable issues, takes one lease at a time, runs
  one bounded tick through each project's Tau or project-local harness, and
  requires a receipt before it mutates anything. Use when asked about the
  project watchdog, the GitHub issue cron, why the watchdog is idle or not
  picking up tickets, pausing or resuming automated issue dispatch, or
  registering a new project with the shared cron.
allowed-tools:
  - Bash
  - Read
  - Grep
triggers:
  - project watchdog
  - global watchdog
  - github issue cron
  - cross-project cron
  - project registry
  - watchdog status
  - pause the watchdog
  - resume the watchdog
  - why is the watchdog idle
  - register a project with the watchdog
metadata:
  short-description: Cross-project GitHub issue watchdog registry and cron dispatcher
runtime_self_improvement: basic
provides:
  - task-orchestration
  - progress-tracking
  - ticket-lookup
  - ticket-lease-routing
  - ticket-resolution
composes:
  - tau
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-subagent
  - best-practices-github-ticket
taxonomy:
  - resilience
  - precision
  - orchestration
  - github
  - cron
---

# Project Watchdog

`project-watchdog` is the shared control plane for the global GitHub issue
watchdog. It keeps the cross-project registry next to the shared skills and
subagents so individual projects do not each invent their own cron loop.

## Commands

```bash
./run.sh status                                    # registry, state, lock, cron
./run.sh tick --project tau                        # dry-run scan, no mutation
./run.sh tick --apply --project tau --max-tickets 1  # one bounded dispatch
./run.sh set-state global paused --reason "..."    # fail-closed kill switch
./run.sh set-state project active --project tau --reason "..."
./run.sh install-cron --apply                      # install the crontab line
./sanity.sh                                        # behavioural acceptance gates
```

Exit codes: `0` success or deliberate refusal, `1` operational failure,
`2` caller error (unknown project id, invalid state name).

## Troubleshooting: the watchdog runs but never dispatches

`status: NOOP, stop_reason: no_routable_issues` on every tick means the scan
succeeded and matched nothing. Check, in order:

1. **Label vocabulary.** Routing requires `agent-work` *plus* either
   (`next:coder` + `executor:local` + repair marker) or
   (`executor:local` + handoff marker). Tickets filed by `/ticket` carry
   `type:*` / `route:*` labels instead and will never match.
   `gh issue list --repo <repo> --label agent-work` returning `0` confirms it.
2. **State gates.** `./run.sh status` — both `global.state` and the project's
   state must be `active`.
3. **Lease labels.** Issues carrying `agent-active` or `agent-blocked` are
   skipped by design until a human clears them.

A failed scan is *never* reported as `NOOP`. If `gh` cannot reach GitHub the
tick fails with `status: BLOCKED` and a non-zero exit.

The runtime is deliberately narrow:

1. Load `registry/projects.json`.
2. Scan registered GitHub repos for routable issues.
3. Acquire one lease for one project ticket.
4. Invoke the project runner for one bounded tick.
5. Require a receipt.
6. Post the receipt or refusal back to GitHub.
7. Exit or move to the next project within the configured ticket limit.

The watchdog must not perform unbounded repair, invent missing routing, or make
global completion claims. If routing is missing or unauthorized, it should label
the issue for `next:human` or the project equivalent and stop.

## Registry

Project entries live in:

```text
registry/projects.json
registry/state.json
```

Each entry describes the project worktree, GitHub repo, allowed local agent
root, and the project-local command that should perform one bounded tick.

`projects.json` is relatively static configuration. `state.json` is the
operator-controlled runtime gate for pause, stop, and resume decisions.

A registry entry is not proof that the project is currently monitored. Only
`state.json` says whether a project is `active`, and only the cron log says
whether ticks are actually firing.

Every GitHub mutation is addressed to the repo of the project being dispatched.
Handlers take `repo` explicitly and have no default, so a dispatch for one
project cannot comment on, relabel, or close an issue in another.

## Layout

```text
scripts/project_watchdog.py    Typer CLI only; no business logic
scripts/check_path_literals.py AST guard against Path("${VAR}/...") literals
scripts/watchdog/config.py     paths, markers, environment resolution
scripts/watchdog/core.py       logging, subprocess, JSON IO, locking, receipts
scripts/watchdog/registry.py   project lookup and routable-issue selection
scripts/watchdog/github.py     repo-parameterised gh wrappers
scripts/watchdog/issue_fields.py  untrusted issue-body parsing and containment
scripts/watchdog/handlers.py   bounded per-issue dispatch
scripts/watchdog/commands.py   tick, install-cron, set-state, status
```

Environment overrides, all optional: `PROJECT_WATCHDOG_STATE_ROOT`,
`PROJECT_WATCHDOG_WORKSPACE`, `UV_BIN`. `sanity.sh` and the tests use the first
to run against a temporary state root instead of the operator's real receipts.

## Idle escalation — silence is not success

A watchdog reporting `NOOP / ok: true` every minute forever is
indistinguishable from a working one. Before 2026-07-27 this skill logged
**41,607** consecutive `no_routable_issues` ticks over roughly a month while a
label mismatch made a match impossible, and every tick reported success.

Idle ticks are now counted per project in `<state-root>/streaks.json`. Once a
project has been idle longer than `PROJECT_WATCHDOG_IDLE_ESCALATION_SECONDS`
(default 24h), the tick reports `NEEDS_ATTENTION` with `stop_reason:
idle_streak_exceeded` and an actionable diagnosis instead of `NOOP`. Escalation
receipts persist at most once per `PROJECT_WATCHDOG_IDLE_RENOTIFY_SECONDS`
(default 24h), so escalating does not reintroduce a receipt directory per
minute. Finding routable work clears the streak.

`./run.sh status` reports `idle_streaks` and `idle_escalation_seconds`.

## Dispatch backends — local or a visible Herdr pane

| Backend | Behaviour |
| --- | --- |
| `local` (default) | Captured subprocess. Self-contained, but invisible while it runs. |
| `herdr` | A named pane in a dedicated Herdr space, watchable in real time. |

Select globally with `PROJECT_WATCHDOG_DISPATCH_BACKEND`, per project with a
`dispatch_backend` field on the registry entry. The space label defaults to
`autoupdate` (`PROJECT_WATCHDOG_DISPATCH_SPACE`).

The pane is wrapped so it is observable and bounded:

- reports `working` on start, then `idle` or `blocked` on exit, so the Herdr UI
  and `$monitor-herdr` see a truthful state;
- writes a sentinel JSON file, so completion is a deterministic file read
  rather than an inference from a UI state — `herdr agent wait --status idle`
  against a raw command times out even after the command succeeds, because
  agent status comes from provider integrations an arbitrary command lacks;
- self-limits with `timeout`, because `$monitor-herdr` treats `done`, `idle`,
  `blocked`, and `unknown` as stopped and **not** `working`. A hung command
  left in `working` would never be flagged; bounding it turns a hang into a
  `blocked` pane the monitor does select;
- holds a failed pane alive for 15 minutes so it does not vanish before the
  monitor's next tick;
- never steals focus.

Observe dispatches with the exact command each receipt names:

```bash
skills/monitor-herdr/run.sh tick --space autoupdate --include-agent watchdog-dispatch
```

The `--include-agent` filter is why every pane reports the stable label
`watchdog-dispatch` rather than its per-issue name.

Dispatch is still synchronous: the tick blocks on a bounded wait so the existing
lease and closure semantics are unchanged. Fire-and-forget dispatch would need a
reconciliation path for leased-but-unfinished issues, which does not exist yet.

## Receipt retention

Ticks with status `NOOP` or `SKIPPED` print and log their receipt but do not
persist a directory. Only eventful runs — `COMPLETED`, `NEEDS_ATTENTION`,
`BLOCKED`, state changes, cron installs — leave a `receipt.json` behind. A
per-minute cron that persisted uneventful receipts accumulated 41,682
directories and 329 MB before 2026-07-27.

## Locking

One tick at a time, enforced by a lock directory under the state root. A lock
whose owner record is older than `LOCK_STALE_SECONDS` (900s) is treated as
abandoned by a killed process and reclaimed, with the takeover logged at
WARNING. Without this, a single SIGKILL would leave the watchdog permanently
`BLOCKED`.

## Pause, Stop, Resume

The watchdog must check both global and per-project state before scanning or
dispatching. State is fail-closed:

- `active`: scanning and one bounded dispatch are allowed.
- `paused`: observation is allowed; dispatch and mutation are refused.
- `stopped`: the project is ignored except for a trusted human resume action.

Subagents may request pause or stop in their receipt, but they do not own the
state transition unless the project explicitly grants that authority. A normal
worker request should become a GitHub comment or watchdog receipt requiring
human/operator confirmation.

Resume should require a trusted human/operator action and any project-specific
preconditions listed in `resume_requires`, such as a valid goal capsule, clean
worktree, or valid GitHub authentication.

## Dynamic GitHub Actions

GitHub Actions and the local watchdog should cooperate through labels and
receipts, not by racing each other:

- `executor:github-actions`: cloud-safe validation, lint, tests, and read-only
  review can run in Actions.
- `executor:local`: WebGPT, local browser, mounted storage, local models, and
  private workstation services must be picked up by the local watchdog.
- `executor:either`: the watchdog may choose based on project policy and current
  lease state.

Actions may route work to local by commenting a schema-valid handoff and
changing labels to `executor:local`. The local watchdog may route work to
Actions by invoking `workflow_dispatch` or `repository_dispatch` only when the
project config declares the workflow as allowed.

No dispatcher should mutate an issue unless it holds the current lease.

## Tau Generic Handoff Issue Marker

Tau issues can be routed through the global watchdog by adding `agent-work`,
`executor:local`, and a body marker:

```text
project-watchdog-action:tau-handoff-dispatch \
  start=experiments/goal-locked-subagents/proofs/.../start-handoff.json \
  max_steps=1 \
  active_goal_hash=sha256:... \
  apply_transport=false
```

The watchdog treats `start` as a Tau repo-relative path, rejects absolute paths
or `..`, runs one bounded `tau handoff-command-loop` tick, writes receipts under
`~/.local/state/project-watchdog/receipts/<run_id>/`, and comments the evidence
back to the issue. `apply_transport=true` is allowed only when the issue should
apply the terminal Tau GitHub transport; otherwise the transport receipt is
rendered dry-run.

Issues with `agent-active` or `agent-blocked` are skipped until a human/operator
clears the state label. This prevents cron from retrying a failed ticket every
minute without an explicit retry decision.
