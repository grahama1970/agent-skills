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

`ingest-code` scans a source-code repository for reusable code knowledge,
relationships, CWE/taxonomy metadata, and optional Tree-sitter code symbols. It
writes supported records through the current `/memory` client.

This is a code-ingestion skill. It is not a general document, media, or
multimodal extractor. Repository Markdown such as `README.md`, `AGENTS.md`, and
`docs/` may contribute code-related lessons, but requests primarily involving
PDF, DOCX, HTML, XML, PPTX, XLSX, EPUB, images, YouTube, video, or other media
extraction belong to `$extractor` or to a separately implemented memory
orchestration path.

`/memory` owns ArangoDB, Qdrant, embeddings, sparse/hybrid retrieval, and
payload/index behavior. `ingest-code` must not talk to Qdrant directly.

## Quick Start

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/ingest-code

# Initial or complete repository scan with structured code symbols
./run.sh scan /absolute/path/to/repository --treesitter

# Refresh an existing repository index
./run.sh rescan -c /absolute/path/to/repository --treesitter

# Preview without writing to /memory or writing a marker
./run.sh scan /absolute/path/to/repository --dry-run
```

Use `scan` for an initial or complete scan. Use `rescan` when refreshing a
repository. Add `--treesitter` when the caller needs structured `code_symbols`
for memory-backed code retrieval. Prefer absolute repository paths.

## Commands

### `scan` — Full Codebase Scan

```bash
./run.sh scan <path> [OPTIONS]

Options:
  --glob, -g         Repeatable repository-relative file patterns (default: *.py *.ts *.tsx *.js *.jsx *.rs *.go *.java *.c *.cpp)
  --cwe-only         Skip Phase 1, only run CWE scan
  --validate         Run LLM validation on CWE matches
  --treesitter       Run Tree-sitter scan for structured code symbols
  --code-index       Upsert Tree-sitter symbols to memory `code_symbols` (default)
  --no-code-index    Disable structured code-symbol upserts
  --dry-run          Preview without writing to /memory
  --scope            Memory scope (default: "code")
  --batch-size       Positive number of files per CWE scan batch (default: 50)
```

Invalid `scan --batch-size` values exit with status 2 before scanning. The
value must be a positive integer.

Live full scans use `INGEST_WORKERS` for concurrent compatibility-lesson
writes. Missing or blank values default to 8. Non-integer, zero, or negative
values exit with status 2 before repository discovery. The setting is unused
by dry-run and CWE-only scans.

`--scope` must be a nonblank string. Leading and trailing whitespace is removed.
Invalid values exit with status 2 before repository discovery or memory writes.

Explicit `scan --glob` values must be positive repository-relative glob
patterns. Basename-only patterns such as `*.py` are recursive. Blank, absolute,
parent-traversing, or otherwise unsafe values exit with status 2 before
scanning.

With both `--dry-run` and `--treesitter`, `ingest-code` runs the validated
Tree-sitter extraction path and prints the `code_symbols` records that would be
upserted. It performs no memory writes and writes no `.ingest-code.json` marker.

In dry-run output, `[EDGE]` lines are relationship candidates only.
`edges_found` reports the candidate count and `edges_stored` remains `0`; the
memory edge endpoint is not called.

Malformed Tree-sitter file or symbol records fail the command with status 1
before code-symbol preview or persistence; they are never treated as an empty
successful scan.

Tree-sitter source locations must resolve to real lines in the discovered file.
Out-of-bounds or unreadable source ranges fail with status 1 before code-symbol
preview or persistence.

Tree-sitter records are canonicalized before preview or persistence. Exact
duplicate source-symbol records count once. Conflicting records for the same
path, qualified name, and start line fail with status 1 and produce no
completed marker.

When taxonomy support is available, both `scan` and `rescan` enrich the
complete functional-knowledge batch before the first knowledge write for that
codebase. Taxonomy exceptions or malformed tag results exit with status 1,
prevent later phases and the completed marker, and are not silently treated as
empty enrichment. Absence of the taxonomy module remains nonfatal.

Functional-knowledge extractors must return an array of records containing
nonblank `problem` and `solution` strings and a nonempty string-tag array.
Malformed extractor output exits with status 1 before taxonomy enrichment,
preview, persistence, or marker creation. A valid empty array is a successful
zero-knowledge result.

Every discovered source file used by a requested phase must remain readable. A
read failure exits with status 1 and prevents the completed marker. Readable
files with unsupported or syntactically invalid content may still produce zero
records.

Malformed CWE scanner results fail with status 1 before CWE preview or
persistence and prevent the completed marker. A valid empty `cwe_mappings`
array remains a successful zero-finding result.

Built-in CWE pattern scanning runs with or without the optional taxonomy module.
When taxonomy is available, it may provide bridge tags and Phase 1 enrichment.
When absent, only that enrichment is omitted. `scan --cwe-only` still runs the
built-in CWE scan.

`scan` and `rescan` use the same CWE compatibility payload. CWE ID, name,
category, source file, and validated taxonomy bridge tags are propagated
deterministically; empty taxonomy enrichment does not alter the base CWE tags.

### `rescan` — Incremental Rescan (Scheduler Job)

```bash
./run.sh rescan [OPTIONS]

