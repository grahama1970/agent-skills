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
4. **Phase 4 — Structured Code Index**: Optional Tree-sitter extraction emits a complete code-graph bundle and applies it through Memory/GMO's governed `/code/projection/apply` lifecycle endpoint.
5. **Static Debugger Affordances**: Code-graph bundles emit `debugger.invocation_candidate.v1` rows in `debug_invocations.jsonl`. These are candidate routes only; `$debugger` must prove a candidate at runtime before Memory can promote it.

Functional lessons and CWE summaries remain lesson-style memory records for compatibility. Structured files, symbols, and edges are canonicalized by Memory/GMO's complete projection lifecycle, not by independent per-symbol batches. `/memory` owns ArangoDB, Qdrant, embeddings, sparse/hybrid retrieval, and payload/index behavior. `/ingest-code` must not talk to ArangoDB or Qdrant directly.

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

# Read-only target freshness check before using Memory code snippets for repair
./run.sh ensure-current \
  --repo /path/to/codebase \
  --branch main \
  --commit "$COMMIT_SHA" \
  --path src/example.py \
  --json
```

## Runner Reproducibility Contract

`run.sh` executes through the skill-scoped `pyproject.toml` and `uv.lock`:

```text
uv run --project "$SCRIPT_DIR" --locked python "$SCRIPT_DIR/ingest_code.py" ...
```

Normal execution does not use dynamic `uv --with` dependencies, does not source
the repository root `.env`, and does not fall back to ambient `python3`. Missing
`uv`, missing lock state, or incompatible Python/dependency resolution fails
closed before the scanner runs.

Each invocation gets run-scoped mutable paths under:

```text
${INGEST_CODE_RUN_ROOT:-${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/ingest-code-runs/$INGEST_CODE_RUN_ID}
```

The runner sets `UV_PROJECT_ENVIRONMENT`, `UV_CACHE_DIR`, `XDG_CACHE_HOME`,
`PYTHONPYCACHEPREFIX`, and `TMPDIR` under that run root unless the caller has
already supplied explicit values. Concurrent runs therefore do not share the
normal virtual environment, uv cache, pycache, or temp directory.

Every scan/rescan emits:

```text
artifacts/ingest-code/environment_manifest.json
```

with schema `ingest-code.environment_manifest.v1`. The manifest records the
interpreter, package versions, runner/module/lock hashes, source repository
identity, projection mode, run-scoped mutable paths, terminal status, and the
allowlisted environment variable names as present/absent classifications only.
It never records environment variable values. Its stable
`environment_manifest_digest` is included in the code-graph manifest and in
`ingest-code.code_projection_request.v1`.

For Docker-backed Memory/GMO deployments where the service sees a different
mount path than the host, set:

```bash
export INGEST_CODE_BUNDLE_PATH_MAP=/host/prefix=/service/prefix
```

The host still computes bundle/checksum digests from the local artifacts; only
the request's `bundle_path` transport field is translated for the service.

## Commands

### `scan` — Full Codebase Scan

```bash
./run.sh scan <path> [OPTIONS]

Options:
  --glob, -g         File patterns (default: *.py *.ts *.js *.rs *.go *.java *.c *.cpp)
  --cwe-only         Skip Phase 1, only run CWE scan
  --validate         Run LLM validation on CWE matches
  --treesitter       Run Tree-sitter scan for structured code symbols
  --projection-mode  Projection handling: emit, apply, or none
  --code-index       Compatibility alias for --projection-mode apply
  --no-code-index    Compatibility alias for --projection-mode none
  --compat-symbol-upsert
                     Use legacy per-symbol Memory upserts with a visible warning
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
  --projection-mode  Projection handling: emit, apply, or none
  --code-index       Compatibility alias for --projection-mode apply
  --no-code-index    Compatibility alias for --projection-mode none
  --scope            Memory scope
```

### `ensure-current` — Target-Scoped Projection Freshness Preflight

```bash
./run.sh ensure-current [OPTIONS]

Options:
  --repo             Repository worktree to check (required)
  --branch           Expected branch/ref name (default: current branch)
  --commit           Expected commit SHA (default: current HEAD)
  --path             Repository-relative target path; repeatable
  --scope            Memory/GMO projection scope (default: "code")
  --json             Emit `ingest-code.code_projection_freshness.v1`
  --refresh          Explicitly refresh through `scan --treesitter --code-index`
  --canonical-branch Branch allowed to activate canonical projection (default: "main")
  --max-target-files Bound directory expansion (default: 200)
```

`ensure-current` is the pre-repair gate for stateless workers. It resolves the
repository root, branch, commit, and target paths; rejects absolute paths,
`..`, and repository escapes; reads active code-search/code-node/code-coverage
state through the supported Memory/GMO code-navigation boundary; then compares
current source hashes with indexed source hashes for the requested targets.

The result status is one of:

| Status | Meaning |
|--------|---------|
| `CURRENT` | Active Memory/GMO source hashes match current target files and coverage allows modification guidance. |
| `SOURCE_CURRENT_INDEX_INCOMPLETE` | Source bytes match, but coverage is incomplete, so exhaustive callers/callees/impact absence claims are blocked. |
| `STALE` | Current source differs from the active projection; stored snippets are not modification authority. |
| `UNINDEXED` | No applicable active projection record matched the target. |
| `BLOCKED` | Identity, containment, service, receipt, or validation failed closed. |

Default `ensure-current` is read-only. It must not parse files, create
embeddings, apply projections, or fall back to legacy per-symbol writes. With
`--refresh`, it may run the existing complete-bundle scan only when the checkout
is clean, on the configured canonical branch, and bound to the requested
commit. Feature/repair worktrees are refused so unreviewed code cannot replace
the canonical main projection.

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

When `--treesitter` is enabled, `/ingest-code` writes a deterministic local code-graph bundle under `artifacts/ingest-code/code-graph/`, computes the submitted bundle digest and checksums digest, and then follows the selected projection mode:

| Mode | Behavior |
| --- | --- |
| `--projection-mode emit` | Validate the complete bundle and write `code_projection_request.json` without opening the Memory/GMO socket or performing an external effect. This is the intended mode for Tau-managed execution. |
| `--projection-mode apply` | Apply the validated request through Memory/GMO's governed `/code/projection/apply` endpoint and verify the returned application receipt. This is the standalone compatibility path. |
| `--projection-mode none` | Build and validate the local bundle only; no projection request or application is requested. |

`--code-index` and `--no-code-index` remain compatibility aliases for `apply` and `none` respectively during migration. Supplying a new projection mode together with an explicit legacy projection flag fails closed instead of guessing precedence.

The Memory/GMO receipt is the only canonical projection success signal. It must bind the submitted bundle digest, checksums digest, activated generation, and expected file/symbol/edge counts. If Memory/GMO is unavailable, rejects the bundle, or returns a receipt whose digest does not match the submitted bundle, the scan fails closed and does not fall back to per-symbol writes.

An emitted `ingest-code.code_projection_request.v1` is not activation proof. It binds scope, repo, branch, root, source commit, expected counts, artifact inventory, submitted bundle digest, checksums digest, stable idempotency key, requested effect kind, and explicit non-claims. Tau or another host authority must separately authorize and apply it before any Memory/GMO generation is considered active.

Each record includes:

| Field | Purpose |
|-------|---------|
| `repo`, `branch`, `commit`, `path` | Scope and staleness control |
| `language`, `symbol_kind`, `symbol_name`, `qualified_name` | Symbol filtering and exact lookup |
| `start_line`, `end_line`, `code`, `content_hash` | Cited source retrieval and deterministic updates |
| `imports`, `parameters`, `local_variables`, `called_symbols`, `string_literals` | Lexical terms for memory's sparse/hybrid retrieval |
| `problem`, `solution`, `text`, `tags` | Compatibility with existing memory recall surfaces |

Documentation metadata is provenance-safe:

| Field | Purpose |
|-------|---------|
| `source_docstring` / `docstring` | Exact authored source docstring text, preserved for compatibility |
| `source_docstring_status` | `present`, `missing`, `generated_file`, or `not_applicable` for v1 extraction |
| `documentation_need` | Deterministic triage: `required`, `recommended`, `optional`, or `exempt` |
| `documentation_need_reasons` | Source-derived reasons such as `public_api`, `external_io`, `security`, `mutation`, or `trivial_helper` |
| `summary_evidence` | Canonical source-fact packet and hash for optional generated summaries |
| `derived_summary` | Current unreviewed generated summary only when bound to the current `symbol_version_id`, source hash, and evidence hash |
| `retrieval_text`, `retrieval_text_sha256`, `purpose_source` | Canonical semantic text and hash used by Memory retrieval |

Generated or model-written summaries are never copied into `docstring` or
`source_docstring`, and `/ingest-code` never rewrites source files to add
docstrings. Authored docstrings are preferred in retrieval text. A derived
summary may appear only as `derived_summary.status="derived_unreviewed"` and
only while its source/evidence hashes match the current symbol version; stale
or malformed summaries fail closed to `null`.

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

## Incremental Re-Indexing

Re-ingesting a repo emits a complete desired bundle while parsing only files
whose source or relevant transforms changed. The bundle remains the handoff
authority; the local cache is disposable acceleration evidence, not canonical
backend state.

Two local state files may exist:

- `artifacts/ingest-code/incremental-components.json` stores file components
  from the last accepted complete bundle: source fingerprint, explicit transform
  fingerprints, serialized symbols, and a component hash.
- `artifacts/ingest-code/incremental-state.json` is the legacy Memory-upsert
  retry state mapping each `symbol_id` to its `content_hash` plus the
  `transform_version` that produced it. This state is used only by the explicit
  `--compat-symbol-upsert` mode.

The file-component key is repository, branch, and repository-relative path. The
source fingerprint is a Git blob id for clean tracked files and an exact
SHA-256 for dirty or untracked files. Reuse is allowed only when the previous
bundle was complete, the source fingerprint matches, all relevant transform
fingerprints match, and the cached component hash verifies.

The v1 transform fingerprint set is explicit:

- discovery/ignore/configuration contract;
- Tree-sitter skill and parser adapter inputs;
- symbol identity/schema construction;
- documentation/semantic-text construction;
- typed edge resolver;
- artifact writer/schema.

Changing any relevant fingerprint fails closed to recomputation for the
affected component. Cache corruption, a partial prior run, missing provenance,
or fingerprint ambiguity also fails closed to recomputation.

Each run reports its plan:

```
Incremental: {"unchanged": 812, "added": 3, "changed": 1, "deleted": 2, "invalidated_by_transform": false}
File components: 1 parsed, 812 reused, 2 deleted
```

**Deletions are retired by complete projection, not left behind.** Symbols whose
source no longer exists are absent from the next complete bundle. Memory/GMO
uses that absence to retire no-longer-current files, symbols, and edges during
generation activation. In explicit compatibility mode, symbols are pruned from
the `code_symbols` collection because the legacy path cannot express a complete
repository generation.

Two ordering rules the implementation depends on:

- State is committed only after Memory/GMO returns an accepted projection
  application receipt, or after the explicit compatibility upsert succeeds.
  Committing first would mark unapplied symbols as done and they would never be
  retried.
- In compatibility mode, deletions are computed against the real previous state
  even when a transform bump invalidates everything, so a full re-index never
  loses the delete set.

A missing or corrupt state file degrades to a full re-index rather than failing
the ingest.

`scan --treesitter --projection-mode apply` uses the governed bundle-application endpoint.
The legacy per-symbol Memory upsert path remains only under
`--compat-symbol-upsert` and emits a visible warning because it is not
complete-projection lifecycle authority.

### CocoIndex Incremental Evaluation

`skills/ingest-code/evals/cocoindex-incremental/run.sh --offline-fixtures`
compares the native file-component cache against a pinned noncanonical
CocoIndex scheduler adapter. CocoIndex is eval-only and must not become Memory
state, a retrieval authority, or a production dependency from benchmark claims
alone.

The eval pins `cocoindex==1.0.19`, verifies the installed package checksum,
copies fixtures into an isolated artifact directory, blocks outbound network
connections during fixture execution, and emits:

```text
execution-receipt.json
native-results.json
cocoindex-results.json
bundle-comparison.json
invalidations.json
recovery-results.json
decision.md
```

The adapter may use CocoIndex memoized functions as disposable scheduling/cache
evidence, but both arms must emit the existing backend-neutral code-graph bundle
shape. The command fails closed if either arm does not run, if normalized bundle
digests diverge, if fixtures are modified, or if backend effects are observed.

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
| `artifacts/ingest-code/code-graph/debug_invocations.jsonl` | Static debugger invocation candidates bound to current symbol/source version, with pytest/CLI/HTTP/worker/direct/factory hints plus side-effect and fixture limitations |
| `artifacts/ingest-code/code-graph/diagnostics.jsonl` | Distinct parse, ignored-file, and skip diagnostics with exact root-relative paths |
| `artifacts/ingest-code/code-graph/coverage.json` | Coverage receipt with parsed, failed, ignored, skipped, symbol, edge, and diagnostic counts; parse failures set `fail_closed=true` |
| `artifacts/ingest-code/code-graph/checksums.json` | SHA-256 checksums for all other files in the bundle |
| `artifacts/ingest-code/analysis_handoff.json` | `ingest-code.analysis_handoff.v1` binding the deterministic bundle to optional downstream analysis without changing canonical code-graph identity |
| `artifacts/ingest-code/runtime_verification_requests.jsonl` | `ingest-code.runtime_verification_request.v1` rows that classify static debugger candidates for a later Tau/debugger workflow without executing target code |

These artifacts are fallback evidence, not a replacement for `/memory recall`.
Prefer `/memory recall` when available; use the JSONL and evidence files for
offline inspection, review bundles, or deterministic receipts.

For cleanup evidence refreshes that must not mutate Memory, use:

```bash
./run.sh scan /path/to/repo --treesitter --cleanup-evidence --local-artifacts-only
```

`--local-artifacts-only` writes local analysis artifacts and skips knowledge
storage, edge storage, and Memory projection application.

## Static Debugger Invocation Candidates

`debug_invocations.jsonl` is a handoff artifact for `$debugger`, not proof that
an invocation works. Each row is bound to repository, branch, commit,
`symbol_id`, `symbol_version_id`, source path/range, content hash, and
`ingest-code.debug_affordance.v1`.

Supported v1 invocation kinds are `pytest`, `cli`, `http`, `attach_runtime`,
`direct`, and `factory_method`.

Status values remain static and conservative:

- `candidate_static`: a static candidate that still needs debugger proof.
- `needs_fixture`: required arguments, async/generator/context-manager behavior,
  HTTP/app context, overload declarations, classes, or ordinary instance methods
  need a fixture or adapter.
- `unsafe_direct`: static evidence found filesystem, database, network, mutation,
  or destructive indicators, so no direct command is emitted.
- `attach_runtime`: a worker/runtime attach point is visible, but a live runtime
  harness is required.

`ingest-code` does not execute candidates, create launch configurations, or
mark anything `verified_*`. Runtime promotion belongs to `$debugger` and Memory.
Changing `debug_affordance.py` invalidates incremental file-component reuse via
the `debug_invocation_candidates` transform fingerprint.

`runtime_verification_requests.jsonl` packages those candidates into explicit,
freshness-bound request rows with dispositions such as
`READY_FOR_VERIFICATION`, `NEEDS_INPUT`, `AMBIGUOUS_TARGET`,
`DYNAMIC_TARGET`, `STALE_SOURCE_BINDING`, `INCOMPLETE_COVERAGE`, and
`BLOCKED_POLICY`. A ready request only means the static source, symbol,
candidate, input artifacts, environment manifest, analysis handoff, containment,
profile, and resource limits are exact enough for a downstream verifier to try.
It is not runtime proof and must not contain stdout, stderr, exit codes,
debugger observations, accepted effects, or Memory promotion claims.

## Related Skills

| Skill | Relationship |
|-------|--------------|
| `/memory` | Storage backend — lesson records use compatibility storage; structured code projection uses `/code/projection/apply` |
| `/taxonomy` | CWE extraction engine (Phase 2) |
| `/monitor-codebase` | Nightly orchestrator that calls `rescan` |
| `/treesitter` | Structured symbol extraction for the memory-backed code index |
| `/scheduler` | Cron job registration |
