---
name: monitor-confused-agents
description: >
  Monitor Herdr-visible Codex/Claude agent panes for stalled, blocked, unknown,
  or confused state, then ask each stalled agent whether it needs human
  intervention or can self-unblock with brave-search or webgpt.
triggers:
  - monitor confused agents
  - monitor stalled agents
  - ask stalled agents if they are confused
  - herdr agent monitor
  - codex space monitor
  - lost agent monitor
provides:
  - stalled-agent-monitoring
  - progress-tracking
  - agent-unblock-probe
composes:
  - brave-search
  - webgpt
  - task-monitor
  - tau
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-subagent
runtime_self_improvement: basic
taxonomy:
  - observability
  - orchestration
  - resilience
---

# Monitor Confused Agents

Use this skill to monitor Herdr agent panes and restart agents that stopped
before the immutable goal was met.

This skill is a thin fail-closed monitor. It does not replace Tau, Herdr,
`$brave-search`, `$webgpt`, or `$ask`. It uses the Herdr socket API, writes
receipts, and, only with `--apply`, sends a bounded restart or human-blocker
prompt to selected stopped panes.

## Commands

```bash
skills/monitor-confused-agents/run.sh tick --space codex
skills/monitor-confused-agents/run.sh tick --space codex --apply
skills/monitor-confused-agents/run.sh status
skills/monitor-confused-agents/run.sh install-cron
skills/monitor-confused-agents/run.sh install-cron --space codex --apply
skills/monitor-confused-agents/run.sh probe-text --pane-id w11:pG --agent codex --reason early_stop
skills/monitor-confused-agents/sanity.sh
```

## Runtime Contract

- `tick` uses the Herdr Unix socket API against `~/.config/herdr/herdr.sock` by
  default.
- `tick` resolves the named Herdr `--space` by workspace id, number, or label.
- `tick` reads `workspace.list`, `pane.list`, `pane.read`, and `agent.explain`.
- By default `tick` is observation-only and sends nothing.
- `tick --apply` sends one prompt per selected pane using `pane.send_text` plus
  `pane.send_keys`.
- On Herdr versions that expose `terminal session control`, that lower-level
  controller is the preferred future path for text plus carriage return. The
  installed Herdr `0.7.1` on this host exposes `terminal attach` but not
  `terminal session control`, so this skill uses the available socket methods
  and post-submit readback.
- A Herdr `ok` response is transport evidence only. The monitor reads the pane
  after pressing Enter and requires visible submission evidence before marking
  `submit_confirmed:true`.
- Before injecting input, the monitor runs Herdr's idle wait and then checks
  `agent.explain`. If the agent is already `working`, it skips injection and
  records `skipped:true`.
- Some Codex panes need a second Enter after a multi-line paste. If the first
  Enter does not produce submission evidence, the monitor sends one additional
  Enter and records `second_enter_sent:true`.
- Prompt spam is prevented by a state file and a cooldown.
- Every run writes:

```text
~/.local/state/monitor-confused-agents/receipts/<run-id>/receipt.json
~/.local/state/monitor-confused-agents/receipts/<run-id>/events.jsonl
~/.local/state/monitor-confused-agents/logs/monitor-confused-agents.log
```

## Candidate Selection And Immutable Goal Gate

The monitor targets stopped terminals in the named Herdr space. Stopped statuses
default to:

```text
done idle blocked unknown
```

For each stopped pane, the monitor reads recent transcript text and looks upward
from the pane cwd for immutable-goal files:

```text
IMMUTABLE_GOAL.md
GOAL.md
.goal
.codex/goal.json
.codex/GOAL.md
.tau/goal.json
```

If no immutable goal is found in project files, the monitor records the pane and
allows it to remain stopped. The monitor must not invent an objective from
generic early-stop language; defining the immutable goal is on the human or
project instructions.

If the current transcript region says `Immutable Goal:
ACHIEVED_WITH_RECEIPT:path`, `DONE_WITH_RECEIPT`, or `Goal achieved`, and that
same current region does not contain proof-blocker or remaining-work markers,
the monitor records the pane and does not prompt it. Cron may inspect completed
panes every 10 minutes; deterministic inspection is acceptable, but restart
prompts are not.

If an immutable goal is found or the transcript shows remaining work / hook
failure / early stop language, the monitor selects the pane. The restart prompt
requires the agent to state:

- the immutable goal or `UNKNOWN`;
- whether the goal is achieved with a receipt;
- why it stopped if the goal is not achieved;
- `Unblock Attempts:` showing `$brave-search` and the project-bound
  `$browser-oracle` reviewer receipt, or why each is not applicable;
- whether it will resume, use `$brave-search`, use `$webgpt`/`$ask`, or ask the
  human for a legitimate blocker.

If recent text shows a real missing human decision, credential, authority, or
external state, and there is no early-stop evidence overriding that blocker, the
monitor sends a human-blocker prompt instead of a resume prompt.

If the current transcript region includes `Immutable Goal: BLOCKED:...` and a
complete `Unblock Attempts:` line showing `$brave-search` plus the project-bound
browser-oracle reviewer receipt or `NOT_APPLICABLE` reasons, the monitor treats
the blocker as legitimate human intervention and leaves the pane stopped unless
current early-stop markers override that claim.

## Prompt Actions

Restart prompts use this disposition vocabulary:

```text
RESUMING_NOW
BLOCKED_NEEDS_HUMAN
CONFUSED_NEEDS_HUMAN
CAN_SELF_UNBLOCK_BRAVE_SEARCH
CAN_SELF_UNBLOCK_WEBGPT
DONE_WITH_RECEIPT
```

The prompt tells the agent to use the real `$brave-search`, `$webgpt`, or `$ask`
runtime if that is the next unblock step, and to stop and ask the human only
when the blocker is a real missing decision, credential, authority, or external
state.

## Cron

Install the 10 minute cron line:

```bash
skills/monitor-confused-agents/run.sh install-cron --apply
```

The installed cron is marked with:

```text
# monitor-confused-agents herdr cron
```

It runs `tick --apply` every 10 minutes and appends output to the skill log
directory. Re-running `install-cron --apply` replaces the existing marked line.

## Proof Boundaries

Report `mocked` and `live` explicitly:

- Fixture tests prove parsing, selection, cooldown, prompt construction, and
  crontab rendering only.
- A dry-run `tick` proves Herdr can be observed and receipts can be written.
- An applied `tick --apply` proves the monitor attempted Herdr prompt transport
  and records both API results and post-Enter submission evidence. Treat
  `api_sent:true` without `submit_confirmed:true` as a transport failure that
  still needs attention.
- A sent probe is not proof that an agent correctly unblocked itself; the next
  proof is the agent's own receipt, status artifact, or human decision.
