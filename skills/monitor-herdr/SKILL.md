---
name: monitor-herdr
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
  - ticket
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

# Monitor Herdr

Use this skill to monitor Herdr agent panes and restart agents that stopped
before the immutable goal was met.

This skill is a thin fail-closed monitor. It does not replace Tau, Herdr,
`$brave-search`, `$webgpt`, `$ask`, or `$ticket`. It uses the Herdr socket API, writes
receipts, and, only with `--apply`, sends a bounded restart or human-blocker
prompt to selected stopped panes.

## Commands

```bash
skills/monitor-herdr/run.sh tick --space codex
skills/monitor-herdr/run.sh tick --space codex --min-stopped-seconds 600
skills/monitor-herdr/run.sh tick --space codex --apply
skills/monitor-herdr/run.sh status
skills/monitor-herdr/run.sh install-cron
skills/monitor-herdr/run.sh install-cron --space codex --apply
skills/monitor-herdr/run.sh probe-text --pane-id w11:pG --agent codex --reason early_stop
skills/monitor-herdr/sanity.sh
uv run --project skills/monitor-herdr pytest -q skills/monitor-herdr/evals/test_real_world_e2e.py
uv run --project skills/monitor-herdr python skills/monitor-herdr/evals/live_herdr_e2e.py run --allow-live
uv run --project skills/monitor-herdr python skills/monitor-herdr/evals/live_herdr_e2e.py run --allow-live --allow-apply --require-prompt
```

## Runtime Contract

- `tick` uses the Herdr Unix socket API against `~/.config/herdr/herdr.sock` by
  default.
- `tick` resolves the named Herdr `--space` by workspace id, number, or label.
- `tick` reads `workspace.list`, `pane.list`, `pane.read`, and `agent.explain`.
- By default `tick` is observation-only and sends nothing.
- `tick --apply` sends one prompt per selected pane using `herdr pane run`,
  which submits text plus Enter atomically on supported Herdr builds. The
  socket `pane.send_text` plus `pane.send_keys` path remains a bounded fallback
  only when `pane run` fails before modifying input.
- `tick --min-stopped-seconds N` requires a stopped pane to have been stopped
  for at least `N` seconds before it is selected for prompting. When Herdr
  exposes an idle/stopped age field, the monitor uses that field. On Herdr
  versions that expose only current state, including the installed `0.7.1`
  server on this host, the monitor records the first observed stopped timestamp
  in its own state file and uses that observed age on later ticks.
- The official Herdr CLI documents `pane run` as the command that submits text
  plus Enter. Use that path for live Codex/Claude prompt submission unless a
  future Herdr release exposes a better non-takeover agent prompt API.
- A Herdr `ok` response is transport evidence only. The monitor reads the pane
  after pressing Enter and requires visible submission evidence before marking
  `submit_confirmed:true`.
- Before injecting input, the monitor runs Herdr's idle wait and then checks
  `agent.explain`. It requires a positive prompt-ready matched rule and rejects
  fallback, skip, or warning explain output. If the agent is already `working`
  or explain is ambiguous, it skips injection and records `skipped:true`.
- `blocked` and `unknown` pane states are observation-only. The monitor records
  them but does not type into them because they may be approval, permission, or
  human-input surfaces.
- `idle` based on Herdr fallback classification is also observation-only. A
  prompt is injected only when Herdr state is prompt-ready enough for input.
- Herdr CLI helper calls receive the same `HERDR_SOCKET_PATH` as the socket
  observation client so a custom session cannot observe one Herdr server and
  inject into another.
- Some Codex panes need a second Enter after a multi-line paste. If the first
  Enter does not produce submission evidence, the monitor sends one additional
  Enter and records `second_enter_sent:true`.
- Some Herdr/Codex terminal states accept `ctrl+j` as the submit/newline key
  where repeated `enter` does not submit. If both Enter attempts fail and the
  pane is still prompt-ready, the monitor sends one bounded `ctrl+j` fallback
  using Herdr key-combo syntax and records `ctrl_j_sent:true`.
