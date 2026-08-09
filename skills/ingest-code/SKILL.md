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
  - agentic-evals
disciplines:
  - data-engineering
  - memory-knowledge
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# ingest-code

Codebase ingestion into `/memory`:

1. **Phase 1 — Functional Knowledge**: Python AST extracts module docstrings, function signatures, class hierarchies. Markdown parser extracts section-level knowledge from CONTEXT.md, README.md, etc. Generic parser handles TS/JS exports.
2. **Phase 2 — CWE Scanning**: `/taxonomy` extracts security-relevant patterns (bridge tags + CWE mappings) per file.
3. **Phase 3 — Relationship Edges**: Python import analysis stores resolved code dependency edges in `/memory`; the local code-graph bundle also records typed import/call/inheritance occurrences, including inactive unresolved and ambiguous candidates for audit.
4. **Phase 4 — Structured Code Index**: Optional Tree-sitter extraction emits rich `code_symbol` records to `/memory` via `/upsert` into the `code_symbols` collection.

Functional lessons and CWE summaries remain lesson-style memory records for compatibility. Structured code symbols are stored through `/memory /upsert`; `/memory` owns ArangoDB, Qdrant, embeddings, sparse/hybrid retrieval, and payload/index behavior. `/ingest-code` must not talk to Qdrant directly.

## Quick Start

```bash
cd .pi/skills/ingest-code

# Full knowledge + CWE scan
./run.sh scan /path/to/codebase

# CWE scan only (legacy mode)
./run.sh scan /path/to/codebase --cwe-only

# Preview without storing to /memory
./run.sh scan /path/to/codebase --dry-run

# Include Tree-sitter structured code symbols for memory's hybrid code index
./run.sh scan /path/to/codebase --treesitter

# Nightly rescan (only files modified in last day)
./run.sh rescan --since 1d -c /path/to/codebase --treesitter
```

## Commands

### `scan` — Full Codebase Scan

