---
name: ux-lab
description: Launch and validate canonical UX Lab adapters and shared UI owned by agent-skills.
allowed-tools: Bash, Read
---

# ux-lab

Canonical UX Lab shared UI source is `agent-skills/skills/ux-lab/ui`.

Canonical Sparta Explorer source and runtime ownership remains
`experiments/sparta/explorer`. Canonical Tau DAG viewer source and runtime
ownership remains `experiments/tau`.

For Tau DAG viewing, this skill is a launcher and capability-check wrapper
only. It contains no Tau DAG React application, DAG schemas, journal reader,
or state reducer.

- Start Sparta Explorer: `./run.sh`
- Launch Tau DAG viewer: `./run.sh tau-dag-view --run-dir /path/to/run`
- Validate ownership and endpoint: `./sanity.sh`
- Validate shared UI package: `cd ui && npm ci && npm run typecheck`
- UI: `http://127.0.0.1:3002/#sparta-explorer/threat-matrix`
- API: `http://127.0.0.1:3001/api/f36/explorer-projection`

The Tau wrapper validates `tau.dag_viewer_capabilities.v1` with
`read_only: true`, then delegates unchanged to `tau dag-view`. Any discrepancy
is resolved in favor of Tau's emitted contracts.

See [`references/tau-dag-viewer.md`](references/tau-dag-viewer.md).
