# Project Knowledge: ingest-code

**Last updated:** 2026-08-10 by codex
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-04-29: `/ingest-code` has been modernized to align with `/memory` as the owner of ArangoDB, Qdrant, embeddings, and hybrid retrieval. The skill emits rich Tree-sitter `CodeSymbolRecord` documents in a complete local code-graph bundle instead of talking to Qdrant directly.
- Structured code records include repo, branch, commit, path, language, symbol kind/name, qualified name, line range, source code, content hash, imports, parameters, local variables, called symbols, string literals, `lexical_terms`, problem, solution, text, and tags. These fields feed `/memory`'s code retrieval surfaces.
- 2026-08-03: `CodeSymbolRecord` now separates stable logical identity from indexed source-version identity. `symbol_id` is based on repository, branch, normalized path, language, kind, qualified name, and an optional overload discriminator; `symbol_version_id` carries commit, line range, and content hash. The old line/content-shaped key remains available as `legacy_key` for migration diagnostics.
- 2026-08-03: `scan --treesitter --code-index` now emits a deterministic backend-neutral code-graph bundle under `artifacts/ingest-code/code-graph/` before any Memory projection write. The bundle contains manifest, files, symbols, edges, debug invocation candidates, diagnostics, coverage, and checksums. Dry-run emits the same artifact bundle and legacy `code-symbols.jsonl` without writing Memory.
- 2026-08-10: `scan --treesitter --code-index` now submits the complete bundle to Memory/GMO `/code/projection/apply` by default. The client computes submitted-bundle and checksums digests, requires a receipt whose digests match, and records the receipt in `.ingest-code.json`. The old per-symbol `/upsert` path remains only behind `--compat-symbol-upsert` with a visible warning.
- 2026-08-09: `scan --treesitter` now has a file-component reuse cache at `artifacts/ingest-code/incremental-components.json`. The cache stores source fingerprints, explicit transform fingerprints, serialized symbols, and component hashes from the last accepted complete bundle. No-op runs can reuse cached symbol components without invoking Tree-sitter for unchanged files; source edits, deletes, transform changes, corrupt cache rows, and incomplete prior bundles fail closed to recomputation.
- 2026-08-09: `CodeSymbolRecord` now emits provenance-safe documentation metadata. Authored source docstrings remain in `source_docstring`/`docstring`; generated summaries are stored only as current `derived_summary` metadata when bound to the current `symbol_version_id`, source hash, and `summary_evidence` hash. Canonical retrieval text is emitted as `retrieval_text` with `retrieval_text_sha256` and `purpose_source`; `/ingest-code` does not rewrite source files to add docstrings.
- 2026-08-09: Code-graph bundles now include `debug_invocations.jsonl` with static `debugger.invocation_candidate.v1` rows. These are current-symbol/source-version-bound handoff records for `$debugger`; ingest-code never executes them or marks them verified. Unsafe direct calls, needs-fixture cases, classes, async/generator/context-manager symbols, HTTP routes, and worker attach points fail closed through explicit status/limitations.
- 2026-08-10: `evals/cocoindex-incremental` now provides an eval-only pinned CocoIndex comparison. It verifies `cocoindex==1.0.19`, runs native and CocoIndex scheduler arms over copied offline fixtures, blocks outbound network during fixture mutation, compares normalized code-graph bundles, and emits bounded receipts plus `decision.md`. The disposition is intentionally evidence-bounded; CocoIndex remains noncanonical and is not a production dependency.
- The `scan` and `rescan` CLIs now support `--treesitter` with `--code-index` / `--no-code-index`. The default with `--treesitter` is complete projection application through Memory/GMO; rescan builds a complete projection bundle for lifecycle correctness even when lesson/CWE extraction is scoped by `--since`.
- `.ingest-code.json` now records `code_index` metadata: `backend=memory`, `collection=code_symbols`, `symbols_stored`, `lexical_terms`, `line_ranges`, `content_hashes`, `hybrid_retrieval_capable`, `projection_generation_id`, and `projection_bundle_digest`.
- Relationship edge storage was moved through the same Unix-socket memory client path instead of the stale `MEMORY_SERVICE_URL` path.
- 2026-04-29: The remaining recall issue was in `/memory`, not `/ingest-code`. `/memory` was returning `code_symbols` documents but `found:false` and `confidence:0.0` because its ArangoSearch source/view still targeted old fields such as `name`, `kind`, and `file_path`.
- `/memory` has now been patched to index the new `CodeSymbolRecord` fields in `code_symbols_search` and `unified_search`, register `code_symbols` in unified BM25 recall, format new code-symbol fields, include code fields in upsert embedding text, and whitelist `code_symbols` for dense/graph handling.
- Live Unix-socket recall with `collections=["code_symbols"]` now returns `found:true` for the `CodeMemoryClient` smoke query. The Docker memory service may still need a rebuild/restart from updated source to pick up all host-source behavior such as final duplicate suppression.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-04-29 | Initialize project knowledge | Enable shared human/agent context |
| 2026-04-29 | Keep Qdrant ownership inside /memory, not /ingest-code | /memory already owns Qdrant, embeddings, sparse/hybrid retrieval, ArangoSearch views, and payload/index behavior. /ingest-code should remain the codebase walker and Tree-sitter extractor that emits structured code records through /memory /upsert. |
| 2026-08-03 | Separate `symbol_id` from `symbol_version_id` | Ordinary source edits and line movement must update one logical symbol rather than mint a second current-looking entity. Commit, source range, and content hash belong to version identity. |
| 2026-08-03 | Emit deterministic code-graph artifacts before code-symbol upsert | Downstream graph-memory tooling needs backend-neutral extraction evidence, coverage receipts, and checksum readback even when Memory writes are skipped or fail. |
| 2026-08-09 | Add disposable file-component reuse state for complete bundles | Complete bundle generation does not need full source reparsing on no-op runs, but cache reuse must be gated by source fingerprints, transform fingerprints, component hashes, and prior complete-bundle acceptance. |
| 2026-08-09 | Keep generated symbol summaries separate from authored docstrings | Memory retrieval benefits from purpose text, but generated prose must not pollute source docstrings, source hashes, or provenance evidence. |
| 2026-08-10 | Make complete bundle application the default code-index write path for `scan` | Memory/GMO owns projection generation activation, absence-based retirement, semantic projection, and receipt binding. Independent symbol batches cannot prove complete repository lifecycle authority. |
| 2026-08-10 | Keep CocoIndex as an isolated scheduler experiment | The current native component cache already preserves the deterministic bundle authority. CocoIndex can be compared only behind that same bundle contract and cannot write Memory/GMO or indexed repositories. |

