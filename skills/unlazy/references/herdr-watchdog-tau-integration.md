# Herdr, Project Watchdog, Ticket, and Tau Integration

`unlazy` is the acceptance kernel. It should not become another scheduler,
ticket manager, Herdr monitor, or Tau runner.

Use one canonical `GATES.md` and one `unlazy.acceptance_ref.v1` for each
independently closable goal. Downstream systems carry references to the goal,
ledger, lock, and gate IDs; they do not copy gate commands into prose prompts.

## Acceptance Reference

Every ticket, Herdr work order, Tau DAG node, and watchdog receipt should carry:

```json
{
  "schema": "unlazy.acceptance_ref.v1",
  "goal_path": "skills/persona-dream/IMMUTABLE_GOAL.json",
  "goal_sha256": "sha256:<64 hex>",
  "ledger_path": "skills/persona-dream/GATES.md",
  "ledger_sha256": "sha256:<64 hex>",
  "lock_path": "skills/persona-dream/.agent/contracts/GATES.lock.json",
  "lock_sha256": "sha256:<64 hex>",
  "required_gate_ids": ["PD-HORUS-EMBRY-CHATTERBOX-AUDIO-LIVE"]
}
```

Validate a receipt boundary with:

```bash
skills/unlazy/run.sh receipt-check \
  --project-root /path/to/repo \
  /path/to/repo/path/to/receipt.json
```

`receipt-check` proves only binding and containment. It does not run gates,
judge the worker, or close the goal.

## Component Boundaries

- `$ticket`: stores target, lease, proof command, and `acceptance_ref`.
- `$project-watchdog`: dispatches and closes only after re-verifying the
  relevant gate IDs at current `HEAD`.
- `$ops-herdr`: sends work orders that assign gate IDs and `OWNS:` paths.
- `$monitor-herdr`: restarts stopped panes from the next unmet gate, not from
  transcript prose.
- `$tau`: references the same acceptance object from DAG contracts and node
  receipts; it does not duplicate acceptance logic.

Only a validated `project_watchdog.goal_completion.v1` receipt may support a
global `ACHIEVED_WITH_RECEIPT:path` claim. Gate receipts, Herdr receipts, Tau
terminal receipts, and reviewer prose remain subtask evidence.

## Avoid

- Do not copy `CHECK:` or `EXPECT:` into tickets, work orders, or prompts.
- Do not let a worker edit the approved goal, ledger, lock, schema, or verifier.
- Do not treat pane text, issue prose, `AGENTS.md`, `CLAUDE.md`, CI green,
  Tau exit zero, or an empty issue queue as completion proof.
- Do not use mocked fixtures to close live provider, audible audio, or dynamic
  conversation gates.
