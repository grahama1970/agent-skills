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
- has a live real-Codex transport receipt showing `submit_confirmed:true`.

Status: NEEDS_ATTENTION: receipts/idle-age-gate-20260721T1154Z.json

Remaining live gate: run the live apply eval against a Herdr space with at
least one eligible selected pane and require `submit_confirmed:true`.
