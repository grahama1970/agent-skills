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
  - agentic-evals
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
disciplines:
  - agentic-orchestration
  - observability-operations
---

# Project Watchdog

`project-watchdog` is the shared control plane for the global GitHub issue
watchdog. It keeps the cross-project registry next to the shared skills and
subagents so individual projects do not each invent their own cron loop.

## Commands

```bash
./run.sh status                                    # registry, state, lock, cron
./run.sh ui-data --receipt-limit 100               # read-only JSON snapshot for UI
./run.sh tick --project all                        # dry-run fleet scan, no mutation
./run.sh tick --apply --project all --max-tickets 1  # one bounded fleet dispatch
./run.sh tick --project tau                        # strict scan of tau only
./run.sh set-state global paused --reason "..."    # fail-closed kill switch
./run.sh set-state project active --project tau --reason "..."
./run.sh install-cron --apply                      # install the */5 crontab line
./sanity.sh                                        # behavioural acceptance gates
```

Exit codes: `0` success or deliberate refusal, `1` operational failure,
`2` caller error (unknown project id, invalid state name).

## Routing: which issues are eligible

An issue must carry `agent-work` and none of the hold labels
(`agent-active`, `agent-blocked`, `needs-human`, `maintainer-blocked`,
`next:human`, `status:deferred`). Eligible issues take the
first matching route:

| Route | Condition | Dispatch |
| --- | --- | --- |
| `add_tau_coder_command_spec` | `next:coder` + `executor:local` + repair marker in body | `tau handoff-command-loop` |
| `tau_handoff_dispatch` | `executor:local` + handoff marker in body | `tau handoff-command-loop` |
| `ticket_repair` | anything else carrying `agent-work` | `$ask tau-dag` creator-reviewer DAG, executed by Tau |

`ticket_repair` is the route ordinary `/ticket`-filed tickets take. `/ticket`
stamps `agent-work` at file time for any ticket with a concrete `route:` whose
type is not `question` or `triage`; those two are human-first by definition and
an unknown route has nowhere to be sent.

`--project <id>` is strict. A tick naming `--project tau` may dispatch only Tau
or report why Tau did not dispatch; it must not fall through to `agent-skills`
while the receipt still says Tau was requested. Fleet rotation is explicit:
use `--project all`, and installed global cron lines must render that value.

`runner_kind` does not gate routability. It used to require `tau-command-loop`,
because the lane hand-authored a contract against Tau's own command-spec tree,
which only the tau checkout has — so every other registered project was refused
before it could dispatch. `$ask` compiles the DAG for any repo; a project needs
only a worktree.

Collision is a property of the **target**, not the repository. agent-skills
holds 364 skills, and two tickets against different ones share no files. Each
ticket names its target on the `target:` line `/ticket` writes; older tickets
fall back to the skill paths their body mentions. A leased ticket blocks its own
targets and nothing else.

Registered projects may narrow a shared repository with `issue_target_prefixes`
and may leave a subtree to a narrower project with
`issue_target_exclude_prefixes`. This is required for skill-scoped projects
inside `agent-skills`: `battle` may dispatch only tickets whose parsed target is
under `skills/battle`, while the broad `agent-skills` project excludes that
prefix so fleet rotation does not hand Battle tickets to the generic skill
maintainer or hand Ask/Surf tickets to the Battle agent.

## Troubleshooting: the watchdog runs but never dispatches

`status: NOOP, stop_reason: no_routable_issues` on every tick means the scan
succeeded and matched nothing. Check, in order:

1. **`agent-work` label.** `gh issue list --repo <repo> --label agent-work`.
   Tickets filed before 2026-07-27 predate the stamping and will not carry it.
2. **Hold labels.** Any of the hold labels above parks a ticket deliberately.
3. **State gates.** `./run.sh status` — both `global.state` and the project's
   state must be `active`.


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
global completion claims. It should stop for the human only when the receipt says
`requires_human_input: true` or the next step is a real operator decision. A
machine-actionable `NEEDS_ATTENTION` result must instead include
`requires_human_input: false` plus `authorized_agent_next_steps`; supervising
agents are authorized to keep working from those commands instead of burying the
next action in `Not done`. If routing is missing or unauthorized and no safe
machine repair exists, it should label the issue for `next:human` or the project
equivalent and stop.

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
scripts/watchdog/ui_export.py  read-only UI snapshot from status + receipts
scripts/watchdog/commands.py   tick, install-cron, set-state, status, ui-data
ui/                            React/Tailwind control-tower UI
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

## Lease expiry

