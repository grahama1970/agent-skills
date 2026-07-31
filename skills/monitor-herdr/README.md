# Monitor Herdr

![Monitor Herdr header](assets/monitor-herdr-header.webp)

`monitor-herdr` watches Herdr-visible agent panes for the failure mode that is
most expensive for a human: an agent stops, says something plausible, and leaves
real work unfinished.

## Why It Exists

The skill exists because stalled-agent babysitting does not scale. A human
should be available for real blockers: missing credentials, policy decisions,
external approvals, and unclear intent. The human should not have to keep
asking every idle Codex or Claude pane whether it forgot the immutable goal,
stopped after a partial proof, or needs a tool invocation to unblock itself.

Long agent runs fail in a boring way before they fail in an interesting one:
they stop too early. The transcript often contains obvious remaining work,
hook-blocked final messages, or "next steps" that should have been executed
without another human poke.

Herdr already knows where the panes are. Codex and Claude already know enough
to answer a direct question honestly most of the time. This skill connects those
two facts: when a pane is stopped and the goal does not look satisfied, ask the
agent directly whether it can resume, search, ask a reviewer, or needs human
intervention.

That is the whole point. Not a dashboard. Not a replacement scheduler. Not a
new source of truth. Just a conservative monitor that keeps stopped agents from
silently becoming human chores.

## What It Does

`monitor-herdr` connects to Herdr, finds stopped panes in a named space, reads
recent text and `agent.explain` state, looks for an immutable goal, classifies
the stop reason, and records the decision. With `--apply`, it sends one bounded
prompt through `herdr pane run` and confirms submission appeared in the pane.
See [What It Will Not Do](#what-it-will-not-do) for the fail-closed rules.

The prompt is deliberately direct. It asks the stopped agent whether the
immutable goal is achieved, why it stopped, and whether it can resume, search,
ask a browser reviewer, or needs real human intervention.

## What It Will Not Do

`monitor-herdr` is intentionally fail-closed.

It will not invent an immutable goal when the project has none. It will not type
into panes Herdr classifies as blocked, unknown, approval-like, or ambiguous. It
will not treat a successful Herdr API write as proof that the prompt submitted.
It will not mark an agent as unblocked just because a nudge was sent.

If an agent says the immutable goal is complete with receipt evidence, the
monitor records that and leaves the pane alone. If an agent has a real human
blocker and has already tried the appropriate self-unblock paths, the monitor
also leaves it alone.

### Decision Model

| Pane condition | Monitor behavior |
| --- | --- |
| Goal completed with receipt evidence | Records and leaves alone |
| Legitimate human blocker | Records and leaves stopped |
| Blocked, unknown, approval-like, or ambiguous | Observes only; never types |
| No immutable goal and no early-stop evidence | Records and leaves alone |
| Likely early stop and positively prompt-ready | With `--apply`, sends one bounded prompt |
| Transport call succeeds but submission not visible | Records `NEEDS_ATTENTION` |

## Start Here

Run a read-only tick first:

```bash
skills/monitor-herdr/run.sh tick --space codex --min-stopped-seconds 600
```

The default `--min-stopped-seconds 600` gate means a newly stopped pane normally
has to remain stopped across the monitoring interval before it is eligible.

Install the 10-minute cron only after reviewing dry-run receipts and confirming
the pane classification with `probe-text`. Applied mode **will** type into
prompt-ready panes.

```bash
skills/monitor-herdr/run.sh install-cron --space codex --apply
```

Inspect current monitor state:

```bash
skills/monitor-herdr/run.sh status
```

Status distinguishes the latest receipt from the latest cron-sourced receipt.
That matters because a manual live eval should not make cron look healthy.

Open a workspace file in the installed Herdr file viewer:

```bash
skills/monitor-herdr/run.sh open-file /path/to/workspace/file.py
skills/monitor-herdr/run.sh open-file src/file.py:42
skills/monitor-herdr/run.sh open-file --query "prompt builder" --root /path/to/workspace
```

Exact paths must resolve to files under the workspace root. If the target is a
plain query, `open-file` fuzzy-matches the workspace file list, fails closed on
tied top matches, and opens a Files split on the resolved file using
`herdr-file-viewer --open`.

Generate the exact prompt text for one pane without sending it:

```bash
skills/monitor-herdr/run.sh probe-text \
  --pane-id w11:pTEST \
  --agent codex \
  --reason early_stop \
  --cwd /tmp \
  --json
```

## Runtime Shape

Normal paths:

```text
skills/monitor-herdr/
  SKILL.md             operational contract for agents
  README.md            this human guide
  run.sh               stable entrypoint
  sanity.sh            cheap deterministic proof
  scripts/             Herdr client, classifier, goal discovery, prompt builder
  tests/               unit coverage
  evals/               deterministic and opt-in live E2E checks
  herdr-plugin/        native Herdr plugin wrapper around run.sh
  receipts/            committed minimal state receipts, not runtime logs
```

Runtime receipts live outside the repo by default:

```text
~/.local/state/monitor-herdr/receipts/<run-id>/receipt.json
~/.local/state/monitor-herdr/receipts/<run-id>/events.jsonl
~/.local/state/monitor-herdr/logs/monitor-herdr.log
```

## Proof

Cheap local checks:

```bash
skills/monitor-herdr/sanity.sh
uv run --project skills/monitor-herdr pytest -q \
  skills/monitor-herdr/evals/test_real_world_e2e.py
```

Opt-in live Herdr checks:

```bash
uv run --project skills/monitor-herdr python \
  skills/monitor-herdr/evals/live_herdr_e2e.py run --allow-live

uv run --project skills/monitor-herdr python \
  skills/monitor-herdr/evals/live_herdr_e2e.py run \
  --allow-live --allow-apply --require-prompt

uv run --project skills/monitor-herdr python \
  skills/monitor-herdr/evals/live_plugin_e2e.py run --allow-live
```

Fixture and deterministic evals prove parsing, selection, prompt construction,
cooldowns, stopped-age behavior, and typed-but-not-submitted failure accounting.
They do not prove that a live pane accepted a prompt. The live apply eval is the
gate for proving that an eligible pane accepted a prompt and produced
`submit_confirmed:true`.

## Herdr Plugin

The plugin wrapper is intentionally boring. Herdr launches an action, and the
action calls the same `run.sh` entrypoint as the skill:

```bash
herdr plugin link skills/monitor-herdr/herdr-plugin
herdr plugin action list --plugin agent-skills.monitor-herdr
```

The actions are status, dry-run tick, apply tick, and current-pane prompt
probe. Plugin tick receipts use `invocation_source:"herdr_plugin"`; cron
receipts use `invocation_source:"cron"`.

## Current State

The skill has deterministic coverage, live Herdr observation behavior, live
prompt-submit receipts using `herdr pane run`, and a native Herdr plugin wrapper
with a live action-log eval.

Scheduler health is separate. Until an installed cron line produces a
cron-sourced receipt, `status` reports scheduler health as `NEEDS_ATTENTION`
even when manual live evals pass.
