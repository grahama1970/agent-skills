# Project Knowledge: ingest-code

**Last updated:** 2026-04-29 12:17 by agent
**Status:** Active development

## Current Understanding

- Project initialized, knowledge tracking started
- 2026-04-29: `/ingest-code` has been modernized to align with `/memory` as the owner of ArangoDB, Qdrant, embeddings, and hybrid retrieval. The skill now emits rich Tree-sitter `CodeSymbolRecord` documents through `/memory /upsert` into `collection=code_symbols` instead of talking to Qdrant directly.
- Structured code records include repo, branch, commit, path, language, symbol kind/name, qualified name, line range, source code, content hash, imports, parameters, local variables, called symbols, string literals, `lexical_terms`, problem, solution, text, and tags. These fields feed `/memory`'s code retrieval surfaces.
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

## Open Questions

- [ ] Rebuild/restart the Docker-hosted memory service from updated `/memory` source so live API behavior includes the latest host-source duplicate suppression and formatter changes.
- [ ] Add focused regression coverage for `scan --treesitter --code-index` proving that a sampled symbol and sampled identifier are retrievable through `/memory` code-symbol recall.

## Key Files

| File | Purpose |
|------|---------|
| ingest_code.py | Main scan/rescan CLI and ingestion orchestration |
| treesitter_scan.py | Tree-sitter extraction path that emits structured code symbol records |
| code_symbol_record.py | `CodeSymbolRecord` model and lexical term generation |
| code_memory_client.py | Unix-socket `/memory` wrapper for `/upsert`, `/learn`, and edge storage |
| SKILL.md | Skill contract and operator-facing documentation |
| PROJECT_KNOWLEDGE.md | Shared project knowledge |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->
