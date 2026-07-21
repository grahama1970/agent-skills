# Monitor Herdr

`monitor-herdr` watches Herdr-visible agent panes for the failure mode that is
most expensive for a human: an agent stops, says something plausible, and leaves
real work unfinished.

The skill exists because stalled-agent babysitting does not scale. A human
should be available for real blockers: missing credentials, policy decisions,
external approvals, and unclear intent. The human should not have to keep
asking every idle Codex or Claude pane whether it forgot the immutable goal,
stopped after a partial proof, or needs to use `$brave-search`, `$webgpt`, or
`$ask` to unblock itself.

`monitor-herdr` is the small automated nudge in that loop. It inspects stopped
panes, decides whether a restart prompt is appropriate, writes receipts, and
only types into a pane when the Herdr state looks prompt-ready enough to avoid
spraying text into approvals, shells, or ambiguous terminal states.

## What It Does

At a high level:

1. Connects to the Herdr socket.
2. Finds panes in a named space such as `codex`.
3. Reads recent pane text and Herdr's own `agent.explain` state.
4. Looks for an immutable goal in the project or in the Codex goal footer.
5. Separates completed goals, real blockers, ambiguous states, and likely early
   stops.
6. In dry-run mode, records what it would do.
7. With `--apply`, sends one bounded restart or human-blocker prompt and then
   checks whether submission actually appeared in the pane.

The prompt is deliberately direct. It asks the stopped agent to say whether the
immutable goal is achieved, why it stopped, and whether it can resume, search,
ask a browser reviewer, or needs real human intervention.

## Why It Exists

Long agent runs fail in a boring way before they fail in an interesting one:
they stop too early. The transcript often contains obvious remaining work,
hook-blocked final messages, or "next steps" that should have been executed
without another human poke.

Herdr already knows where the panes are. Codex and Claude already know enough
to answer a direct question honestly most of the time. This skill connects those
two facts: when a pane is stopped and the goal does not look satisfied, ask the
agent the uncomfortable question automatically.

That is the whole point. Not a dashboard. Not a replacement scheduler. Not a
new source of truth. Just a conservative monitor that keeps stopped agents from
silently becoming human chores.

## Start Here

Run a read-only tick first:

```bash
skills/monitor-herdr/run.sh tick --space codex --min-stopped-seconds 600
```

Install the 10-minute cron only after the dry run looks sane:

```bash
skills/monitor-herdr/run.sh install-cron --space codex --apply
```

Inspect current monitor state:

```bash
skills/monitor-herdr/run.sh status
```

Generate the exact prompt text for one pane without sending it:

```bash
skills/monitor-herdr/run.sh probe-text \
  --pane-id w11:pTEST \
  --agent codex \
  --reason early_stop \
  --cwd /tmp \
  --json
```

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
  receipts/            committed example receipts
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
```

Fixture and deterministic evals prove parsing, selection, prompt construction,
cooldowns, stopped-age behavior, and typed-but-not-submitted failure accounting.
They do not prove that a live pane accepted a prompt. The live apply eval is the
gate for that.

## Current State

The skill has deterministic coverage and Herdr-observation behavior. Its
immutable goal still names one remaining live gate: run the live apply eval
against an eligible Herdr pane and require `submit_confirmed:true`.

Until that receipt exists, the honest state is `NEEDS_ATTENTION` for full live
restart proof, even if dry-run observation and local evals pass.
