# phart-dag-chart

Validate **ask.dag.v1** / **scillm.exec.graph.v1** JSON and render PHART 1.5 ASCII decision-tree charts.

## Requirements

- [uv](https://github.com/astral-sh/uv)
- Python **3.14+** (`uv python install 3.14`)

## Commands

```bash
./run.sh validate path/to/plan.dag.json
./run.sh validate path/to/plan.dag.json --json
./run.sh chart path/to/plan.dag.json
./sanity.sh
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Validation or render error (`error [code]:` on stderr) |
| 2 | Missing uv or bad usage |

## Composed by

- **$ask** — dry-run and `format_dag_ascii_chart()` call this skill before in-process PyPI fallback.

## Storage

Local `.venv` should be a symlink to `/mnt/storage12tb/skills/phart-dag-chart/.venv` on this workstation (see `scripts/ensure_venv.sh`).