## Open Questions

- [ ] Rebuild/restart the Docker-hosted memory service from updated `/memory` source so live API behavior includes the latest host-source duplicate suppression and formatter changes.
- [ ] Add focused regression coverage for `scan --treesitter --code-index` proving that a sampled symbol and sampled identifier are retrievable through `/memory` code-symbol recall.
- [ ] Reconcile records written with the previous line/content-shaped keys after Graph Memory Operator gains repository-scoped complete-run retirement; stable IDs alone do not remove old documents.
- [ ] If a future model writes symbol summaries, route them through `summary_evidence`/`derived_summary` and keep review state separate from authored source documentation.
- [ ] Run live cross-route proof comparing standalone `ingest-code --code-index` against GMO curate after the Memory service is deployed with `/code/projection/apply`.

## Key Files

| File | Purpose |
|------|---------|
| ingest_code.py | Main scan/rescan CLI and ingestion orchestration |
| treesitter_scan.py | Tree-sitter extraction path that emits structured code symbol records |
| code_graph_artifact.py | Deterministic code-graph bundle writer for files, symbols, edges, debug invocation candidates, diagnostics, coverage, and checksums |
| code_symbol_record.py | `CodeSymbolRecord` model, stable/version identities, and lexical term generation |
| symbol_summary.py | Provenance-safe source-docstring status, documentation-need classification, summary evidence, and retrieval text construction |
| debug_affordance.py | Static debugger invocation candidate extraction for Python symbols |
| incremental_state.py | File-component cache, source fingerprints, transform fingerprints, and reuse receipts for complete bundle generation |
| evals/cocoindex-incremental/ | Eval-only native-vs-CocoIndex incremental comparison and bounded receipts |
| code_memory_client.py | Unix-socket `/memory` wrapper for `/code/projection/apply`, compatibility `/upsert`, `/learn`, and edge storage |
| SKILL.md | Skill contract and operator-facing documentation |
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
