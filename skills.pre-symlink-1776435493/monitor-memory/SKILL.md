---
name: monitor-memory
description: >
  Nightly orchestrator that verifies the full memory pipeline is healthy.
  Composes existing skills (ops-arango, taxonomy, persona-journal, monitor-personas,
  assess, create-walkthrough) into 25 probes across 6 tiers. Delegates all work,
  never reimplements skill logic.
triggers:
  - monitor memory
  - memory health
  - check memory pipeline
  - nightly health check
  - memory probes
  - run memory monitor
allowed-tools: Bash
metadata:
  short-description: Nightly memory & system health orchestrator

provides:
  - monitor-memory
composes: [task-monitor]
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Monitor Memory

Composed orchestrator that delegates to existing skills and reports a unified
health picture across memory, personas, projects, and infrastructure.

## Continuous Operation (Non-Negotiable)

This skill is **always-on**. It:
- Runs on its configured schedule indefinitely — it NEVER stops unless explicitly halted by the user
- The agent MUST NOT stop and wait for the human to ask for status or remember to check
- If a cycle fails, diagnose the failure, attempt auto-repair, and continue
- Only escalate to the human if genuinely blocked after exhausting /dogpile research
- Gracefully handles restarts and maintains state across cycles
- Is designed for multi-day/week/month autonomous operation

**Anti-pattern**: Reporting status and waiting for the human to ask "what next?" is UNACCEPTABLE. The agent must proactively fix issues and continue the monitoring loop.

## Architecture

```
monitor-memory check [--tier N] [--probe NAME] [--json]
│
├── TIER 1: Memory & Data Health (auto-fix safe)
│   ├── P01 embedding-coverage
│   ├── P02 taxonomy-coverage
│   ├── P03 source-qra-coverage
│   ├── P04 taxonomy-drift
│   ├── P10 backup-freshness
│   ├── P11 edge-staleness
│   ├── P12 duplicate-detection
│   ├── P25 orphaned-lessons
│   ├── P26 heuristic-taxonomy
│   ├── P27 taxonomy-evolution
│   ├── P28 universal-embedding-coverage
│   └── P29 local-memory-sync
│
├── TIER 2: Persona Lifecycle (report only)
│   ├── P05 journal-completeness
│   ├── P06 dream-completeness
│   ├── P07 content-scan
│   ├── P14 scope-growth
│   ├── P15 feed-freshness
│   └── P16 episodic-health
│
├── TIER 3: Integration Smoke Tests (detect + dispatch)
│   └── P20 persona-smoke-test
│
├── TIER 4: Project Health (heavyweight, runs last)
│   ├── P08 project-assess
│   └── P09 project-walkthrough
│
└── TIER 5: Infrastructure (lightweight)
    ├── P13 embedding-service
    ├── P17 disk-usage-12tb
    ├── P18 scheduler-audit
    └── P19 security-freshness
```

## Commands

```bash
# Run all probes
./run.sh check --json

# Run a specific tier
./run.sh check --tier 1 --autofix --json

# Run a single probe
./run.sh check --probe embedding-coverage --json

# Manual fix
./run.sh fix embedding-coverage

# Dashboard
./run.sh dashboard

# Register nightly schedule
./run.sh register-nightly

# Help
./run.sh help
```

## Nightly Schedule

| Time  | Job                      | Description                          |
|-------|--------------------------|--------------------------------------|
| 04:45 | docs-update-arangodb     | Pull latest ArangoDB docs into /memory |
| 05:00 | monitor-memory T1        | Memory & data health + auto-fix      |
| 05:15 | monitor-memory T2        | Persona lifecycle checks             |
| 05:30 | monitor-memory T3        | Persona smoke tests                  |
| 05:45 | monitor-memory T5        | Infrastructure                       |
| 06:00 | monitor-memory T4        | Project assess + walkthrough         |

Runs after all upstream pipelines (monitor-personas at 02:00, journals at 03:00,
episodic archiver at 04:00) so it can verify they completed.

The docs-update jobs pull latest documentation from upstream repos into /memory
via best-practices-* skills. As more best-practices skills add doc ingestion,
their update jobs should be registered here at 04:45-04:59.

## Environment Variables

| Variable              | Default                     | Description              |
|-----------------------|-----------------------------|--------------------------|
| `ARANGO_URL`          | `http://127.0.0.1:8529`    | ArangoDB endpoint        |
| `ARANGO_DB`           | `memory`                    | Database name            |
| `ARANGO_USER`         | `root`                      | Database user            |
| `ARANGO_PASS`         | (empty)                     | Database password        |
| `EMBEDDING_SERVICE_URL` | `http://localhost:8080`   | Embedding FastAPI        |
| `MEMORY_PROJECT_PATH` | `/home/graham/.../memory`  | Memory project root      |

## Auto-Fix (Tier 1 only)

Safe auto-fix actions that are idempotent and non-destructive:

- **embedding-coverage**: Calls `ops-arango embeddings --fix`
- **backup-freshness**: Triggers `ops-arango dump`
- **edge-staleness**: Runs `memory-agent propose`
- **duplicate-detection**: Runs `ops-arango duplicates --fix`
- **taxonomy-coverage**: Flags for manual review

## State

Reports and state written to `~/.pi/monitor-memory/`:
- `report_t{1-5}.json` — Latest tier reports
- `task_state.json` — Task-monitor integration state
