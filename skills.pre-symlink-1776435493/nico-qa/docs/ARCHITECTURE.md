# Nico QA — SPARTA Explorer Data Quality Automation

## Purpose

Automated data quality auditor for the SPARTA Explorer. Nico Bailon (developer/QA persona) reviews 50+ items per session — this skill replaces manual spot-checking with deterministic httpx calls to the Explorer's Express API, producing structured JSON findings.

**Design constraint**: This skill does NOT capture the user's mouse. All data checks run via HTTP. Browser automation (/surf) is used ONLY for visual verification screenshots.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     nico-qa skill                            │
│                                                              │
│  CLI (Typer)                                                 │
│  ├── audit     → run all data quality checks via httpx       │
│  ├── report    → human-readable Rich summary                 │
│  └── screenshot → visual verification via /surf              │
│                                                              │
│  Data path (audit + report):                                 │
│    httpx POST → localhost:3001/api/memory/list               │
│              → Express proxy (server/index.ts, 170 LOC)      │
│              → Unix socket /run/user/1000/embry/memory.sock   │
│              → memory daemon                                 │
│              → ArangoDB (6 collections)                      │
│                                                              │
│  Visual path (screenshot only):                              │
│    /surf navigate → localhost:3002 (Vite dev server)         │
│    /surf screenshot → PNG evidence files                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## File Layout

```
.pi/skills/nico-qa/
├── ARCHITECTURE.md      ← this file
├── SKILL.md             ← frontmatter + triggers + usage
├── pyproject.toml       ← dependencies: typer, httpx, loguru, rich
├── sanity.sh            ← smoke test (daemon reachable? API responds?)
├── audit.py             ← CLI entry point + check orchestration
├── checks.py            ← individual check functions (pure data)
├── api.py               ← httpx client wrapper for /api/memory/list
└── report.py            ← Rich formatting for human-readable output
```

Target: under 800 LOC total across all Python files (best-practices-python).

## API Contract

All data checks use a single endpoint on the Express proxy server at `localhost:3001`.

### Endpoint: POST /api/memory/list

The Express server proxies this to the memory daemon's `/list` endpoint via Unix socket.

**Request:**

```json
{
  "collection": "sparta_controls",
  "limit": 100,
  "offset": 0,
  "filter": {}
}
```

**Response:**

```json
{
  "total": 11234,
  "items": [
    {
      "_key": "...",
      "control_id": "T0100",
      "name": "...",
      "description": "...",
      "source_framework": "SPARTA",
      "mind": ["Detect", "Harden"],
      ...
    }
  ]
}
```

### Collections and Expected Shapes

| Collection | Approx Count | Key Fields |
|---|---|---|
| `sparta_controls` | 11K | control_id, name, description, source_framework, mind |
| `sparta_qra` | 217K | control_id, question, answer, reasoning, grounding_score, mind |
| `sparta_relationships` | 131K | source_control_id, target_control_id, method, nrs_score |
| `sparta_urls` | 6.8K | url_id, url, domain, status_code, content_type |
| `sparta_url_knowledge` | 42K | url_id, topic, excerpt_type, text, control_ids |
| `technique_knowledge` | 2K | technique_id, topic, text |

### api.py — httpx Client Wrapper

Thin wrapper that handles connection to the Express proxy:

```python
BASE_URL = "http://localhost:3001"

async def list_collection(
    collection: str,
    limit: int = 100,
    offset: int = 0,
    filter: dict | None = None,
) -> dict:
    """POST /api/memory/list with collection + filters."""

async def count_collection(collection: str) -> int:
    """Return total count for a collection (limit=0 query)."""

async def paginate_all(
    collection: str,
    page_size: int = 500,
    filter: dict | None = None,
) -> list[dict]:
    """Paginate through entire collection. Use sparingly — 217K QRAs
    should be sampled, not fully loaded."""
```

All functions use `httpx.AsyncClient` with a 30-second timeout. On connection failure, raise a clear error pointing the user at `localhost:3001` and the memory daemon.

## Data Quality Checks

### Check 1: Controls — Empty/Placeholder Descriptions

**What**: Find controls where `description` is empty, null, or matches placeholder patterns (e.g., "TODO", "TBD", "placeholder", description shorter than 20 characters).

**How**: Paginate `sparta_controls`, filter client-side for empty/short/placeholder descriptions.

**Output finding:**

```json
{
  "severity": "high",
  "category": "controls_empty_description",
  "message": "47 controls have empty or placeholder descriptions",
  "control_ids": ["T0100", "T0101", ...],
  "count": 47
}
```

### Check 2: Controls — Framework Distribution

**What**: Count controls per `source_framework` to detect imbalances or unexpected frameworks.

**How**: Paginate `sparta_controls`, group by `source_framework`.

**Output finding:**