Issue leases use `agent-active` or `maintainer-active`. Their acquisition time
comes from GitHub's label event, and new watchdog lease comments also include
`acquired_at`. A lease becomes stale after
`PROJECT_WATCHDOG_LEASE_STALE_SECONDS` (default 24 hours).

On an applied tick, stale lease labels are removed before routing. The tick
receipt names each issue, label, acquisition time, age, expiry window, and
reason under `reclaimed_leases`. Reclamation removes only the lease label; it
does not change assignees or dispatch that same issue again in the reclaiming
tick. A dry run reports `would_reclaim_leases` without mutating GitHub.

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

## Three lanes, in order

A tick tries them in this order and stops at the first that has work, so an
audit can never delay a ticket that is actually waiting.

### 0. Dependency unblock — clear proved upstream holds only

Before repair dispatch, the scan reads `blocked-by` / `depends_on` references.
When every upstream issue is closed as `COMPLETED`, an applied tick removes only
the dependency hold labels (`blocked:upstream`, `maintainer-blocked`,
`needs-human`), records `dependency_unblock` as the handled work, and exits. It
does not dispatch the newly unblocked ticket in the same tick; the next cron
tick handles that ticket from a fresh scan. This keeps dependency clearing from
turning immediately into a repair DAG or a worktree-readiness failure.

### 1. Repair — `ticket_repair`

`$ask tau-dag --dag-template creator-reviewer` compiles the DAG and Tau executes
it. The watchdog does not drive the loop, count attempts, or decide when work is
done; Tau owns dispatch, receipt validation, resume, timeouts, immutable-goal
enforcement and fail-closed drift detection, and its receipt is the verdict.
The watchdog must still monitor the Tau run continuously. It must read the
Ask/Tau JSON stream artifacts (`events.jsonl`, `dag-progress.json`, node
receipts, or the run-specific equivalents) from dispatch until Tau emits a
terminal `PASS`, `FAIL`, `BLOCKED`, or `NEEDS_ATTENTION` verdict. Status output
must name the active run directory, current node/status, event count or latest
event id, elapsed time, and next stop condition. If the stream stalls or is not
readable, watchdog records that as a concrete pipeline defect instead of
silently stopping or summarizing from stale prose.

The retained watchdog receipt for this obligation is
`tau-stream-monitor.json`. It is not optional evidence. A repair tick that
invoked `$ask tau-dag` but did not write or read that monitor artifact is
`NEEDS_ATTENTION`, even when the child process exited or a model response file
exists.

Provider boundary: project-watchdog never calls SciLLM directly, never chooses a
SciLLM endpoint, and never passes raw `--scillm-*` auth or URL flags. The only
allowed provider route for repair is:

```text
project-watchdog -> $ask tau-dag -> Tau-executed DAG/command_spec -> Tau-owned SciLLM adapter
```

If a repair receipt reports `SCILLM_AUTH_INVALID_API_KEY` or
`scillm_auth_invalid_api_key`, that is a Tau/SciLLM provider-adapter failure
reported through the Tau receipt. project-watchdog may surface the exact failure
code, preserve the receipt path, and label the ticket for operator action; it
must not reimplement SciLLM auth probing, call `http://localhost:4001`, or
describe the failure as project-watchdog itself talking to SciLLM.

Two seats, deliberately different model families (`repair_creator`,
`repair_reviewer`, per project or env). A reviewer sharing the creator's blind
spots is a second pass, not a second opinion, so identical seats are refused
before dispatch.

Repair creators and repair reviewers must be locally executing lanes that can
work from the repair worktree and run the ticket's proof command. Browser/web
model seats such as `webgpt`, `webclaude`, `webkimi`, `webgemini`, and
`webgrok` cannot run local code and must not be configured as
`repair_creator` or `repair_reviewer`.

Web models are still useful before repair dispatch: use them through `$ask` for
strategy review, failure-family analysis, and creating focused `$ticket` items
with concrete targets, dependencies, acceptance criteria, and proof commands.
They advise what work should be filed; they do not execute or verify the local
repair lane.

`oc-*`/`opencode-go/*` are SciLLM OpenCode Go chat/review routes; they must not
be given `--handler-workspace` and treated as Codex CLI models. Repo-changing
OpenCode work needs a separate OpenCode serve/transport authoring lane with its
own receipt contract.

Each repair is authored in a worktree of its own, created from `origin/main`
per dispatch under the state root. The registered checkout is a human's working
tree; authoring there builds on whatever it happens to hold. It is still
consulted for one thing: whether this ticket's targets are settled.

