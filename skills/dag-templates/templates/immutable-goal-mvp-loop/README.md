# Immutable Goal MVP Loop

Use this primitive when an agent has an immutable goal and must move through
small, reviewable MVPs instead of retrying broadly.

## Shape

1. Freeze the human-approved goal and hash.
2. Decompose the goal into focused MVPs.
3. Implement exactly one MVP.
4. Review the MVP against the immutable goal.
5. If the review passes, audit and report.
6. If blocked, confused, or thrashing, run `$brave-search`.
7. If still blocked after search, run `$ask`.
8. Audit or stop with receipts.

## Required Slots

- `dag_id`
- `goal_id`
- `goal_hash`
- `immutable_goal`
- `target_repo`
- `target`

## Artifacts

- `dag.tau.dag.json` is the canonical Tau contract.
- `ask-prompt.md` is the prompt packet to use with `$ask` or Tau.
- `phart-dag-chart.txt` is the rendered chart for quick inspection.
- `agentic_eval.json` guards materialization and chart rendering for this primitive.

Agents must materialize a copy with `../../run.sh materialize` and must not edit
this canonical DAG for a project-specific run.