- Submission evidence must newly appear after the prompt attempt. Old
  `Running UserPromptSubmit hook`, `Working (`, or `Booting MCP server` text in
  scrollback does not confirm the current prompt.
- If the transcript changes between selection and send to a current
  goal-achieved or fully exhausted-blocker state, the monitor skips the prompt
  before typing.
- Pre-read failures, Herdr send failures, Enter failures, and typed-but-not
  submitted attempts make the tick exit nonzero with `status:NEEDS_ATTENTION`.
- Any input-modifying uncertain attempt is recorded in cooldown state, but it
  uses the shorter unconfirmed-attempt cooldown, default `600` seconds, rather
  than the normal confirmed-submit cooldown.
- Prompt spam is prevented by a state file and cooldowns: confirmed submissions
  default to one hour; unconfirmed input-modifying attempts retry on the
  10-minute cron cadence unless configured otherwise.
- Stopped-age tracking is monitor-owned state when the Herdr API does not
  provide idle duration. A first observation can record the stopped pane without
  selecting it; a later cron tick may select it once `--min-stopped-seconds` is
  satisfied.
- Every run writes:

```text
~/.local/state/monitor-herdr/receipts/<run-id>/receipt.json
~/.local/state/monitor-herdr/receipts/<run-id>/events.jsonl
~/.local/state/monitor-herdr/logs/monitor-herdr.log
```

Receipts include `invocation_source`. Normal manual runs use `cli`, plugin
ticks use `herdr_plugin`, and installed cron uses `cron`. Scheduler health
looks for cron receipts specifically, so a manual live eval cannot hide a bad
scheduled job.

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

If no immutable goal is found in project files and there is no explicit
early-stop/hook-failure marker, the monitor records the pane and allows it to
remain stopped. The monitor must not invent an objective from generic idle text;
defining the immutable goal is on the human or project instructions.

If no immutable goal is found but the current transcript has explicit
early-stop/hook-failure markers such as `Stop hook (stopped)`, `status response
blocked`, `remaining work`, or `what remains`, the monitor may select the pane.
The prompt forces the agent to answer with `Immutable Goal: UNKNOWN` if needed
and either resume the obvious remaining work, use `$brave-search`/browser-oracle
to unblock, check and resolve any referenced `$ticket`, or state a real human blocker.

Codex's own `/goal` footer is also treated as an immutable-goal signal. A
footer such as `Goal blocked (/goal resume)` means there is an active goal that
has not reached an allowed stop state, so an otherwise prompt-ready stopped pane
can be selected even when no project `GOAL.md` exists.

If the current transcript region says `Immutable Goal:
ACHIEVED_WITH_RECEIPT:path`, `DONE_WITH_RECEIPT`, or `Goal achieved`, and that
same current region does not contain proof-blocker or remaining-work markers,
the monitor records the pane and does not prompt it. Cron may inspect completed
panes every 10 minutes; deterministic inspection is acceptable, but restart
prompts are not.

Goal discovery is bounded to the pane's project root. A parent directory outside
that root must not donate a `GOAL.md` or `IMMUTABLE_GOAL.md` to the pane.

If an immutable goal is found or the transcript shows remaining work / hook
failure / early stop language, the monitor selects the pane. The restart prompt
requires the agent to state:

- the immutable goal or `UNKNOWN`;
- whether the goal is achieved with a receipt;
- why it stopped if the goal is not achieved;
- `Ticket Check:` showing `$ticket` lookup/lease/fix/proof/close activity when
  the transcript, project state, or human prompt names a GitHub issue or
  `$ticket`, or `NOT_APPLICABLE` with a concrete reason;
- `Unblock Attempts:` showing `$brave-search` and the project-bound
  `$browser-oracle` reviewer receipt, or why each is not applicable;
- whether it will resume, use `$ticket`, use `$brave-search`, use
  `$webgpt`/`$ask`, or ask the human for a legitimate blocker.

