# Proof for agent-skills#1348

## Scope

Implemented provenance-safe documentation metadata for `ingest-code` code-symbol
records:

- preserves authored source docstrings as `source_docstring` / `docstring`;
- classifies source docstring status and documentation need from source facts;
- emits `summary_evidence` with a deterministic evidence hash;
- admits derived summaries only as `derived_summary.status="derived_unreviewed"`
  when bound to the current symbol version, content hash, and evidence hash;
- emits canonical `retrieval_text`, `retrieval_text_sha256`, and `purpose_source`;
- keeps source files unchanged.

## Files

- `skills/ingest-code/symbol_summary.py`
- `skills/ingest-code/code_symbol_record.py`
- `skills/ingest-code/code_graph_artifact.py`
- `skills/ingest-code/ingest_code.py`
- `skills/ingest-code/tests/test_symbol_documentation.py`
- `skills/ingest-code/scripts/prove_symbol_documentation.py`
- `skills/ingest-code/SKILL.md`
- `skills/ingest-code/PROJECT_KNOWLEDGE.md`
- `artifacts/tickets/agent-skills-1348/live-proof-summary.json`

## Deterministic Checks

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1348 uv run pytest \
  skills/ingest-code/tests/test_symbol_documentation.py \
  skills/ingest-code/tests/test_code_symbol_record.py \
  skills/ingest-code/tests/test_code_graph_artifact.py \
  skills/ingest-code/tests/test_incremental_components.py -q
```

Result: `18 passed in 0.39s`.

```bash
bash skills/ingest-code/sanity.sh
```

Result: `Result: PASS`.

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result: `OK: checked 578 test file(s); no mock+proof claim violations`.

## Live Filesystem Proof

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1348-rebased uv run --no-project --isolated \
  --with typer --with httpx --with loguru --with python-dotenv \
  python skills/ingest-code/scripts/prove_symbol_documentation.py \
  --out /tmp/ingest-code-symbol-documentation-proof-rebased
```

Result: `status=pass`, `mocked=false`, `live=true`.

Receipt:

- `/tmp/ingest-code-symbol-documentation-proof-rebased/proof-summary.json`
- `artifacts/tickets/agent-skills-1348/live-proof-summary.json`
- SHA-256: `25a5f2e233545395b1df0be5ff753af3f217c8f0980f0476aa96f95885947a4a`

Key readback assertions:

- source file SHA-256 values were identical before and after symbol enrichment;
- authored docstrings were preserved and appeared once in retrieval text;
- undocumented public IO symbols required documentation;
- current derived summaries were used only as unreviewed retrieval purpose text;
- stale derived summaries were rejected;
- generated-file symbols were exempt;
- bundle `symbols.jsonl` carried evidence and retrieval-text hashes.

## Boundary

This covers the `ingest-code` extraction and local artifact contract. It does
not replace the upstream governed bundle-application endpoint tracked by
`agent-skills#1346`.
