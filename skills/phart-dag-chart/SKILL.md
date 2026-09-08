---
name: phart-dag-chart
description: >
  Render useful terminal charts from DAG contracts or typed execution receipts. For actual runs,
  project receipt-backed operational workflows such as ticket → routing → execution → proof →
  closure → final receipt instead of substituting the internal Tau handler DAG. Also validates
  ask/scillm/Tau DAG JSON and watches Tau dag-progress.json. Python 3.14+ with PHART.
allowed-tools: Bash, Read
triggers:
  - render dag chart
  - dag ascii chart
  - render phart dag chart
  - validate dag json
  - dag decision tree
  - dry-run dag chart
  - chart this run
  - show actual run workflow
  - receipt workflow chart
  - project watchdog chart
  - ticket repair chart
  - show what happened
provides:
  - dag-ascii-chart
  - dag-validate
  - receipt-workflow-chart
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
display. Receipt workflow mode renders what an observed run did, starting with
`agent_skills.project_watchdog.tick_receipt.v1`. Watch mode is a lightweight
terminal monitor over Tau-authored `dag-progress.json`; it is not a replacement
for the live React Flow viewer.

## Contract

| Input | Output |
|-------|--------|
| Valid `ask.dag.v1`, `scillm.exec.graph.v1`, or `tau.dag_contract.v1` JSON | `chart --view structure` → fenced ASCII decision tree on stdout |
| Valid `agent_skills.project_watchdog.tick_receipt.v1` receipt | `chart --view auto` → receipt-backed workflow chart on stdout |
| Invalid JSON / schema / cycle / unknown dep / mismatched evidence | stderr `error [code]: …` + optional `hint:`; exit **1** |
| Missing file / bad usage | exit **2** |
| Tau DAG JSON + `dag-progress.json` | `watch` → compact status + optional ASCII graph, refreshed until terminal state |

No raw Python tracebacks for expected failures.

## Commands

```bash
./run.sh validate plans/my.dag.json
./run.sh validate plans/my.dag.json --json
./run.sh chart plans/my.dag.json
./run.sh chart plans/my.dag.json --show-meta --compact-loops
./run.sh chart receipts/project-watchdog-.../receipt.json --evidence repair-proof-gate.json --evidence agentic-eval.json --plain
./run.sh watch plans/my.dag.json --progress /tmp/tau-run/dag-progress.json
./run.sh watch plans/my.dag.json --run-dir /tmp/tau-run --once --no-chart
```

## Default chart projection

`chart` defaults to `--view auto`.

Use **workflow** view when the input is a typed execution receipt or the request is about an actual run, ticket, classification, repair, proof, closure, or final receipt. If both a Tau/Ask DAG and receipts exist, receipts win; the DAG is supporting evidence about one execution phase.

Use **structure** view when the user explicitly asks for handlers, dependencies, fanout, joins, retries, planned topology, or when the only authoritative input is a DAG contract.

Never satisfy an actual-run request by rendering only the internal Ask/Tau handler DAG. Presence in a plan proves configuration. Presence in a receipt proves observation. A typed proof artifact proves only the assertion it validates.

Workflow mode must not infer:
- filing mechanism from GitHub author alone;
- model identity from handler identity alone;
- PASS/READY/trial counts from artifact existence;
- ticket closure from `status=COMPLETED` without `ticket_closed=true`;
- historical run state from current GitHub state.

## Composed by

- **$ask** — dry-run and `format_dag_ascii_chart()` prefer this skill (`phart-git` renderer) before in-process PyPI fallback.

## Validation messages

Aligned with `$ask` `validate_ask_dag` for structure (schema, node ids, types, depends_on, cycles). Chart mode skips skill registry checks; warns on empty `skill.run` or join nodes without `depends_on`.

`chart --show-meta` includes available node metadata in labels: `agent`, `model`, `skills`, executor, and retry count. `chart --compact-loops` collapses repeated `*-1`, `*-2`, `*-3` attempt chains into a bounded loop node while preserving the max iteration count and creator/reviewer model and skill metadata.

For Tau visual loops, distinguish product-quality control flow from app/tool failures. A reviewer verdict such as `visual_gate_not_ready` stays inside the bounded visual loop and may end at `visual-not-ready-after-max`. Runtime or contract failures from any node belong in top-level `on_error` metadata and render as a concurrent `global-error-sidecar` with the route `triage-error -> ticket -> project-watchdog -> agentic-evals`.

## Requirements

- **Python ≥3.14** (PHART 1.5 git rev pinned in `pyproject.toml` / `uv.lock`)
- **uv** for `./run.sh`

## Common mistakes

- Passing a directory instead of a `.json` file → `error [not_a_file]`.
- Duplicate node ids or dependency cycles → validation exit **1** with `hint:` (no Python traceback).
- Expecting PHART 1.5 on Python 3.12 → use `$ask` in-process PyPI fallback; this skill needs **3.14+**.
- Treating `watch` as the source of truth → wrong. Tau `dag-progress.json` / receipts are authoritative; `watch` only renders them.
- Trying to make terminal PHART match React Flow → too noisy. Keep the terminal view compact: state, active/completed/blocked nodes, last event, and optional ASCII structure.
