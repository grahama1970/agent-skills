---
name: phart-dag-chart
description: >
  Validate ask/scillm DAG JSON and render PHART 1.5 ASCII decision-tree charts for terminals
  and dry-run output. DAG.json in → chart on stdout or actionable errors on stderr (no tracebacks).
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
composes: []
taxonomy:
  - precision
  - validation
---

# phart-dag-chart

Structural validation and PHART rendering for **ask.dag.v1** (and **scillm.exec.graph.v1** input normalized for display).

## Contract

| Input | Output |
|-------|--------|
| Valid `dag.json` | `chart` → fenced ASCII decision tree on stdout |
| Invalid JSON / schema / cycle / unknown dep | stderr `error [code]: …` + optional `hint:`; exit **1** |
| Missing file / bad usage | exit **2** |

No raw Python tracebacks for expected failures.

## Commands

```bash
./run.sh validate plans/my.dag.json
./run.sh validate plans/my.dag.json --json
./run.sh chart plans/my.dag.json
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
