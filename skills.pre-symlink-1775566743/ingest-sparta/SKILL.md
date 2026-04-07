---
name: ingest-sparta
description: >
  Thin wrapper around the SPARTA pipeline project (79K LOC Python).
  Runs pipeline steps, checks status, runs tests, launches Explorer UX.
  The real code lives at ~/workspace/experiments/sparta/src/sparta/pipeline/ —
  this skill is an interface, not a reimplementation.
project-path: /home/graham/workspace/experiments/sparta
triggers:
  - ingest sparta
  - sparta ingestion
  - sparta explorer
  - run sparta pipeline
  - sparta pipeline step
  - sparta status
provides:
  - sparta-ingestion
  - sparta-pipeline
composes:
  - ux-lab
  - memory
  - task-monitor
taxonomy:
  - precision
  - resilience
  - ingestion
  - security
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /ingest-sparta

Thin skill wrapper around the real SPARTA pipeline at
`/home/graham/workspace/experiments/sparta/`.

## What This Skill Does

Dispatches commands to the real pipeline. Does NOT contain pipeline logic.

## What the Real Pipeline Does

48 numbered Python steps (27K+ LOC) that:
1. Fetch SPARTA-Data.xlsx + ATT&CK + CWE + D3FEND + NIST + ESA sources
2. Extract and normalize 2,147+ controls across 6 frameworks
3. Fetch ~10K URLs referenced by controls
4. Extract clean text from fetched HTML/PDF
5. Generate embeddings and knowledge anchors
6. Build relationship graph (deterministic + LLM-verified edges)
7. Generate QRAs with T0/T1.5/T2 quality cascade
8. Calibrate confidence thresholds via active learning
9. Export tiered graph

Data stored in DuckDB (358MB production DB) + ArangoDB (via SpartaDataBridge).

DuckDB migration to ArangoDB complete for pipeline steps (commit f8c5be4d).
DuckDB remains as read-only data layer via SpartaDataBridge.

## Commands

```bash
# Run a specific pipeline step
./run.sh step 03 --run-id myrun --limit 100
./run.sh step 12 --run-id myrun
./run.sh step 05d --run-id myrun --dry-run

# List all available steps
./run.sh steps

# Pipeline health check
./run.sh status

# Run tests (486 tests)
./run.sh test
./run.sh test -k "test_qra"

# Launch Explorer UX (Vite :3002 + Express API :3001)
./run.sh explorer
./run.sh explorer --no-browser
```

## Pipeline Steps (real, in src/sparta/pipeline/steps/)

| Step | Name | What It Does |
|------|------|-------------|
| 00 | fetch_sources | Download SPARTA xlsx, ATT&CK JSON, CWE XML |
| 01 | extract_worksheets | Parse SPARTA spreadsheet into structured data |
| 01b | load_external | Import ATT&CK, CWE, D3FEND, NIST data |
| 02 | url_inventory | Build URL manifest from controls |
| 03 | fetch_urls | Download referenced URLs (ArangoDB) |
| 04 | extract_controls | Extract control metadata |
| 04b | controls_audit | Audit control extraction quality |
| 05 | extract_knowledge | Extract text from fetched content |
| 05b | extraction_audit | Audit extraction quality |
| 05d | chunk_url_content | Section-aware content chunking |
| 06 | embed_knowledge | Generate 384-dim embeddings |
| 07 | knowledge_anchors | Entity grounding |
| 08 | relationships | Deterministic edge creation |
| 09 | relationships_llm | LLM-verified relationship edges |
| 10 | extract_features | Feature extraction |
| 11 | parameter_discovery | Parameter discovery |
| 12 | qra | QRA generation with quality cascade |
| 12b | qra_audit | QRA quality audit |
| 13-55 | calibration | Threshold calibration, active learning, export |
| 60-61 | technique_knowledge | Build technique knowledge corpus (new) |

## Explorer UX

8-tab React UI for SPARTA pipeline transparency. Launch via `./run.sh explorer`.

- **Frontend**: Vite on `:3002` — renders `SpartaExplorer` with 8 view components
- **API proxy**: Express on `:3001` — proxies `/api/memory/*` to daemon Unix socket
- **Data**: ArangoDB via memory daemon (11K controls, 218K QRAs, 131K relationships)

Views: Overview, Sources, Controls, URLs, Knowledge, QRAs, Relationships, Pipeline.
Keyboard: press 1-8 to switch tabs.

Components at `pi-mono/packages/ux-lab/src/components/sparta/explorer/`.

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `/sparta-review` | Brandon persona assessment of QRA quality |
| `/reality-check-sparta` | Adversarial data quality verification |
| `/monitor-sparta` | Continuous T0/T1.5/T2 quality monitoring |
| `/data-audit` | DuckDB coverage report (Control→URL→Knowledge→QRA) |
| `/qra-review` | Human-in-the-loop QRA accept/reject TUI |
| `/sparta-stress-test` | End-to-end query pipeline stress test |

## Environment

```bash
SPARTA_ROOT=/home/graham/workspace/experiments/sparta  # auto-detected
# DuckDB: data/runs/<run-id>/sparta.duckdb
# ArangoDB: via SpartaDataBridge (graph_memory)
# Embedding: port 8602
```
