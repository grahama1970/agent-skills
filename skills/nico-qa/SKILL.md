---
name: nico-qa
description: >
  Automated data quality audit for SPARTA Explorer. Runs deterministic httpx checks
  against the Express API (localhost:3001) to verify all 6 ArangoDB collections have
  complete, non-placeholder data. Produces structured JSON findings with severity levels.
triggers:
  - nico audit
  - data quality check
  - explorer audit
  - nico qa
  - sparta data quality
provides:
  - nico-qa
composes:
  - surf
  - test-interactions
  - memory
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Nico QA — SPARTA Explorer Data Quality Audit

Automated data quality auditor that checks the same API path the Explorer UX uses.
If this audit passes, the Explorer renders correct data. If it fails, the Explorer has a real problem.

## Commands

### audit — Run all data quality checks

```bash
.pi/skills/nico-qa/run.sh audit
```

Runs 8 checks across 6 collections via httpx POST to `localhost:3001/api/memory/list`.
Outputs structured JSON with findings, severity levels, and sample IDs.

### report — Pretty-print audit results

```bash
.pi/skills/nico-qa/run.sh report
```

Runs a fresh audit and prints a human-readable summary sorted by severity.

### screenshot — Visual verification via /surf

```bash
.pi/skills/nico-qa/run.sh screenshot
```

Uses `/surf` to navigate `localhost:3002`, capture Explorer tabs, and save PNG evidence.

## Checks

| # | Category | Severity | What |
|---|----------|----------|------|
| 1 | controls_empty_description | high | Controls with empty/placeholder descriptions |
| 2 | controls_framework_distribution | info | Count controls per source_framework |
| 3 | qra_zero_coverage | high | Controls with 0 QRAs |
| 4 | qra_placeholder_reasoning | medium | QRAs with generic/placeholder reasoning |
| 5 | url_zero_coverage | medium | Controls with no associated URLs |
| 6 | url_domain_errors | medium | URLs with 4xx/5xx status codes by domain |
| 7 | relationship_orphan_controls | low | Controls with no relationships |
| 8 | knowledge_zero_chunks | medium | URLs with 0 extracted knowledge chunks |

## Output Schema

```json
{
  "timestamp": "2026-03-18T14:30:00Z",
  "duration_seconds": 12.3,
  "explorer_api": "http://localhost:3001",
  "collections_checked": 6,
  "findings": [{"severity": "high", "category": "...", "message": "...", "count": 47, "sample_ids": [...]}],
  "summary": {"total_findings": 8, "by_severity": {"high": 2, "medium": 4, "low": 1, "info": 1}}
}
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `EXPLORER_API_URL` | `http://localhost:3001` | Express proxy base URL |
| `EXPLORER_UI_URL` | `http://localhost:3002` | Vite dev server for screenshots |
| `NICO_QA_SAMPLE_SIZE` | `2000` | QRA sample size for statistical checks |
| `NICO_QA_TIMEOUT` | `30` | httpx timeout in seconds |
