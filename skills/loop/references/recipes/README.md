# Loop Recipes

Recipes are prompt patterns for one bounded artifact loop. They are not a graph
engine and they do not replace Scillm DAG or project-agent orchestration.

Use this boundary:

```text
Multiple independent artifacts or project phases -> outer orchestrator.
One artifact needing inspect/produce/verify/repair -> $loop recipe.
```

Available recipes:

- `code-repair.md`
- `code-change.md`
- `read-only-preflight-fanout.md`
- `artifact-review.md`

Generic one-artifact runs may emit `receipt_type: "loop-run.v1"`, validated by
`../../scripts/validate_loop_run_receipt.py`. The schema lives at
`../loop-run.v1.schema.json`. That receipt is intentionally constrained and must
not be used as a multi-node project DAG schema.
