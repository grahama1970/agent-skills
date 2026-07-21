# Immutable Goal

Provide `monitor-herdr` as a fail-closed Herdr monitor skill that:

- observes stopped agents in a named Herdr space;
- does not resume agents with no immutable goal;
- does not resume agents whose immutable goal is already achieved with receipt evidence;
- does not type into fallback-idle, blocked, unknown, approval, or ambiguous panes;
- prompts selected stopped agents with `$brave-search` and project-bound browser-oracle unblock instructions;
- supports a stopped-age gate through `--min-stopped-seconds`, using Herdr
  idle-age fields when available and monitor-owned first-observed-stopped state
  otherwise;
- installs a 10-minute cron for the `codex` Herdr space;
- includes deterministic evals for false positives, stopped-age gating, Herdr
  idle-age field preference, and failed/non-submitted prompt entry;
- includes opt-in live Herdr E2E evals that write machine-readable reports;
- has a live real-Codex transport receipt showing `submit_confirmed:true`;
- uses `herdr pane run` as the primary live submit transport so Enter is
  submitted atomically;
- exposes scheduler health that distinguishes cron receipts from manual or
  plugin receipts;
- includes a native Herdr plugin wrapper whose actions delegate to `run.sh`.

Status: ACHIEVED_WITH_RECEIPT:

- live apply eval report:
  `/mnt/storage12tb/skills/monitor-herdr/outputs/live-e2e/live-e2e-20260721T171728089240Z/report.json`
- live submit receipt:
  `/home/graham/.local/state/monitor-herdr/receipts/monitor-herdr-20260721T171728192864Z/receipt.json`
- live plugin eval report:
  `/mnt/storage12tb/skills/monitor-herdr/outputs/live-plugin-e2e/live-plugin-e2e-20260721T171718424807Z/report.json`

Post-merge operational gate: reinstall or refresh the production cron checkout
so the marked cron line runs this version and emits
`invocation_source:"cron"` receipts. Until then, `run.sh status` must report
scheduler health as `NEEDS_ATTENTION` instead of treating manual receipts as
cron proof.
