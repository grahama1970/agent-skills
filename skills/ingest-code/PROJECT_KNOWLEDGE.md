# Project Knowledge: ingest-code

**Last updated:** 2026-08-03 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-04-29: `/ingest-code` has been modernized to align with `/memory` as the owner of ArangoDB, Qdrant, embeddings, and hybrid retrieval. The skill now emits rich Tree-sitter `CodeSymbolRecord` documents through `/memory /upsert` into `collection=code_symbols` instead of talking to Qdrant directly.
- Structured code records include repo, branch, commit, path, language, symbol kind/name, qualified name, line range, source code, content hash, imports, parameters, local variables, called symbols, string literals, `lexical_terms`, problem, solution, text, and tags. These fields feed `/memory`'s code retrieval surfaces.
- 2026-08-03: `CodeSymbolRecord` now separates stable logical identity from indexed source-version identity. `symbol_id` is based on repository, branch, normalized path, language, kind, qualified name, and an optional overload discriminator; `symbol_version_id` carries commit, line range, and content hash. The old line/content-shaped key remains available as `legacy_key` for migration diagnostics.
- 2026-08-03: `scan --treesitter --code-index` now emits a deterministic backend-neutral code-graph bundle under `artifacts/ingest-code/code-graph/` before code-symbol Memory upserts. The bundle contains manifest, files, symbols, import edges, diagnostics, coverage, and checksums. Dry-run emits the same artifact bundle and legacy `code-symbols.jsonl` without writing Memory.
- 2026-08-03: Code-graph coverage now fails closed from explicit root-level Tree-sitter extraction outcomes and file statuses, not just Python parse failures. Missing, timed-out, non-zero, malformed, partial, and unexpectedly empty extractor runs set `coverage.complete=false`, `fail_closed=true`, and `reconciliation_eligible=false`. Read/hash failures, binary, too-large, unsupported, Python parse failures, and non-Python files absent from extractor output also fail closed.
- 2026-08-03: Production symbol identity now uses canonical `repository_id` from explicit configuration or normalized Git remote identity instead of checkout directory basename. Local fallback identity is marked non-authoritative and prevents reconciliation eligibility. Python symbol qualification includes nested functions/classes/methods, duplicate declaration groups get deterministic discriminators, unsafe paths are rejected before identity calculation, and `treesitter_scan.py` is only a compatibility wrapper around the canonical producer.
- 2026-08-03: Code-graph bundles now freeze the v1 envelope with per-artifact schema versions, extractor/parser versions, normalized configuration and digest, tracked/untracked source state, exact allowed filenames, and a `bundle_digest` over non-checksum artifact hashes. Bundles publish through a validated sibling temporary directory so stale or interrupted artifacts cannot replace the prior accepted bundle. `.ingest-code.json` records the accepted manifest hash, checksums hash, bundle digest, commit, configuration digest, coverage status, and reconciliation eligibility.
- 2026-08-03: Code-symbol Memory writes now report structured `/upsert`, legacy fallback, and failed records separately. Structured success requires bounded exact-key readback of the current `code_symbols` document. Legacy `/store` or `/learn` fallback is retained for compatibility but marks the write `degraded` and does not enable the marker's healthy hybrid `code_symbols` index claim.
- 2026-08-03: Scan, rescan, and local artifact freshness now share one marker contract. Full `scan --treesitter` markers bind to accepted manifest/checksum/bundle digests, commit/ref, configuration digest, coverage, source hashes, and successful/failed extraction roots. `scan --treesitter --dry-run` is the full offline artifact-export path, while `--no-code-index` disables only Memory structured upsert. Incremental `rescan` markers use `coverage_scope=incremental`, set `reconciliation_eligible=false`, and cannot make a prior full bundle fresh by timestamp alone.
- The `scan` and `rescan` CLIs now support `--treesitter` with `--code-index` / `--no-code-index`. The default with `--treesitter` is to upsert structured code symbols to memory. Legacy lesson-style functional knowledge and CWE records remain for compatibility.
- `.ingest-code.json` now records `code_index` metadata: `backend=memory`, `collection=code_symbols`, `symbols_stored`, `lexical_terms`, `line_ranges`, `content_hashes`, and `hybrid_retrieval_capable`.
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

## Open Questions

- [ ] Rebuild/restart the Docker-hosted memory service from updated `/memory` source so live API behavior includes the latest host-source duplicate suppression and formatter changes.
- [ ] Add focused regression coverage for `scan --treesitter --code-index` proving that a sampled symbol and sampled identifier are retrievable through `/memory` code-symbol recall.
- [ ] Reconcile records written with the previous line/content-shaped keys after Graph Memory Operator gains repository-scoped complete-run retirement; stable IDs alone do not remove old documents.

## Key Files

| File | Purpose |
|------|---------|
| ingest_code.py | Main scan/rescan CLI and ingestion orchestration |
| treesitter_scan.py | Tree-sitter extraction path that emits structured code symbol records |
| code_graph_artifact.py | Deterministic code-graph bundle writer for files, symbols, import edges, diagnostics, coverage, and checksums |
| code_symbol_record.py | `CodeSymbolRecord` model, stable/version identities, and lexical term generation |
| code_memory_client.py | Unix-socket `/memory` wrapper for `/upsert`, `/learn`, and edge storage |
| SKILL.md | Skill contract and operator-facing documentation |
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