```bash
./run.sh scan <path> [OPTIONS]

Options:
  --glob, -g         File patterns (default: *.py *.ts *.js *.rs *.go *.java *.c *.cpp)
  --cwe-only         Skip Phase 1, only run CWE scan
  --validate         Run LLM validation on CWE matches
  --treesitter       Run Tree-sitter scan for structured code symbols
  --code-index       Upsert Tree-sitter symbols to memory `code_symbols` (default)
  --no-code-index    Disable structured code-symbol upserts
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
  --treesitter       Run Tree-sitter scan for structured code symbols
  --code-index       Upsert Tree-sitter symbols to memory `code_symbols` (default)
  --no-code-index    Disable structured code-symbol upserts
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

### Phase 4: Structured Code Index (Tree-sitter → /memory)

When `--treesitter --code-index` is enabled, `/ingest-code` emits `CodeSymbolRecord` documents to `/memory /upsert` with `collection="code_symbols"`.
Before any code-symbol upsert, the same extraction pass writes a deterministic local code-graph bundle under `artifacts/ingest-code/code-graph/`.

Each record includes:

| Field | Purpose |
|-------|---------|
| `repo`, `branch`, `commit`, `path` | Scope and staleness control |
| `language`, `symbol_kind`, `symbol_name`, `qualified_name` | Symbol filtering and exact lookup |
| `start_line`, `end_line`, `code`, `content_hash` | Cited source retrieval and deterministic updates |
| `imports`, `parameters`, `local_variables`, `called_symbols`, `string_literals` | Lexical terms for memory's sparse/hybrid retrieval |
| `problem`, `solution`, `text`, `tags` | Compatibility with existing memory recall surfaces |

Identifier-heavy fields are emitted as `lexical_terms` such as `symbol:build_evidence_case`, `param:enable_llm`, `call:execute_llm_request`, and split identifier tokens. These are inputs to `/memory`'s code retrieval backend; `/ingest-code` does not create Qdrant collections or payload indexes directly.

### Typed Code Edges

The local `edges.jsonl` bundle uses typed `CodeEdgeRecord` entries for file and symbol relationships:

| Field | Purpose |
|-------|---------|
| `from_id`, `from_entity_type`, `to_id`, `to_entity_type` | Stable file/symbol endpoints; resolved edges must point at records present in the same bundle |
| `edge_type` | One of `DEFINES`, `IMPORTS`, `CALLS`, `INHERITS`, `IMPLEMENTS` |
| `resolution_status` | `resolved`, `candidate`, or `unresolved`; also mirrored as legacy `status` |
| `resolution_method`, `confidence`, `provenance`, `synthesized_by` | How the edge was produced and how strong the static resolution is |
| `source_path`, `source_start_line`, `source_end_line`, `source_start_column`, `source_end_column` | Exact source occurrence span for the edge |
| `active_for_traversal` | `true` only for resolved edges; candidates and unresolved references are never traversal-active |
| `raw_reference`, `candidate_ids`, `candidate_descriptors`, `unresolved_reason`, `attempted_resolution_stages` | Audit data for alias, relative import, ambiguous dispatch, and reflection/dynamic call cases |

Current Python support resolves exact file imports, relative imports, explicit import aliases, local lexical calls, inherited method calls, and same-module/package call targets. Same-named functions that cannot be disambiguated are emitted as inactive candidates. Dynamic/reflection calls such as `getattr(...)` are emitted as inactive unresolved references unless a later resolver can prove a concrete target.

Only resolved legacy import dependencies are sent to `/memory /add-edges`. The local typed bundle is the provenance receipt; candidates and unresolved edges are retained there for review but are not admitted as canonical active graph edges.

## Directory Filtering

**Git repositories:** When scanning a git repo, `/ingest-code` uses `git ls-files` which automatically respects `.gitignore`. Files ignored by git are excluded from ingestion.

**Hardcoded skip directories** (always skipped, even in non-git dirs):
`.venv`, `venv`, `node_modules`, `__pycache__`, `.git`, `dist`, `build`, `.eggs`, `.mypy_cache`, `.pytest_cache`, `site-packages`, `.uv`

**Always included** (regardless of .gitignore): `CONTEXT.md`, `README.md`, `CLAUDE.md`, `MEMORY.md`, `AGENTS.md`, plus `docs/` and `local/docs/`.

## Integration with /monitor-codebase

The nightly pipeline calls `rescan` with scoped directories from `.monitor-codebase.json`:

```json
{
  "include_dirs": ["src/extractor/pipeline/steps", "prototypes/tabbed/api"],
  "exclude_dirs": [".venv", "node_modules", "checkpoints"]
}
```

The `exclude_dirs` list is additive — it supplements both `.gitignore` and the hardcoded skip directories.

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

## Indexing Marker

After a successful scan, `/ingest-code` writes a `.ingest-code.json` marker file to the scanned directory:

```json
{
  "ingested_at": "2026-04-14T13:30:00",
  "path": "${HOME}/workspace/my-project",
  "stem": "my-project",
  "files_scanned": 968,
  "knowledge_stored": 1520,
  "cwe_stored": 45,
  "edges_stored": 234,
  "code_index": {
    "enabled": true,
    "backend": "memory",
    "collection": "code_symbols",
    "treesitter": true,
    "symbols_stored": 4182,
    "lexical_terms": true,
    "line_ranges": true,
    "content_hashes": true,
    "hybrid_retrieval_capable": true
  },
  "scope": "code"
}
```

**Why this exists:** Other skills (like `/code-runner`) can check for this marker to determine if a codebase has been semantically indexed. If `code_index.enabled` is true, they should prefer `/memory recall` over `code_symbols`/hybrid code retrieval before falling back to ripgrep pattern matching.

The marker is also stored in `/memory` with tags `["ingest-code", "indexed-codebase", <stem>, <path>]` for discovery via recall.

## Local Agent Artifacts

`/ingest-code` also leaves local artifacts for project agents that cannot or
should not query `/memory` during a task:

| Artifact | Purpose |
|----------|---------|
| `.ingest-code.json` | Marker with scan status, scope, scan roots, code-index counts, and local artifact paths |
| `.cleanup-evidence.json` | Per-candidate dependency evidence consumed by `$cleanup` for tracked-file mutation decisions |
| `artifacts/ingest-code/code-symbols.jsonl` | JSONL code-symbol records with paths, line ranges, signatures, docstrings, lexical terms, and snippets for offline lookup |
| `artifacts/ingest-code/code-graph/manifest.json` | Bundle metadata, repository identity, scan roots, dirty tracked-worktree state, counts, and artifact list |
| `artifacts/ingest-code/code-graph/files.jsonl` | Root-relative file records with stable file IDs, language, parse/skip/ignored/failed status, source hash, and reason |
| `artifacts/ingest-code/code-graph/symbols.jsonl` | Symbol records with `symbol_id`, `symbol_version_id`, `legacy_key`, source range, content hash, and Memory-compatible document shape |
| `artifacts/ingest-code/code-graph/edges.jsonl` | Deterministic typed `DEFINES`/`IMPORTS`/`CALLS`/`INHERITS` occurrence edges with resolution status, active traversal gate, source spans, confidence, and provenance |
| `artifacts/ingest-code/code-graph/diagnostics.jsonl` | Distinct parse, ignored-file, and skip diagnostics with exact root-relative paths |
| `artifacts/ingest-code/code-graph/coverage.json` | Coverage receipt with parsed, failed, ignored, skipped, symbol, edge, and diagnostic counts; parse failures set `fail_closed=true` |
| `artifacts/ingest-code/code-graph/checksums.json` | SHA-256 checksums for all other files in the bundle |

These artifacts are fallback evidence, not a replacement for `/memory recall`.
Prefer `/memory recall` when available; use the JSONL and evidence files for
offline inspection, review bundles, or deterministic receipts.

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Storage backend — lesson records use compatibility storage; structured code symbols use `/upsert` |
| `/taxonomy` | CWE extraction engine (Phase 2) |
| `/monitor-codebase` | Nightly orchestrator that calls `rescan` |
| `/treesitter` | Structured symbol extraction for the memory-backed code index |
| `/scheduler` | Cron job registration |
