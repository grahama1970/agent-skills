---
name: extract-controls
description: >
  Extract framework control references from documents and create graph edges
  to sparta_controls. Supports NIST, CWE, ATT&CK, SPARTA, D3FEND, ISO.
  3-tier extraction: regex → RapidFuzz → classifier (future).
allowed-tools: [Bash, Read]
triggers:
  - extract controls
  - find controls in document
  - control extraction
  - map controls
metadata:
  short-description: Extract framework control references and create graph edges
provides:
  - extract-controls
composes:
  - memory
  - extractor
  - lean4-prove
  - task-monitor
taxonomy:
  - precision
  - compliance
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# extract-controls

Extract framework control references (NIST, CWE, ATT&CK, SPARTA, D3FEND, ISO) from
documents and create graph edges in ArangoDB. Three edge collections capture different
confidence levels and semantic roles:

- `chunk_control_edges` — every reference (evidence layer)
- `requirement_control_edges` — references inside requirement-bearing chunks (claim layer)
- `proof_jobs` — queued for lean4-prove formal verification (proof layer)

## Architecture: 3-Tier Extraction

```
Input text
    │
    ▼
┌─────────────────────────────────┐
│ Tier 1: Regex (CANDIDATE_PATTERNS) │  ~1 ms/chunk, wide net
│   AC-2, CWE-89, T1059, D3-CM   │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Tier 2: RapidFuzz resolve       │  ControlCatalog against sparta_controls
│   Exact → parent_exact → fuzzy  │  (pip install rapidfuzz)
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Tier 3: Classifier (FUTURE)     │  plug in when training data available
└─────────────────────────────────┘
    │
    ▼
ArangoDB edges
```

## Commands

### Extract from a PDF

```bash
./run.sh extract /path/to/document.pdf
```

Runs the full extractor pipeline to chunk the PDF into `datalake_chunks`, then the
framework mapper creates edges for each chunk. Same as running extractor + s12.

### Extract from inline text

```bash
./run.sh extract --text "Per NIST AC-2, the system shall implement automated account management. CWE-89 applies to SQL injection vulnerabilities."
```

Runs regex + RapidFuzz matching directly on the provided text and prints JSON results.
Useful for quick testing and CI validation.

### Backfill existing chunks

```bash
# Dry run first — see what would be created
./run.sh backfill --dry-run

# Live backfill (idempotent — MD5 edge keys prevent duplicates)
./run.sh backfill

# Tune fuzz threshold (default: 85)
./run.sh backfill --fuzz-threshold 80
```

Backfills `chunk_control_edges`, `requirement_control_edges`, and `proof_jobs` for ALL
existing `datalake_chunks`. Idempotent — re-running is safe.

### Shadow-LEGO validation

```bash
# Validate 10% sample (default)
./run.sh validate

# Validate 25% sample
./run.sh validate --sample-rate 0.25
```

Shadow-LEGO: runs extraction on a sample of chunks, compares output against the current
edge collection, reports any new gaps or regressions. Used in CI.

### Process proof_jobs queue

```bash
# Process next 10 jobs (default batch)
./run.sh prove

# Larger batch, high priority only
./run.sh prove --batch-size 50 --priority 1

# NIST-only jobs
./run.sh prove --batch-size 20 --priority 1
```

Delegates to `scripts/consume_proof_jobs.py` in the memory project. Calls `lean4-prove`
for each requirement→control pair. On success, creates `proof_requirement_edges` and
updates `requirement_control_edges.lean4_status` to `"proved"`.

### Coverage report

```bash
# All frameworks
./run.sh coverage

# Single framework
./run.sh coverage --framework NIST
./run.sh coverage --framework SPARTA
./run.sh coverage --framework CWE
```

Queries ArangoDB: controls with/without edges, chunk coverage %, requirement coverage.

### Stats

```bash
./run.sh stats
```

Quick counts for all 3 edge collections plus `proof_jobs` status breakdown (pending /
proved / failed / retry).

## Edge Graph Structure

```
sparta_controls/AC-2  (SPEC — the control)
    ↑ chunk_control_edges        (EVIDENCE — every chunk referencing it)
    ↑ requirement_control_edges  (CLAIM — subset with shall/must/will modals)
    ↑ proof_requirement_edges    (PROOF — when lean4-prove succeeds)

datalake_chunks/<key>  (SOURCE — the document chunk)
    → chunk_control_edges → sparta_controls/<key>
    → requirement_control_edges → sparta_controls/<key>
```

## Supported Frameworks

| Framework | Pattern Examples | ArangoDB Field |
|-----------|-----------------|----------------|
| NIST 800-53 | AC-2, SI-3(1), CM-6 | `source_framework: "NIST"` |
| CWE | CWE-89, CWE-1234 | `source_framework: "CWE"` |
| MITRE ATT&CK | T1059, T1059.003 | `source_framework: "ATT&CK"` |
| SPARTA | SV-AC-1(1), SV-CF-3 | `source_framework: "SPARTA"` |
| D3FEND | D3-CM, d3f:FileAnalysis | `source_framework: "D3FEND"` |
| ISO 27001 | A.9.1.1, A.12.6 | `source_framework: "ISO"` |
| CAPEC | CAPEC-66 | `source_framework: "CAPEC"` |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARANGO_HOST` / `ARANGO_URL` | `http://localhost:8529` | ArangoDB host |
| `ARANGO_PORT` | `8529` | Port (when host has no scheme) |
| `MEMORY_ARANGO_DB` / `ARANGO_DB` | `memory` | Database name |
| `ARANGO_USER` | `root` | ArangoDB username |
| `ARANGO_PASSWORD` / `ARANGO_PASS` | (from .env) | ArangoDB password (managed by /memory — never hardcode) |
| `MEMORY_ROOT` | `/home/graham/workspace/experiments/memory` | Memory project path |
| `EXTRACTOR_ROOT` | `/home/graham/workspace/experiments/extractor` | Extractor project path |

## Integration with lean4-prove

`requirement_control_edges` are queued as `proof_jobs` for formal verification.
Each job contains:
- `requirement_text` — the full chunk text
- `control_id` / `control_ref` — the matched control
- `framework` — priority 1 for NIST/SPARTA, priority 2 for others
- `status` — `pending` → `proved` / `failed` / `retry`

Run `./run.sh prove` to consume the queue via `lean4-prove`.

## Idempotency

All edge keys are deterministic MD5 hashes of `chunk_key:control_key`. Re-running
backfill or extract is always safe — existing edges are replaced in-place, proof_jobs
are inserted with `on_duplicate=ignore`.