Options:
  --since            Only files modified since a positive whole-number duration ("12h", "7d") or ISO-8601 date/time
  -c, --codebase     Codebase path(s) to rescan (repeatable)
  --validate         Run LLM validation
  --treesitter       Run Tree-sitter scan for structured code symbols
  --code-index       Upsert Tree-sitter symbols to memory `code_symbols` (default)
  --no-code-index    Disable structured code-symbol upserts
  --scope            Memory scope
```

Invalid `--since` values exit with status 2 before scanning. Accepted forms
include positive whole-number durations such as `12h` and `7d`, ISO-8601 dates
such as `2026-07-23`, and ISO-8601 date/times such as
`2026-07-23T12:00:00+00:00`.

Modification-time metadata must be readable for every candidate evaluated by
`--since`. A stat or timestamp-conversion failure exits with status 1 and
prevents memory writes and completed markers; it is not treated as an unchanged file.

## Agent Rules

Agents must:

- Use only the supported `scan` or `rescan` commands for this skill.
- Use `--treesitter` when structured code-symbol indexing is required.
- Honor `.monitor-codebase.json`, `CODE_SYMBOLS_SCAN_INCLUDE_DIRS`, and the
  hardcoded skip directories.
- Treat `.ingest-code.json` according to its normalized status.
- Report terminal memory-write errors instead of masking them.
- Route document and media extraction requests to `$extractor`.

Agents must not:

- Call Qdrant directly.
- Run or import Graphify.
- Invent or call `/v1/ingest/*`, snapshot, commit, receipt, debugger-proof, or
  DAG endpoints from this skill.
- Claim multimodal ingestion from `ingest-code`.
- Treat a dry run or a local marker as proof of backend embedding coverage.
- Treat logs or static UI state as durable workflow receipts.
- Move memory storage ownership into this skill.

## Scan Scope

Scan roots are resolved in this order:

1. A nonblank `CODE_SYMBOLS_SCAN_INCLUDE_DIRS` environment value overrides
   `.monitor-codebase.json` `include_dirs`.
2. The environment value is comma-separated. Entries are trimmed, resolved
   under the repository, deduplicated in order, and kept only when the directory
   exists.
3. A nonblank override with no valid existing directories produces an empty
   scoped scan. It does not broaden to the repository root.
4. Without a nonblank environment override, `.monitor-codebase.json`
   `include_dirs` controls scan roots.
5. Without any configured include roots, the repository root is scanned.

Example:

```bash
CODE_SYMBOLS_SCAN_INCLUDE_DIRS="src,scripts" \
  ./run.sh rescan -c /absolute/path/to/repository --treesitter
```

`.monitor-codebase.json` `exclude_dirs` remains additive. It supplements both
`.gitignore` and the hardcoded skip directories; the environment variable only
overrides include roots.

`exclude_dirs` must be a JSON array of nonblank repository-relative directory
names or paths. Absolute paths, parent traversal, and glob syntax are invalid
and exit with status 2 before scanning.

## Processing

Current processing is local and command-driven:

1. Discover files inside resolved scan roots while respecting git ignore rules,
   configured exclusions, and hardcoded skip directories.
2. Extract code lessons, relationships, CWE/taxonomy metadata, and optional
   Tree-sitter symbols.
3. Write supported records through the current `/memory` client.
4. Write `.ingest-code.json` after a successful non-dry-run scan.

`ingest-code` currently does not create memory snapshots, coordinate multimodal
extractors, run Graphify, or perform server-side plan/commit orchestration.

## Memory Writes

`ingest-code` uses `httpx` over the configured `/memory` Unix socket. Lesson
and compatibility records use the current memory compatibility calls.
Structured `code_symbols` are sent in batches to `POST /upsert` with
`collection="code_symbols"`.

When a structured multi-record code-symbol batch fails, it is recursively split
before using the legacy path. Legacy code-symbol storage is attempted only after
a singleton structured upsert fails. If both methods fail, the terminal error
must remain visible.

Agents should invoke the `scan` or `rescan` command. They should not reproduce
these internal HTTP calls manually.

## Extracted Records

### Functional Knowledge

| Field | Purpose |
|-------|---------|
| Module docstring | Module purpose |
| Class definition | Class, methods, and bases |
| Function signature | Arguments, return type, and docstring |
| Markdown sections | Code-related architecture notes, decisions, and local docs |
| TS/JS exports | Exported symbols and component names |

### CWE Metadata

`/taxonomy` extracts security-relevant patterns and CWE mappings per source file
when taxonomy support is available.

### Structured Code Symbols

When `--treesitter --code-index` is enabled, `ingest-code` emits
`CodeSymbolRecord` documents to `/memory /upsert` with
`collection="code_symbols"`.

Each record includes:

| Field | Purpose |
|-------|---------|
| `repo`, `branch`, `commit`, `path` | Scope and staleness control |
| `language`, `symbol_kind`, `symbol_name`, `qualified_name` | Symbol filtering and exact lookup |
| `start_line`, `end_line`, `code`, `content_hash` | Source retrieval and deterministic updates |
| `imports`, `parameters`, `local_variables`, `called_symbols`, `string_literals` | Lexical terms for sparse/hybrid retrieval |
| `problem`, `solution`, `text`, `tags` | Compatibility with existing memory recall surfaces |

Identifier-heavy fields are emitted as lexical terms such as
`symbol:build_evidence_case`, `param:enable_llm`, `call:execute_llm_request`,
and split identifier tokens. These are inputs to `/memory`'s code retrieval
backend.

Python parameter payloads cover positional-only, positional-or-keyword,
variadic, keyword-only, and keyword-variadic arguments in declaration order,
while preserving the existing omission of a parameter literally named `self`.
Python lexical fields are declaration-scoped; they include nested declaration
headers but exclude nested function, class, and lambda bodies.
For Python, `local_variables` includes names bound in the selected declaration's
scope, including nested declaration names, imports, exception aliases, and
pattern captures, not only assignment-target `Name(Store)` nodes.
Python comprehension iteration targets are excluded from the containing
declaration's `local_variables`, while direct comprehension calls, literals,
filters, iterables, result expressions, and walrus-bound names remain lexical
context for the containing declaration.
Selected Python declaration headers contribute calls and literals but not
body-local bindings; nested declaration headers still bind into the selected
enclosing declaration's scope.
Exact Python AST matches canonicalize record line ranges, code slices, hashes,
and identity to the first syntactic decorator line, or to the declaration line
when undecorated, regardless of whether Tree-sitter reports the decorator or
definition line.
Exact Python AST matches also canonicalize `parent_symbol` to the immediate
lexical parent function, async function, or class. Tree-sitter parent metadata
is preserved only when Python parsing or exact AST matching fails.

## Directory Filtering

**Git repositories:** When scanning a git repo, `/ingest-code` uses `git ls-files` which automatically respects `.gitignore`. Files ignored by git are excluded from ingestion.

**Hardcoded skip directories** (always skipped, even in non-git dirs):
`.venv`, `venv`, `node_modules`, `__pycache__`, `.git`, `dist`, `build`, `.eggs`, `.mypy_cache`, `.pytest_cache`, `site-packages`, `.uv`

**Always included** (regardless of .gitignore): Named root documentation files
with `.md` or `.mdx` suffixes, `CONTEXT`, `README`, `CLAUDE`, `MEMORY`, and
`AGENTS`, plus direct `.md` and `.mdx` files under `docs/`, `local/`, and
`local/docs/`. All candidates remain subject to repository-containment and
`--since` checks.

## Integration with /monitor-codebase

The nightly pipeline calls `rescan` with scoped directories from `.monitor-codebase.json`:

```json
{
  "include_dirs": ["src/extractor/pipeline/steps", "prototypes/tabbed/api"],
  "exclude_dirs": [".venv", "node_modules", "checkpoints"]
}
```

The `exclude_dirs` list is additive — it supplements both `.gitignore` and the
hardcoded skip directories. Entries must be nonblank repository-relative
directory names or paths, not absolute paths, parent traversal, or glob syntax.

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

After a successful non-dry-run scan, `ingest-code` writes `.ingest-code.json` to
the scanned directory:

```json
{
  "ingested_at": "2026-04-14T13:30:00",
  "started_at": "2026-04-14T13:30:00",
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
  "scope": "code",
  "run_status": "complete",
  "completed": true,
  "scan_roots": ["${HOME}/workspace/my-project/src"],
  "completed_scan_roots": ["${HOME}/workspace/my-project/src"]
}
```

Normalized marker status:

| Status | Meaning |
|--------|---------|
| `missing` | No `.ingest-code.json` exists |
| `invalid` | The marker cannot be parsed or normalized |
| `running` | The marker reports an incomplete run |
| `fresh` | The marker reports `run_status: complete` and `completed: true` |
| `failed` | The marker reports a failed run |

`fresh` is returned only for a structurally valid completed marker. A JSON
object is not sufficient by itself. Completed markers require repository
identity, nonnegative scan counts, scope, and internally consistent code-index metadata.
A legacy marker without `run_status` remains supported only when its
legacy marker fields are valid.

The marker records local scan status, scope, completed roots, and code-index
metadata. It is evidence that the local command completed its current workflow.
It is not proof of a future memory snapshot, durable run receipt, Qdrant
reconciliation, embedding completeness, or DAG state.

`code_index.treesitter` means at least one configured Tree-sitter scan root
completed successfully. It does not merely echo the `--treesitter` option. A
successful zero-symbol scan may therefore have `treesitter: true`,
`enabled: false`, and `symbols_stored: 0`.

Dry runs do not write to `/memory` and do not write this marker.

The marker is also stored in `/memory` with tags `["ingest-code", "indexed-codebase", <stem>, <path>]` for discovery via recall.

## Failure Behavior

On a nonzero exit, reported storage error, invalid marker, or incomplete marker,
report the failure and the relevant local details. Do not claim semantic
indexing succeeded.

Do not bypass failures by calling Qdrant, Graphify, or undocumented memory
endpoints directly.

## Handoffs

**Extractor:** Route requests primarily involving PDF, DOCX, HTML, XML, PPTX,
XLSX, EPUB, images, YouTube, video, or other media extraction to `$extractor`
or an implemented memory orchestration command. Do not add those extraction
responsibilities to `ingest-code`.

**Graphify:** Graphify is not part of the current agent-facing contract. Do not
run Graphify, import its modules, add a `--graphify` command, or treat its
output as current ingest proof. Any future use must remain an internal,
separately implemented and tested code-extraction component.

**monitor-codebase:** `$monitor-codebase` may invoke the current `ingest-code`
command and inspect the current marker. Do not claim memory run receipts or
snapshot-bound coverage receipts exist until they are implemented.

**debugger:** Use `$debugger` when `ingest-code` itself requires runtime
debugging. `ingest-code` does not currently persist paused-frame debugger state.

**DAG/Tau:** No `ingest-code` DAG endpoint or durable receipt viewer is
currently implemented. Do not infer workflow success from a static or proposed
DAG.

## Proof Boundary

Local deterministic checks can show that command code and marker/client behavior
match the current implementation:

```bash
python3 -m pytest tests -q
git diff --check
```

These checks do not prove live `/memory` availability, Qdrant embedding
coverage, multimodal extraction, Graphify adapter behavior, monitor receipts,
debugger-state storage, or DAG viewer behavior.

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Storage backend; structured code symbols use `/upsert` |
| `/taxonomy` | CWE extraction engine (Phase 2) |
| `/monitor-codebase` | Nightly orchestrator that calls `rescan` |
| `/treesitter` | Structured symbol extraction for the memory-backed code index |
| `/extractor` | Owner for document/media extraction outside the code lane |
