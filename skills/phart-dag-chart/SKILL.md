---
name: phart-dag-chart
description: >
  Validate ask/scillm/Tau DAG JSON, render PHART 1.5 ASCII decision-tree charts for terminals
  and dry-run output, and watch Tau dag-progress.json as a compact terminal status view.
  DAG.json in → chart/status on stdout or actionable errors on stderr (no tracebacks).
  Python 3.14+ with PHART from github.com/scottvr/phart.
allowed-tools: Bash, Read
triggers:
  - render dag chart
  - dag ascii chart
  - render phart dag chart
  - validate dag json
  - dag decision tree
  - dry-run dag chart
provides:
  - dag-ascii-chart
  - dag-validate
  - tau-dag-terminal-watch
composes:
  - agentic-evals
taxonomy:
  - precision
  - validation
disciplines:
  - agentic-orchestration
  - developer-tooling
---

# phart-dag-chart

Structural validation and PHART rendering for **ask.dag.v1**, with
**scillm.exec.graph.v1** and **tau.dag_contract.v1** inputs normalized for
display. Watch mode is a lightweight terminal monitor over Tau-authored
`dag-progress.json`; it is not a replacement for the live React Flow viewer.

## Contract

| Input | Output |
|-------|--------|
| Valid `ask.dag.v1`, `scillm.exec.graph.v1`, or `tau.dag_contract.v1` JSON | `chart` → fenced ASCII decision tree on stdout |
| Invalid JSON / schema / cycle / unknown dep | stderr `error [code]: …` + optional `hint:`; exit **1** |
| Missing file / bad usage | exit **2** |
| Tau DAG JSON + `dag-progress.json` | `watch` → compact status + optional ASCII graph, refreshed until terminal state |

No raw Python tracebacks for expected failures.

## Commands

```bash
./run.sh validate plans/my.dag.json
./run.sh validate plans/my.dag.json --json
./run.sh chart plans/my.dag.json
./run.sh watch plans/my.dag.json --progress /tmp/tau-run/dag-progress.json
./run.sh watch plans/my.dag.json --run-dir /tmp/tau-run --once --no-chart
```

## Composed by

- **$ask** — dry-run and `format_dag_ascii_chart()` prefer this skill (`phart-git` renderer) before in-process PyPI fallback.

## Validation messages

Aligned with `$ask` `validate_ask_dag` for structure (schema, node ids, types, depends_on, cycles). Chart mode skips skill registry checks; warns on empty `skill.run` or join nodes without `depends_on`.

## Requirements

- **Python ≥3.14** (PHART 1.5 git rev pinned in `pyproject.toml` / `uv.lock`)
- **uv** for `./run.sh`

## Common mistakes

- Passing a directory instead of a `.json` file → `error [not_a_file]`.
- Duplicate node ids or dependency cycles → validation exit **1** with `hint:` (no Python traceback).
- Expecting PHART 1.5 on Python 3.12 → use `$ask` in-process PyPI fallback; this skill needs **3.14+**.
- Treating `watch` as the source of truth → wrong. Tau `dag-progress.json` / receipts are authoritative; `watch` only renders them.
- Trying to make terminal PHART match React Flow → too noisy. Keep the terminal view compact: state, active/completed/blocked nodes, last event, and optional ASCII structure.
