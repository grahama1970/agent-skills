---
name: create-status-surface
description: >
  Create receipt-backed status surfaces and Tau DAG handoff contracts from local
  progress, gate, and checker receipts. Use when a workflow needs a global
  progress bar, evidence status board, local readiness surface, or robust Tau
  connection without claiming provider readiness or live completion.
triggers:
  - create status surface
  - status surface
  - global progress bar
  - receipt-backed progress
  - render progress receipt
  - tau status handoff
  - tau dag status surface
provides:
  - status-surface
  - receipt-backed-progress
  - tau-dag-status-contract
  - progress-tracking
composes:
  - tau
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - validation
  - orchestration
  - progress-tracking
  - evidence
disciplines:
  - observability-operations
  - agentic-orchestration
---

# Create Status Surface

Build local, receipt-backed status surfaces from machine-readable progress
artifacts. The skill is reusable across pipelines because it treats receipts as
source truth and renders derived surfaces only.

Default input:

```text
persona_dream.global_progress.v1
```

Outputs:

```text
status_surface.json
status_surface.html
status_surface_receipt.json
tau_status_surface_dag_contract.v1.json
tau_status_surface_dag_validation_receipt.json
```

## Hard Boundary

This skill never upgrades a local progress rollup into:

```text
provider readiness
manual acceptance
paid-call authorization
live provider submission
live Tau DAG execution
visual quality acceptance
```

It may create a Tau DAG contract for inspection or local orchestration handoff,
but that contract is not a Tau execution receipt.

## Commands

```bash
skills/create-status-surface/run.sh render \
  --input /path/to/global_progress.v1.json \
  --output-dir /tmp/status-surface \
  --title "Persona Dream"

skills/create-status-surface/run.sh validate \
  --surface /tmp/status-surface/status_surface.json \
  --receipt-out /tmp/status-surface/status_surface_validation_receipt.json

skills/create-status-surface/run.sh tau-dag \
  --surface-receipt /tmp/status-surface/status_surface_receipt.json \
  --output /tmp/status-surface/tau_status_surface_dag_contract.v1.json

skills/create-status-surface/run.sh tau-check \
  --dag /tmp/status-surface/tau_status_surface_dag_contract.v1.json \
  --receipt-out /tmp/status-surface/tau_status_surface_dag_validation_receipt.json

skills/create-status-surface/run.sh tau-doctor \
  --receipt-out /tmp/status-surface/tau_doctor_receipt.json
```

Run local sanity:

```bash
skills/create-status-surface/sanity.sh
```

## Tau Connection Rules

- Use `skills/tau/run.sh doctor` for non-mutating Tau wrapper connectivity.
- Generate `tau.dag_contract.v1` with explicit `goal_hash`, nodes, edges,
  terminal human node, limits, required evidence, and fail-closed invariants.
- Use `executor: local` for local status-surface commands and `executor: human`
  for the terminal boundary.
- Do not use `executor: provider`.
- Do not claim Tau execution unless a separate Tau DAG receipt exists.
- Do not create GitHub, provider, Herdr, or browser mutation claims from this
  skill.

## Proof Standard

For reports, include:

```text
mocked: no
live: no for local fixture rendering
actual_provider_call_attempts: 0
live_tau_dag_execution_started: false
```

`tau-doctor` is live only in the narrow sense that it invokes the local Tau
wrapper; it is still non-mutating and does not prove provider execution.