```json
{
  "severity": "info",
  "category": "controls_framework_distribution",
  "message": "Framework distribution: SPARTA=216, ATT&CK=680, NIST=1200, CWE=934, D3FEND=180, ISO=45",
  "control_ids": [],
  "count": 6,
  "details": {"SPARTA": 216, "ATT&CK": 680, "NIST": 1200, "CWE": 934, "D3FEND": 180, "ISO": 45}
}
```

### Check 3: QRAs — Controls with Zero QRAs

**What**: Find controls that have no QRAs at all. These are coverage gaps.

**How**: Get all distinct `control_id` values from `sparta_qra`, compare against all control_ids from `sparta_controls`. The difference is the gap set.

**Output finding:**

```json
{
  "severity": "high",
  "category": "qra_zero_coverage",
  "message": "312 controls have 0 QRAs",
  "control_ids": ["ESA-001", "D3-DA001", ...],
  "count": 312
}
```

### Check 4: QRAs — Placeholder Reasoning

**What**: Find QRAs where `reasoning` or `answer` matches placeholder patterns: empty, under 30 chars, starts with "This is", contains "TODO"/"TBD"/"placeholder", or is an exact duplicate of the question.

**How**: Sample 2000 random QRAs from `sparta_qra`, check reasoning/answer fields.

**Output finding:**

```json
{
  "severity": "medium",
  "category": "qra_placeholder_reasoning",
  "message": "83 of 2000 sampled QRAs have placeholder or generic reasoning (4.2%)",
  "control_ids": ["T0100", ...],
  "count": 83
}
```

### Check 5: URLs — Controls with Zero URLs

**What**: Find controls that have no associated URLs in `sparta_urls`. These controls lack source material.

**How**: Get distinct control references from `sparta_urls` (via control_ids field or join pattern), compare against `sparta_controls`.

**Output finding:**

```json
{
  "severity": "medium",
  "category": "url_zero_coverage",
  "message": "156 controls have no associated URLs",
  "control_ids": ["ISO-27001-A.5.1", ...],
  "count": 156
}
```

### Check 6: URLs — Domains with Errors

**What**: Find URLs with error status codes (4xx, 5xx) or missing content, grouped by domain.

**How**: Paginate `sparta_urls`, filter for `status_code >= 400` or null, group by domain.

**Output finding:**

```json
{
  "severity": "medium",
  "category": "url_domain_errors",
  "message": "3 domains have >10 error URLs: attack.mitre.org (23), cwe.mitre.org (15), d3fend.mitre.org (11)",
  "control_ids": [],
  "count": 49,
  "details": {"attack.mitre.org": 23, "cwe.mitre.org": 15, "d3fend.mitre.org": 11}
}
```

### Check 7: Relationships — Orphan Controls

**What**: Find controls that appear in `sparta_controls` but have zero entries in `sparta_relationships` (neither as source nor target). These are disconnected nodes.

**How**: Get distinct source_control_id and target_control_id from `sparta_relationships`, compare against `sparta_controls`.

**Output finding:**

```json
{
  "severity": "low",
  "category": "relationship_orphan_controls",
  "message": "89 controls have no relationships (disconnected nodes)",
  "control_ids": ["CWE-120", "CWE-121", ...],
  "count": 89
}
```

### Check 8: Knowledge — URLs with Zero Chunks

**What**: Find URLs that were fetched but produced zero knowledge chunks. These indicate extraction failures or empty pages.

**How**: Get distinct url_ids from `sparta_url_knowledge`, compare against `sparta_urls`. URLs present in sparta_urls but absent from knowledge are zero-chunk URLs.

**Output finding:**

```json
{
  "severity": "medium",
  "category": "knowledge_zero_chunks",
  "message": "412 URLs have 0 extracted knowledge chunks",
  "control_ids": [],
  "count": 412,
  "details": {"sample_urls": ["https://attack.mitre.org/techniques/T1234", ...]}
}
```

## Sampling Strategy

For large collections, the skill uses stratified sampling rather than full enumeration:

| Collection | Strategy | Rationale |
|---|---|---|
| `sparta_controls` (11K) | Full scan | Manageable size, check descriptions exhaustively |
| `sparta_qra` (217K) | Sample 2000 random | Too large for full scan; 2000 gives 95% CI +/- 2% |
| `sparta_relationships` (131K) | Distinct IDs only | Only need unique source/target sets |
| `sparta_urls` (6.8K) | Full scan | Manageable size |
| `sparta_url_knowledge` (42K) | Distinct url_ids only | Only need URL-level presence check |
| `technique_knowledge` (2K) | Full scan | Small collection |

## CLI Commands

### `audit` — Full Data Quality Check

```bash
cd .pi/skills/nico-qa
uv run audit.py audit [--checks CHECK1,CHECK2] [--sample-size 2000] [--output audit.json]
```

