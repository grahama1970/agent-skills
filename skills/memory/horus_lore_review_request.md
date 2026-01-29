# Code Review Request: Horus Lore Ingest Modularization

## Summary
Refactored a 2111-line monolithic Python script (`horus_lore_ingest.py`) into 8 modular, debuggable components. Each module is under 500 lines with clear separation of concerns.

## Files to Review

### Module Files (all in `/home/graham/workspace/experiments/pi-mono/.pi/skills/memory/`)

1. **horus_lore_config.py** (136 lines)
   - Warhammer 40k entity lists for rule-based extraction
   - Entity extraction functions
   - Constants for persona retrieval (escape terms, trauma triggers)

2. **horus_lore_chunking.py** (276 lines)
   - Generic text chunking with overlap
   - YouTube transcript chunking with timestamp preservation
   - Audiobook chunking by M4B chapters or regex fallback

3. **horus_lore_embeddings.py** (39 lines)
   - Embedding factory function
   - Supports embedding service or local SentenceTransformer

4. **horus_lore_storage.py** (403 lines)
   - ArangoDB connection and collection management
   - Index, view, and graph creation
   - Edge creation for document relationships (chronological, series, shared entities)

5. **horus_lore_query.py** (468 lines)
   - Hybrid search (BM25 + semantic) with graph traversal
   - Episodic memory queries for past conversations
   - Persona context retrieval for Horus's "subconscious"
   - Context formatting for system prompt injection

6. **horus_lore_ingest.py** (360 lines)
   - YouTube transcript ingestion
   - Audiobook ingestion with chapter extraction
   - Directory ingestion utilities

7. **horus_lore_enrichment.py** (171 lines)
   - LLM batch enrichment preparation for scillm
   - Results application from batch processing

8. **horus_lore_cli.py** (477 lines)
   - Thin CLI entry point
   - Argparse command definitions
   - Command handlers for all subcommands

### Supporting Files
- **horus_lore_sanity.sh** - Test script verifying all CLI commands and imports

## Review Focus Areas

1. **Import Structure**: All modules use absolute imports for script compatibility. Verify no circular dependencies.

2. **Error Handling**: Check for proper exception handling, especially in:
   - ArangoDB connections
   - File I/O operations
   - Embedding service calls

3. **Type Hints**: Verify type annotations are correct and complete.

4. **Code Quality**:
   - Consistent naming conventions
   - Appropriate docstrings
   - No dead code or unused imports

5. **Security Considerations**:
   - Environment variable handling
   - Path validation for file operations

## Quality Gates Already Verified
- All modules < 500 lines (verified by sanity.sh)
- All CLI commands show help without errors
- All module imports succeed
- No circular import issues

## Testing
Run `./horus_lore_sanity.sh` to verify all checks pass.
