---
name: learn-datalake
description: >
  User-facing continuous datalake learning orchestrator.
  Watches a directory, runs review-pdf quality loops for PDFs, and ingests
  non-PDF assets into graph memory for multi-hop traversal.
allowed-tools: [Bash, Read, Write, Glob, Grep]
triggers:
  - learn datalake
  - continuous datalake learning
  - ingest directory to memory
  - watch corpus and learn
metadata:
  short-description: Continuous directory-to-memory learning with PDF QC gates
  version: "0.5.0"
  note: >
    New PDFs automatically get control extraction via extractor s12_framework_mapper.
    Creates chunk_control_edges and requirement_control_edges in ArangoDB, enabling
    /memory recall to traverse from document chunks to framework controls (NIST, CWE,
    ATT&CK, SPARTA, D3FEND, ISO). Existing chunks backfilled via
    scripts/backfill_chunk_control_edges.py (86,552 edges from 2.2M chunks).
    
    NEW in 0.5.0: Autonomous requirement-to-control matching via /match-requirement.
    When --match-requirements is enabled, extracted requirement chunks are automatically
    compared to SPARTA controls (NIST, ISO, SPARTA) using /create-evidence-case for
    validation and /lean4-prove for formal equivalence classification. Results are
    persisted to requirement_control_edges with relationship_type (refines, equivalent,
    partial_coverage, conflicts). Low-confidence matches are flagged for human review.

provides:
  - learn-datalake
composes:
  - review-pdf
  - memory
  - dogpile
  - task-monitor
  - match-requirement
  - create-evidence-case
  - lean4-prove
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# learn-datalake

`learn-datalake` is the user-facing orchestrator for large document corpora.

It composes:

- `review-pdf` for extractor quality/regression control on PDFs
- `memory` for graph ingestion
- `taxonomy` for federated bridge tags

## Quick Start

```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/learn-datalake

# One-shot run over a directory
./run.sh once /mnt/storage12tb/extractor_corpus --target-score 0.95

# Coverage assessment for sector gap analysis
./run.sh assess-coverage /mnt/storage12tb/extractor_corpus --target-pdf-per-sector 500

# Plan and execute gap-filling downloads
./run.sh plan-gap-download /mnt/storage12tb/extractor_corpus \
  --target-pdf-per-sector 500 \
  --execute-fetch

# Continuous watch mode
./run.sh start /mnt/storage12tb/extractor_corpus \
  --target-score 0.95 \
  --poll-seconds 300 \
  --task-monitor \
  --watchdog-seconds 900

# Parallel workers (8 workers for Threadripper 3960X)
./run.sh start /mnt/storage12tb/extractor_corpus --workers 8

# Env var fallback
LEARN_DATALAKE_WORKERS=8 ./run.sh start /mnt/storage12tb/extractor_corpus

# Managed supervisor + sidecar monitor (recommended for multi-day runs)
./run.sh start-supervised /mnt/storage12tb/extractor_corpus \
  --label corpus \
  --task-monitor \
  --task-monitor-project datalake_training

# Status/stop operators
./run.sh status-supervised --label corpus
./run.sh stop-supervised --label corpus
```

## Commands

- `once`: one audit-and-ingest pass.
- `start`: continuous loop for PDFs plus non-PDF ingestion.
- `ingest-non-pdf`: memory ingest for non-PDF files only.
- `assess-coverage`: compute current corpus coverage by sector and content type.
- `plan-gap-download`: generate URL manifest for sector gaps and optionally run fetcher.
- `quarantine-ui`: start the datalake quarantine review UI (FastAPI, default port 8004).
- `review-quarantine`: review quarantined documents (delegates to learn_datalake.py).
  - Default fetch output is sector-scoped under the corpus root:
    - `arxiv/expansion_batch_<n>`
    - `dtic/expansion_batch_<n>`
    - `faa/expansion_batch_<n>`
    - `nasa/expansion_batch_<n>`
    - `nist/expansion_batch_<n>`
    - `ietf/expansion_batch_<n>`
    - `industry/expansion_batch_<n>`
    - `adversarial/expansion_batch_<n>`
    - `edge_cases/expansion_batch_<n>`
  - `--fetch-output-dir` is treated as a base directory and remains sector-scoped under that base.

## Task Monitor + Watchdog

- `once`, `start`, and `plan-gap-download --execute-fetch` register tasks in `task-monitor`.
- Session lifecycle is automatic (`start-session` and `end-session`) and accomplishments are appended per cycle.
- State files are written under:
  - `state/task_monitor/learn_datalake_once_*.json`
  - `state/task_monitor/learn_datalake_start_*.json`
  - `state/task_monitor/learn_datalake_gap_fetch.json`
- Watchdog is enabled by default:
  - `--watchdog-seconds`: hard-fail when a long subprocess has no output for N seconds.
  - `--watchdog-poll-seconds`: heartbeat interval for watchdog and task state updates.
- `task-monitor` integration is strict by default (`--task-monitor-strict`) and fails loudly if monitor commands are unavailable.

## Active Supervision (Monitor + Diagnose + Resume)

Use the supervisor entrypoint for unattended runs. It continuously:

- monitors heartbeat and child liveness,
- diagnoses failures into buckets,
- writes diagnostics artifacts,
- restarts automatically with backoff.

Use `run.sh` wrappers for stable process lifecycle:

