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
# Run a specific pipeline step (from sparta project root)
cd /home/graham/workspace/experiments/sparta
python -m sparta.pipeline.steps.01d_map_cwe_nist --run-id myrun
python -m sparta.pipeline.steps.12_qra --run-id myrun --limit 100
python -m sparta.pipeline.steps.05d_chunk_url_content --dry-run

# Run tests
uv run pytest tests/ -v
uv run pytest tests/ -k "test_qra"

# List available steps
ls src/sparta/pipeline/steps/*.py | grep -E "^[0-9]"
```

## Pipeline Steps (real, in src/sparta/pipeline/steps/)

| Step | Name | What It Does |
|------|------|-------------|
| 00 | fetch_sources | Download SPARTA xlsx, ATT&CK JSON, CWE XML |
| 01 | extract_worksheets | Parse SPARTA spreadsheet into structured data |
| 01b | load_external | Import ATT&CK, CWE, D3FEND, NIST data |
| 01c | load_capec | Import CAPEC attack patterns |
| 01d | map_cwe_nist | CWE→NIST via MITRE Heimdall (authoritative) |
| 01e | enrich_cross_refs | Enrich cross-framework references |
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
| 11b | parameter_discovery_enhanced | GPT-5 enhanced variant |
| 12 | qra | QRA generation with quality cascade |
| 12b | qra_audit | QRA quality audit |
| 12c | batched_verification | Uncertain relationship verification |
| 13 | lean4_verify | Lean4 formal verification |
| 13b | sample_uncertain_band | Sample uncertain bands for calibration |
| 14-25 | calibration | Threshold calibration, active learning |
| 48-55 | export | Discriminative attributes, audit, tiered graph export |
| 60-61 | technique_knowledge | Build technique knowledge corpus |

## Crosswalk Paths (CWE → SPARTA)

Three paths connect CWE weaknesses to SPARTA countermeasures:

| Path | Hops | Data Source | Edges |
|------|------|-------------|-------|
| CWE → SPARTA (direct) | 1 | SPARTA v3.1 `cwe_class_ids` | 2,825+ |
| CWE → NIST → SPARTA | 2 | Heimdall `nist_control_ids` + `tor_threats` | 289+ per NIST |
| CWE → CAPEC → ATT&CK → SPARTA | 4 | MITRE curated fields | sparse |

### Direct Path (SPARTA v3.1)

Step 08 extracts `cwe_class_ids` from SPARTA Techniques and creates CWE→SPARTA edges.

```bash
# Run Step 08 to create/update CWE→SPARTA edges
python -m sparta.pipeline.steps.08_relationships --run-id <run-id>
```

### NIST 2-hop Path (Heimdall)

Step 01d populates `nist_control_ids` on CWE controls from MITRE Heimdall CSV.

```bash
# Run CWE→NIST mapping step
python -m sparta.pipeline.steps.01d_map_cwe_nist --run-id <run-id>
python -m sparta.pipeline.steps.01d_map_cwe_nist --download  # Fetch fresh CSV
```

### Edge Casing in sparta_relationships (CRITICAL)

| Edge Type | source_framework | target_framework |
|-----------|-----------------|------------------|
| CWE→SPARTA | `"CWE"` | `"SPARTA"` (uppercase) |
| NIST→SPARTA | `"nist"` | `"sparta"` (lowercase) |
| CAPEC→CWE | `"CAPEC"` | `"CWE"` |

**When querying for SPARTA targets, check BOTH cases:**

```python
for tf_case in ["sparta", "SPARTA"]:
    resp = client.post("/list", json={
        "collection": "sparta_relationships",
        "filters": {"source_control_id": control_id, "target_framework": tf_case}
    })
```

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

## QRA Schema (CRITICAL)

**Canonical field for control ID: `source_control_id`**

| QRA Type | qra_type | source_control_id Example | Notes |
|----------|----------|---------------------------|-------|
| Native | `native` | `CAPEC-115`, `T1595`, `CWE-79` | Framework definition QRAs |
| Relationship | `sparta_context` | Technique ID from relationship | SPARTA-linked QRAs |

**Legacy field:** `control_id` exists in older QRAs. Code queries BOTH fields:
```python
cid = qra.get("source_control_id") or qra.get("control_id") or ""
```

**When querying by framework:**
```aql
// Native QRAs (from /create-qras skill)
FOR q IN sparta_qra
    FILTER STARTS_WITH(q.source_control_id, "CAPEC-")
    RETURN q

// BOTH native and legacy
FOR q IN sparta_qra
    LET cid = q.source_control_id != null ? q.source_control_id : q.control_id
    FILTER STARTS_WITH(cid, "CWE-")
    RETURN q
```

## Environment

```bash
SPARTA_ROOT=/home/graham/workspace/experiments/sparta  # auto-detected
# DuckDB: data/runs/<run-id>/sparta.duckdb
# ArangoDB: via SpartaDataBridge (graph_memory)
# Embedding: port 8602
```