The creator commits to its branch and must not push — the immutable goal says
so, and the lane records `origin/main` before and after, blocking the ticket if
it moved. That detects the violation; preventing it belongs in branch
protection.

Alpha projects that use dependent ticket families may set `auto_land_main:
true` in `registry/projects.json`. For those projects, a reviewer-passed repair
with a passing proof gate is rebased onto `origin/main`, pushed to `main`, marked
`agent-done`, and closed as `COMPLETED` in the same repair tick. Without this,
the issue remains open with `agent-done` as a branch awaiting review, and
downstream `blocked-by` tickets stay `dependency_open`.

#### The proof gate — a DAG that exited 0 is not a repaired ticket

`$ask tau-dag` exiting 0 means the seats were reached. Before the lane lands or
closes anything it checks four things and fails closed on any of them, writing
`repair-proof-gate.json` into the tick receipt either way:

- the reviewer seat declares `VERDICT: PASS` in its own response;
- no seat declares `FAIL`, `BLOCKED`, or `NEEDS_ATTENTION`;
- if the ticket's `Required proof` section names artifacts, at least one exists,
  was written after this dispatch started, and reads as a completed pass;
- the repair branch is at least one commit ahead of `origin/main`.

Verdicts are read, not inferred: only a `VERDICT:` line or the first word of a
`## Position` section counts, and prose describing a problem yields no verdict,
which is unproven. Refusal leaves the ticket open, `agent-blocked`, and
`NEEDS_ATTENTION`.

agent-skills#1499 is why: both node receipts said `status: PASS` while the
creator's response said it had no tools and the reviewer's said the live proof
had failed and a retry was still running. The issue was landed and closed as
completed with no proof artifact and no commit.

### 2. Closure audit — closing a ticket is a claim

Two seats (`closure_auditors`, at least two distinct) judge each `COMPLETED`
closure against the ticket's own acceptance criterion and required proof, using
the closing comments plus the proof artifacts named in the closure-evidence JSON,
read from disk. The Anthropic-family default is a local Ask/Tau Claude lane,
not `webclaude`; `webclaude` is a browser-transport test seat and should be used
only when explicitly testing the browser path.

- any FAIL → reopened, `agent-work` restored, the repair lane takes it again
- every seat PASS → `closure-verified`, stays closed
- a silent seat, or none → NEEDS_ATTENTION, left closed and unverified

`NOT_PLANNED` closures are excluded: a duplicate or won't-fix is bookkeeping,
not a claim that work was done. A closure citing no artifacts predates the
evidence contract and is NEEDS_ATTENTION, not FAIL. An audit that produced no
verdict cools down rather than retrying the same ticket every minute.

### 3. Completion attestation — an empty queue is not proof

When nothing is open to repair and nothing is left to audit — where the system
would otherwise call itself done — `completion_attestor` (WebGPT by default, a
different transport from the models that did and reviewed the work) judges
whether the project is genuinely finished. On FAIL it names tickets on a
`REOPEN: #123, #456` line and those are reopened, so the cycle repeats. The list
is intersected with the tickets it was shown. Rate-limited per project.

An attestor transport failure, parser failure, or no-verdict response is not a
human-input blocker by itself. The receipt must preserve the failed attestation,
set `requires_human_input: false`, and give the supervising agent the next
commands needed to inspect and repair the attestation path. Ask the human only
when the receipt names an operator decision, credential, label-removal policy, or
other action an agent is not allowed to take.

## cron needs a login environment

cron starts with a nearly empty environment and does not read the user's
profile, so provider credentials and PATH entries exported from a shell rc are
absent: every provider seat failed to authenticate under cron while the same
handler answered from an interactive shell. `install-cron` emits an explicit
`source` of the shell rc before the tick. Override with
`PROJECT_WATCHDOG_SHELL_INIT`.

See `PROJECT_KNOWLEDGE.md` for current readiness and open questions.

## Ecosystem

Member of the agent-governance ecosystem (see `skills/agent-ecosystem/SKILL.md`
for the shared map, mermaid graph, and the `pi.receipt_envelope.v1` boundary
envelope). Produces: tick receipts, proof gates, leases, `lazy_report_shame.continuation_guard.v1` ledgers. Consumes: GitHub agent-work tickets, tau verdicts. Envelope-wrapped
boundary events: dispatch, closure. Failure names come only from the triage-error
catalog or minted `*_unclassified_<8hex>` codes; ambiguous labels are
unrepresentable ecosystem-wide. When open machine work remains, write/validate the continuation ledger through `skills/shame/run.sh guard` so `$shame` rejects `state=done` until the ticket/gate/next command is resolved.