If the transcript or project state references an issue number, issue URL,
`$ticket`, "filed ticket", "assigned ticket", "close the ticket", or equivalent
ticket language, the restarted agent must use the real `$ticket` runtime before
asking the human. If the ticket is open and in scope, the agent must lease it,
diagnose it from repository evidence, apply the focused fix, run deterministic
proof, attach proof, close it, and read back the closed state. If the ticket is
not applicable, already closed, outside scope, or blocked by missing authority,
the agent must say so in `Ticket Check:` with the lookup evidence.

Completion claims are fail-closed. `ACHIEVED_WITH_RECEIPT` and
`DONE_WITH_RECEIPT` are allowed only when the current answer names a concrete
existing local receipt/artifact path that is inside the pane's project boundary
and identifies the command or verification result proving the immutable goal. A
partial checkpoint, advisory reviewer response, screenshot for only one
surface, or receipt that proves a subtask must be reported as `Immutable Goal:
NOT_MET` with `Disposition: RESUMING_NOW`. The classifier also rejects bare
`DONE_WITH_RECEIPT` lines and non-existent or out-of-project receipt paths.

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

The prompt tells the agent to use the real `$ticket`, `$brave-search`,
`$webgpt`, or `$ask` runtime if that is the next unblock step, and to stop and
ask the human only when the blocker is a real missing decision, credential,
authority, or external state.

## Cron

Install the 10 minute cron line:

```bash
skills/monitor-herdr/run.sh install-cron --apply
```

The installed cron is marked with:

```text
# monitor-herdr herdr cron
```

It runs `tick --apply` every 10 minutes and appends output to the skill log
directory. The installed cron defaults to `--min-stopped-seconds 600`, so a
freshly stopped pane normally has to remain stopped across the 10-minute cadence
before the monitor types into it. Re-running `install-cron --apply` replaces
the existing marked line.

`run.sh status` reports `scheduler.status`, `latest_receipt`, and
`latest_cron_receipt`. If cron is installed but no cron-sourced receipt exists,
the scheduler status is `NEEDS_ATTENTION`; do not treat a manual `tick` or live
eval receipt as proof that cron is healthy.

## Herdr Plugin

The skill includes a native Herdr plugin wrapper under:

```text
skills/monitor-herdr/herdr-plugin/herdr-plugin.toml
```

Link it for local use:

```bash
herdr plugin link skills/monitor-herdr/herdr-plugin
herdr plugin action list --plugin agent-skills.monitor-herdr
```

The plugin actions are thin launchers around `run.sh`: status, dry-run tick,
apply tick, and current-pane prompt probe. They do not duplicate monitor logic.

## Proof Boundaries

Report `mocked` and `live` explicitly:

- Fixture tests prove parsing, selection, cooldown, prompt construction, and
  crontab rendering only.
- `evals/test_real_world_e2e.py` exercises deterministic Herdr-like socket
  flows through pane selection, prompt transport, receipt status, false-positive
  suppression, stopped-age gating, Herdr idle-age field preference, and
  typed-but-not-submitted failure accounting.
- `evals/live_herdr_e2e.py` is the opt-in live Herdr eval. It runs the real
  `run.sh tick` command against the active Herdr socket, writes a JSON report
  under `/mnt/storage12tb/skills/monitor-herdr/outputs/live-e2e/`, and can
  optionally require an applied prompt with `submit_confirmed:true`.
- `evals/live_plugin_e2e.py` is the opt-in live Herdr plugin eval. It links the
  local plugin, lists actions, invokes the status action, waits for the specific
  Herdr plugin log id, and requires `status:succeeded` with `exit_code:0`.
- A dry-run `tick` proves Herdr can be observed and receipts can be written.
- An applied `tick --apply` proves the monitor attempted Herdr prompt transport
  and records both API results and post-Enter submission evidence. Treat
  `api_sent:true` without `submit_confirmed:true` as a transport failure that
  still needs attention.
- A sent probe is not proof that an agent correctly unblocked itself; the next
  proof is the agent's own receipt, status artifact, or human decision.
