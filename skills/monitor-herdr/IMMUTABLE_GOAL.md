# Immutable Goal

Provide `monitor-herdr` as a fail-closed Herdr monitor skill that:

- observes stopped agents in a named Herdr space;
- does not resume agents with no immutable goal;
- does not resume agents whose immutable goal is already achieved with receipt evidence;
- does not type into fallback-idle, blocked, unknown, approval, or ambiguous panes;
- prompts selected stopped agents with `$brave-search` and project-bound browser-oracle unblock instructions;
- installs a 10-minute cron for the `codex` Herdr space;
- includes deterministic evals for false positives and failed/non-submitted prompt entry;
- has a live real-Codex transport receipt showing `submit_confirmed:true`.

Status: ACHIEVED_WITH_RECEIPT: receipts/immutable-goal-completion-20260721T0217Z.json
