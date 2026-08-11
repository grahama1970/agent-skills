---
name: ingest-sparta
description: >
  Thin wrapper around the SPARTA pipeline project (79K LOC Python).
  Runs pipeline steps, checks status, runs tests, launches Explorer UX.
  The real code lives at ~/workspace/experiments/sparta/src/sparta/pipeline/ —
  this skill is an interface, not a reimplementation.
project-path: ${HOME}/workspace/experiments/sparta
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
  - agentic-evals
taxonomy:
  - precision
  - resilience
  - ingestion
  - security
disciplines:
  - compliance-security
  - data-engineering
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /ingest-sparta

Thin skill wrapper around the real SPARTA pipeline at
`${HOME}/workspace/experiments/sparta/`.

## What This Skill Does

Dispatches commands to the real pipeline. Does NOT contain pipeline logic.

## What the Real Pipeline Does

37 numbered Python steps that:
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
cd ${HOME}/workspace/experiments/sparta
uv run python -m sparta.pipeline.00_fetch_source
uv run python -m sparta.pipeline.12_qra --run-id myrun --limit 100
uv run python -m sparta.pipeline.08_relationships --run-id myrun

# Run tests
uv run pytest tests/ -v
uv run pytest tests/ -k "test_qra"

# List available steps
ls src/sparta/pipeline/[0-9]*.py
```

**Module path is `sparta.pipeline.NN_name`, NOT `sparta.pipeline.steps.NN_name`.**
The old `steps/` subdirectory generation (56 files, e.g. `01d_map_cwe_nist`,
steps 48-61) lives only on branch `feature/nrs-standardization` at `e1cba40`;
on main its directory held nothing but stale bytecode and was removed
2026-08-11. Any `sparta.pipeline.steps.*` invocation fails with `No module
named`.

## Pipeline Steps (real, in src/sparta/pipeline/)

Verified against the filesystem 2026-08-11. Highest step number is 16; there are
no steps 17+. Earlier revisions of this file listed steps 01b/01c/01d/01e,
05d, 11b, 12b/12c, 13b, 14-25, 48-55 and 60-61, none of which exist.

| Step | Module | What It Does |
|------|--------|-------------|
| 00 | `00_fetch_source` | Download SPARTA xlsx from sparta.aerospace.org |
| 01 | `01_extract_base` | Parse SPARTA spreadsheet into structured data |
| 02a/02b | `02a_sheet_normalize`, `02b_sheet_audit` | Normalize and audit worksheets |
| 03 | `03_sheet_enrich` | Enrich sheet records |
| 04 | `04_context_merge`, `04b_child_bundle` | Merge context, bundle child records |
| 05 | `05_url_inventory` | Build URL manifest from controls |
| 06 | `06_fetch_urls`, `06b_alt_sources`, `06b_category_knowledge`, `06c_alt_sources_review`, `06c_fetch_cwe`, `06d_verify_alt_sources`, `06m_audit` | Fetch URLs, alternate sources, CWE |
| 07 | `07_generate_knowledge_chunks`, `07_generate_pdf_html_chunks`, `07a_cwe_to_chunks`, `07b_generate_llm_knowledge_chunks`, `07c_audit`, `07c_build_knowledge_anchors` | Chunking and knowledge anchors |
| 08 | `08_relationships`, `08c_cwe_summaries`, `08d_cwe_shortlist`, `08e_cwe_adjudicate` | Deterministic edges, CWE adjudication |
| 09 | `09_relationships_llm`, `09a_relationships_llm_audit`, `09a_relationships_tune`, `09b_cc_conceptual`, `09r_reject_sample_audit` | LLM-verified edges |
| 10 | `10_groupings` | Groupings |
| 11 | `11_export_graph`, `11a_qra_inputs_audit` | Graph export, QRA input audit |
| 12 | `12_qra` | QRA generation with quality cascade |
| 13 | `13_persist_arango` | Persist to ArangoDB |
| 14 | `14_embed_chunks` | Generate embeddings |
| 16 | `16_qra_audit` | QRA quality audit |

Step-number prefixes are not unique: `06b`, `06c`, `07`, `07c` and `09a` each
name two different modules. Always invoke the full module name.

## Framework Registry (what is actually in sparta_controls)

The pipeline above does not produce the whole corpus. Verified 2026-08-11:
382,700 controls across 20 `source_framework` values, of which the numbered
steps account for a minority.

| source_framework | Controls | Loaded by |
|------------------|---------:|-----------|
| `NVD_CVE` | 367,886 | `scripts/ingest_nvd_cvelist.py` (outside the numbered pipeline) |
| `NVD` | 4,830 | outside the numbered pipeline |
| `NIST` | 1,905 | numbered pipeline |
| `CISA_KEV` | 1,616 | `scripts/backfill_kev_corpus.py` (outside the numbered pipeline) |
| `ATT_CK_Enterprise` | 1,273 | numbered pipeline |
| `SPARTA` | 1,110 | numbered pipeline |
| `CWE` | 973 | numbered pipeline |
| `CAPEC` | 615 | numbered pipeline |
| `attack` | 524 | ambiguous alias of ATT&CK; domain unrecorded |
| `retired_probe` | 500 | test residue, not a framework |
| `D3FEND` | 424 | numbered pipeline |
| `ATT_CK_Mobile` | 225 | numbered pipeline |
| `MITRE_ATLAS` | 205 | `scripts/ingest_atlas.py` (outside the numbered pipeline) |
| `EMB3D` | 170 | outside the numbered pipeline |
| `ESA` / `ESA_Shield` | 137 / 137 | duplicate populations under two labels |
| `ATT_CK_ICS` | 131 | numbered pipeline |
| `ISO` | 23 | outside the numbered pipeline |
| `NASA` | 14 | outside the numbered pipeline |

Adding a framework means TWO writes, not one: nodes into `sparta_controls` and
edges into `sparta_relationships`. Nodes alone are reachable by semantic and
BM25 search but join no crosswalk chain, which is the failure mode
`monitor-sparta` check 30 (Framework Label Alignment) exists to catch. As of
2026-08-11 it reports 15 frameworks with zero edges covering 378,696 controls.

Use the exact label already present. Do not introduce a case or format variant
of an existing framework.

## Crosswalk Paths (CWE → SPARTA)

Edge counts verified against the live corpus 2026-08-11:

| Path | Hops | Data Source | Edges (live) |
|------|------|-------------|--------------|
| CWE → SPARTA (direct) | 1 | SPARTA v3.1 `cwe_class_ids` | 2,825 |
| NIST → SPARTA | 1 | numbered pipeline | 121,957 |
| CAPEC → CWE | 1 | MITRE curated fields | 1,212 |

### Direct Path (SPARTA v3.1)

Step 08 extracts `cwe_class_ids` from SPARTA Techniques and creates CWE→SPARTA edges.

```bash
# Run Step 08 to create/update CWE→SPARTA edges
uv run python -m sparta.pipeline.08_relationships --run-id <run-id>
```

### CWE → NIST 2-hop Path (Heimdall): Step 15

The July pipeline rewrite dropped the old `steps/01d_map_cwe_nist` module; it
was recovered onto main 2026-08-11 as `15_map_cwe_nist` (commit `0864539`).

```bash
uv run python -m sparta.pipeline.15_map_cwe_nist --download --dry-run  # preview
uv run python -m sparta.pipeline.15_map_cwe_nist                       # apply
```

Populates `nist_control_ids` + `nist_source` on CWE controls from the MITRE
Heimdall CSV (144 curated mappings; 138 CWEs present in the corpus enriched on
recovery, 2-hop path verified live: `CWE-79 → SI-10 → 17 SV-* controls` via
`tor_threats`). Note this writes a FIELD, not edges — CWE→NIST edge documents
in `sparta_relationships` still need a relationships step to materialize the
path for graph traversal.

### Edge Casing in sparta_relationships

Framework labels on edges are case-exact matches of `sparta_controls`
labels since the 2026-08-11 `relationship_framework_label` repair
(243,914 edges relabelled `nist`→`NIST`, `sparta`→`SPARTA`; zero lowercase
labels remain).

| Edge Type | source_framework | target_framework |
|-----------|-----------------|------------------|
| CWE→SPARTA | `"CWE"` | `"SPARTA"` |
| NIST→SPARTA | `"NIST"` | `"SPARTA"` |
| CAPEC→CWE | `"CAPEC"` | `"CWE"` |

Write new edges with the exact `sparta_controls` label. monitor-sparta
check 30 (`framework_label_alignment`) flags any edge whose framework label
matches no control population.

## Explorer UX

8-tab React UI for SPARTA pipeline transparency. Launch via `./run.sh explorer`.

- **Frontend**: Vite on `:3002` — renders `SpartaExplorer` with 8 view components
- **API proxy**: Express on `:3001` — proxies `/api/memory/*` to daemon Unix socket
- **Data**: ArangoDB via memory daemon. Verified 2026-08-11: 382,700 controls,
  250,679 QRAs, 263,854 relationships, 6,854 URLs, 6,855 url_content rows

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
SPARTA_ROOT=${HOME}/workspace/experiments/sparta  # auto-detected
# DuckDB: data/runs/<run-id>/sparta.duckdb
# ArangoDB: via SpartaDataBridge (graph_memory)
# Embedding: port 8602
```