- `start-supervised`: starts supervisor and sidecar monitor with detached sessions.
- `status-supervised`: prints supervisor state, heartbeat, latest sidecar report, and numeric progress counters:
  - `corpus_pdf_count`
  - `corpus_profile_count`
  - `run_discovered_profiles_count`
  - `run_scanned_max`
  - `run_new_extractions`
  - `run_last_extracted_pdf`
- `stop-supervised`: writes `STOP_<label>`, waits, and force-stops if needed.

Command:

```bash
cd /home/graham/workspace/experiments/pi-mono/.pi/skills/learn-datalake
./run.sh start-supervised /mnt/storage12tb/extractor_corpus/nasa \
  --label nasa \
  --task-monitor \
  --task-monitor-project datalake_training
```

Supervisor artifacts:

- state: `state/watchdogs/supervisor_<label>.json`
- diagnostics: `state/watchdogs/diagnostics/diagnostic_<label>_*.json`
- supervisor log: `state/watchdogs/supervisor_<label>.log`
- child run logs: `state/runs/learn_datalake_<label>_*.log`

Graceful stop:

- create stop file: `state/watchdogs/STOP_<label>`
- supervisor terminates child and exits cleanly on next poll.

## Parallel Workers

The `--workers N` flag runs N concurrent review-pdf workers, each processing a
disjoint subset of pending PDFs via symlink-based directory partitioning.

```bash
# Single-threaded (default, backward compatible)
./run.sh start /mnt/storage12tb/extractor_corpus

# 8 parallel workers (recommended for Threadripper 3960X)
./run.sh start /mnt/storage12tb/extractor_corpus --workers 8

# Supervised with parallel workers
./run.sh start-supervised /mnt/storage12tb/extractor_corpus --label corpus --workers 8

# Env var fallback (useful for systemd units)
LEARN_DATALAKE_WORKERS=8 ./run.sh start-supervised /mnt/storage12tb/extractor_corpus
```

- `--workers 0` (default): resolves from `LEARN_DATALAKE_WORKERS` env var, then auto-tunes
  based on current CPU load and available RAM (reads `/proc/meminfo` and `os.getloadavg()`).
  Each worker needs ~2 CPU cores and ~2 GB RAM. Reserves 25% CPU and 30% RAM for OS/services.
  Capped at 16 workers max.
- `--workers 1`: exact original sequential code path (backward compatible).
- `--workers N` (N > 1): discovers pending PDFs, partitions round-robin into N chunks,
  creates per-worker symlink directories, runs N review-pdf loops concurrently.
- Per-worker state files: `review_state_worker_{i}.json` — supervisor aggregates across all.
- Circuit breaker applies to aggregate failure rate across all workers.
- The `status-supervised` table includes a `workers` row showing the active count.

## Autonomous Requirement Matching (NEW in 0.5.0)

When enabled, `/learn-datalake` automatically matches extracted requirements to SPARTA
controls (NIST, ISO, SPARTA). This does the grunt work so security engineers can
refine rather than start from scratch.

### Enable Matching

```bash
# One-shot with requirement matching
./run.sh once /mnt/storage12tb/extractor_corpus --match-requirements

# Continuous with matching enabled
./run.sh start /mnt/storage12tb/extractor_corpus --match-requirements

# With confidence threshold for human review (default: 0.7)
./run.sh once /mnt/storage12tb/extractor_corpus --match-requirements --match-confidence 0.8
```

### Pipeline Flow

```
PDF → /extractor → chunks → /extract-controls → candidate edges
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │ /match-requirement (per chunk)│
                    │                               │
                    │ 1. /create-evidence-case      │
                    │    (validate requirement)     │
                    │                               │
                    │ 2. /create-evidence-case      │
                    │    (validate each control)    │
                    │                               │
                    │ 3. Same-technique check       │
                    │                               │
                    │ 4. /lean4-prove               │
                    │    (formal equivalence)       │
                    └───────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
              High confidence               Low confidence
              (>= threshold)                (< threshold)
                    │                               │
                    ▼                               ▼
          requirement_control_edges       pending_review collection
          with relationship_type          (human review queue)
```

### Output Collections

| Collection | Contents |
|------------|----------|
| `requirement_control_edges` | Verified matches with `relationship_type` |
| `pending_review` | Low-confidence matches for human refinement |
| `match_conflicts` | Detected conflicts (requirement contradicts control) |

### Human Review Queue

Low-confidence matches are queued in `pending_review`:

```bash
# List pending reviews
./run.sh review-queue

# Review in browser
./run.sh review-queue --ui

# Export to CSV for offline review
./run.sh review-queue --export reviews.csv
```

### Relationship Types

| Type | Meaning | Auto-Accept? |
|------|---------|--------------|
| `refines` | Requirement implements control | Yes (if confidence >= threshold) |
| `equivalent` | Same obligation | Yes |
| `partial_coverage` | Requirement covers subset | Queue for review |
| `conflicts` | Contradictory obligations | Flag as conflict |
| `unknown` | Proof failed | Queue for review |

### What Brandon Gets

Instead of manually tracing requirements to controls:

1. **Pre-matched edges** — Most requirement-control links are already established
2. **Conflict alerts** — Contradictory requirements flagged before integration testing
3. **Review queue** — Only edge cases need human judgment
4. **Audit trail** — Every match has evidence_case_id and proof_key for traceability

## Notes

- `review-pdf` remains the hard quality gate for extractor outputs.
- `start` mode keeps running and continues learning when new documents appear.
- non-PDF ingestion is routed via memory acquire so additional modalities can be added without changing this skill.
- coverage commands use existing `dogpile` URL corpora and `fetcher` to close sector gaps before extraction loops.