Runs all 8 checks (or a subset), writes structured JSON to stdout or file.

**Output schema:**

```json
{
  "timestamp": "2026-03-18T14:30:00Z",
  "duration_seconds": 12.3,
  "explorer_api": "http://localhost:3001",
  "collections_checked": 6,
  "findings": [
    {
      "severity": "high",
      "category": "controls_empty_description",
      "message": "47 controls have empty or placeholder descriptions",
      "control_ids": ["T0100", ...],
      "count": 47
    }
  ],
  "summary": {
    "total_findings": 8,
    "by_severity": {"high": 2, "medium": 4, "low": 1, "info": 1}
  }
}
```

### `report` — Human-Readable Summary

```bash
uv run audit.py report [--input audit.json] [--format rich|markdown]
```

Reads a previous audit JSON (or runs a fresh audit inline) and renders a Rich table or markdown summary. Designed for Nico's morning triage — shows severity-sorted findings with control ID counts and recommended actions.

### `screenshot` — Visual Verification

```bash
uv run audit.py screenshot [--tabs overview,controls,qras] [--output-dir screenshots/]
```

Uses `/surf` to navigate `localhost:3002`, capture each requested tab, and save PNGs. This is the ONLY command that touches the browser. The screenshots prove pages render but make no assertions about data — that is the `audit` command's job.

Implementation delegates to `/surf`:
1. `surf navigate http://localhost:3002`
2. For each tab: click tab button, wait 2s for data load, `surf screenshot`
3. Save PNGs with tab name prefix

## Severity Levels

| Severity | Meaning | Threshold Examples |
|---|---|---|
| `high` | Data gaps that affect pipeline usability | Controls with 0 QRAs, empty descriptions |
| `medium` | Quality issues that degrade but don't block | Placeholder reasoning, error URLs, zero-chunk URLs |
| `low` | Minor issues for long-term cleanup | Orphan controls with no relationships |
| `info` | Informational metrics, not problems | Framework distribution, collection counts |

## Relationship to Existing Skills

| Existing Skill | Overlap | Nico QA Differentiator |
|---|---|---|
| `/data-audit` | Coverage percentages per framework | data-audit uses DuckDB (deprecated). Nico QA uses the live Express API via httpx — same data path as the Explorer UX. |
| `/reality-check-sparta` | Adversarial QRA quality checks | reality-check-sparta is deep analysis with Brandon persona, convergence loops, and fresh URL fetching. Nico QA is fast deterministic checks against the live API. |
| `/monitor-sparta` | Continuous quality monitoring | monitor-sparta runs the 3-tier validation cascade (T0/T1.5/T2). Nico QA checks structural completeness, not semantic quality. |
| `/quality-audit` | Statistical sampling | quality-audit is a general-purpose framework. Nico QA is SPARTA-specific with hardcoded collection schemas. |

**Key differentiator**: Nico QA tests the same data path the Explorer UX uses (Express proxy at port 3001). If the audit passes, the Explorer will render correct data. If it fails, the Explorer has a real problem. Other skills query DuckDB (deprecated) or the daemon directly.

## Compose Chain

```
/nico-qa audit → structured JSON
/nico-qa report → Rich table for terminal review
/nico-qa screenshot → /surf screenshots for visual proof
```

Downstream composition:
- `/nico-qa audit` output feeds into the Overview tab's "Outstanding Issues" panel
- `/nico-qa report` output can be stored via `/memory learn` for trend tracking
- `/nico-qa screenshot` evidence supports `/review-design` visual audits

## Configuration

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `EXPLORER_API_URL` | `http://localhost:3001` | Express proxy base URL |
| `EXPLORER_UI_URL` | `http://localhost:3002` | Vite dev server for screenshots |
| `NICO_QA_SAMPLE_SIZE` | `2000` | QRA sample size for statistical checks |
| `NICO_QA_TIMEOUT` | `30` | httpx timeout in seconds |

## Sanity Test

`sanity.sh` verifies:
1. Express API is reachable: `curl -s http://localhost:3001/api/health`
2. Memory daemon is connected: health response includes `"memory_daemon": "connected"`
3. At least one collection responds: POST to `/api/memory/list` with `sparta_controls` returns `total > 0`

Exit 0 if all pass, exit 1 with diagnostic message if any fail.

## Non-Goals

- **No LLM calls**: All checks are deterministic. No /scillm, no /assistant cascade.
- **No browser interaction for data checks**: httpx only. /surf is solely for screenshots.
- **No DuckDB**: The old data-audit skill uses DuckDB (deprecated write-lock issues). This skill uses the live API exclusively.
- **No data mutation**: Read-only. Never calls `/api/memory/learn` or modifies any collection.
- **No convergence loops**: This is a snapshot auditor, not an iterative self-correction tool. Use /reality-check-sparta for convergence.
