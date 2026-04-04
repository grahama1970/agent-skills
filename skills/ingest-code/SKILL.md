---
name: ingest-code
description: >
  Ingest codebases into /memory for knowledge extraction and CWE scanning.
  Phase 1 extracts functional knowledge (module docstrings, function signatures,
  class hierarchies, markdown docs) via Python AST. Phase 2 scans for CWE
  mappings via /taxonomy. Designed to run nightly via /monitor-codebase.
allowed-tools: [Bash, Read]
triggers:
  - ingest code
  - scan codebase
  - ingest codebase
  - scan for cwes
  - codebase ingestion
  - code to memory
metadata:
  short-description: Codebase knowledge + CWE extraction to /memory
  author: "Horus"
  version: "0.2.0"

provides:
  - ingest-code
composes:
  - memory
  - taxonomy
  - task-monitor
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ingest-code

Two-phase codebase ingestion into `/memory`:

1. **Phase 1 — Functional Knowledge**: Python AST extracts module docstrings, function signatures, class hierarchies. Markdown parser extracts section-level knowledge from CONTEXT.md, README.md, etc. Generic parser handles TS/JS exports.
2. **Phase 2 — CWE Scanning**: `/taxonomy` extracts security-relevant patterns (bridge tags + CWE mappings) per file.

All items stored via `/memory learn` with tags like `["codebase", "module"|"class"|"function"|"cwe", name, stem]`.

## Quick Start

```bash
cd .pi/skills/ingest-code

# Full knowledge + CWE scan
./run.sh scan /path/to/codebase

# CWE scan only (legacy mode)
./run.sh scan /path/to/codebase --cwe-only

# Preview without storing to /memory
./run.sh scan /path/to/codebase --dry-run

# Nightly rescan (only files modified in last day)
./run.sh rescan --since 1d -c /path/to/codebase
```

## Commands

### `scan` — Full Codebase Scan

```bash
./run.sh scan <path> [OPTIONS]

Options:
  --glob, -g         File patterns (default: *.py *.ts *.js *.rs *.go *.java *.c *.cpp)
  --cwe-only         Skip Phase 1, only run CWE scan
  --validate         Run LLM validation on CWE matches
  --dry-run          Preview without writing to /memory
  --scope            Memory scope (default: "code")
  --batch-size       Files per CWE scan batch (default: 50)
```

### `rescan` — Incremental Rescan (Scheduler Job)

```bash
./run.sh rescan [OPTIONS]

Options:
  --since            Only files modified since (ISO date or "1d", "7d")
  -c, --codebase     Codebase path(s) to rescan (repeatable)
  --validate         Run LLM validation
  --scope            Memory scope
```

## What Gets Extracted

### Phase 1: Functional Knowledge (Python AST)

| Source | What | Example /memory Problem |
|--------|------|------------------------|
| Module docstring | Module purpose | "What does run_pipeline.py do?" |
| Class definition | Class + methods + bases | "What is the ContentRepository class in content_query.py?" |
| Function signature | Args, return type, docstring | "What does extract_tables() do in s05_table_extractor.py?" |
| Markdown sections | Architecture decisions, bug fixes | "What does 'Bugs Fixed' say in MEMORY.md?" |
| TS/JS exports | Exported symbols | "What is AnswerCanvas in AnswerCanvas.tsx?" |

### Phase 2: CWE Scanning (via /taxonomy)

| Category | Example CWEs | Triggers |
|----------|--------------|----------|
| MemorySafety | CWE-120, CWE-787, CWE-416 | buffer, overflow, memory, pointer |
| InputValidation | CWE-20, CWE-89, CWE-78 | input, validation, inject, command |
| Authentication | CWE-287, CWE-798, CWE-522 | auth, credential, password, session |
| Cryptography | CWE-311, CWE-327, CWE-330 | encrypt, crypto, key, random |

## Directory Filtering

Files in these directories are always skipped:
`.venv`, `venv`, `node_modules`, `__pycache__`, `.git`, `dist`, `build`, `.eggs`, `.mypy_cache`, `.pytest_cache`, `site-packages`, `.uv`

Markdown docs are always included: `CONTEXT.md`, `README.md`, `CLAUDE.md`, `MEMORY.md`, `AGENTS.md`, plus `docs/` and `local/docs/`.

## Integration with /monitor-codebase

The nightly pipeline calls `rescan` with scoped directories from `.monitor-codebase.json`:

```json
{
  "include_dirs": ["src/extractor/pipeline/steps", "prototypes/tabbed/api"],
  "exclude_dirs": [".venv", "node_modules", "checkpoints"]
}
```

## Output Format

```json
{
  "files_scanned": 968,
  "knowledge_extracted": 1547,
  "knowledge_stored": 1520,
  "files_with_cwes": 23,
  "total_cwe_mappings": 45,
  "cwe_stored": 45,
  "cwe_summary": {"CWE-78": 5, "CWE-20": 12}
}
```

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Storage backend — all items stored via `learn()` |
| `/taxonomy` | CWE extraction engine (Phase 2) |
| `/monitor-codebase` | Nightly orchestrator that calls `rescan` |
| `/treesitter` | Advanced code parsing (future Phase 3) |
| `/scheduler` | Cron job registration |
