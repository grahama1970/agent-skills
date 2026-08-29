# phart-dag-chart

> **Disciplines:** agentic-orchestration · developer-tooling

Validate **ask.dag.v1** / **scillm.exec.graph.v1** / **tau.dag_contract.v1** JSON, render PHART 1.5 ASCII decision-tree charts, and watch Tau `dag-progress.json` as a compact terminal status view.

## Requirements

- [uv](https://github.com/astral-sh/uv)
- Python **3.14+** (`uv python install 3.14`)

## Commands

```bash
./run.sh validate path/to/plan.dag.json
./run.sh validate path/to/plan.dag.json --json
./run.sh chart path/to/plan.dag.json
./run.sh watch path/to/plan.dag.json --progress /tmp/tau-run/dag-progress.json
./run.sh watch path/to/plan.dag.json --run-dir /tmp/tau-run --once --no-chart
./sanity.sh
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation, render, terminal DAG failure, or watch timeout (`error [code]:` on stderr) |
| 2 | Missing uv or bad usage |

## Boundaries

- React Flow remains the rich live DAG UX.
- `watch` is a terminal fallback for agents/operators who need a simple loop until Tau reaches `PASS`, `FAIL`, `BLOCKED`, or `NEEDS_ATTENTION`.
- Tau `dag-progress.json` / receipts are authoritative; this skill only renders them.

## Composed by

- **$ask** — dry-run and `format_dag_ascii_chart()` call this skill before in-process PyPI fallback.

## Storage

Local `.venv` should be a symlink to `/mnt/storage12tb/skills/phart-dag-chart/.venv` on this workstation (see `scripts/ensure_venv.sh`).
