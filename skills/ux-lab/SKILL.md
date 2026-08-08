---
name: ux-lab
description: Launch and validate canonical UX Lab adapters and shared UI owned by agent-skills.
allowed-tools: Bash, Read
triggers:
  - ux lab
  - launch ux lab
  - validate ux lab
provides:
  - task-orchestration
composes:
  - agentic-evals
complies:
  - best-practices-skills
disciplines:
  - ui-design-engineering
---

# ux-lab

Canonical UX Lab shared UI source is `agent-skills/skills/ux-lab/ui`.
Canonical UX Lab project housing is `agent-skills/skills/ux-lab/projects.v1.json`.
UX Lab is a light multi-project wrapper: it discovers project surfaces, serves
a small project hub, and delegates runtime ownership to each project.

Canonical Sparta Explorer source and runtime ownership remains
`experiments/sparta/explorer`. Canonical Tau DAG viewer source and runtime
ownership remains `experiments/tau`.

Canonical Persona Dream source and runtime ownership remains
`agent-skills/skills/persona-dream`. UX Lab must list Persona Dream as a
first-class project even when the legacy `http://127.0.0.1:3002/#dream` route
is not mounted by the currently running project app.

For Tau DAG viewing, this skill is a launcher and capability-check wrapper
only. It contains no Tau DAG React application, DAG schemas, journal reader,
or state reducer.

- Start UX Lab project hub: `./run.sh` or `./run.sh serve`
- List project surfaces: `./run.sh list`
- Print a project URL: `./run.sh url persona-dream hub`
- Check project registry status: `./run.sh status`
- Start a project-owned runtime: `./run.sh start-project sparta-explorer`
- Launch Tau DAG viewer: `./run.sh tau-dag-view --run-dir /path/to/run`
- Validate ownership and endpoint: `./sanity.sh`
- Validate shared UI package: `cd ui && npm ci && npm run typecheck`
- UI hub: `http://127.0.0.1:3002/`
- Persona Dream hub card: `http://127.0.0.1:3002/?project=persona-dream`
- Sparta Explorer UI: `http://127.0.0.1:3002/#sparta-explorer/threat-matrix`
- API: `http://127.0.0.1:3001/api/f36/explorer-projection`

The Tau wrapper validates `tau.dag_viewer_capabilities.v1` with
`read_only: true`, then delegates unchanged to `tau dag-view`. Any discrepancy
is resolved in favor of Tau's emitted contracts.

See [`references/tau-dag-viewer.md`](references/tau-dag-viewer.md).
