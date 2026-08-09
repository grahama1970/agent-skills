# Proof for agent-skills#1347

## Scope

Implemented the artifact/cache portion of `ingest-code` incremental complete bundle generation:

- added file-component reuse state with source fingerprints, transform fingerprints, serialized symbols, and component hashes;
- wired `scan --treesitter` to parse changed files through Tree-sitter and rehydrate unchanged file components from cache;
- kept complete code-graph bundle generation as the handoff authority;
- documented that backend projection application remains blocked by `agent-skills#1346`.

## Files

- `skills/ingest-code/incremental_state.py`
- `skills/ingest-code/ingest_code.py`
- `skills/ingest-code/scripts/prove_incremental_components.py`
- `skills/ingest-code/tests/test_incremental_components.py`
- `skills/ingest-code/SKILL.md`
- `skills/ingest-code/PROJECT_KNOWLEDGE.md`
- `artifacts/tickets/agent-skills-1347/live-proof-summary.json`

## Deterministic Checks

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1347-integrate uv run pytest \
  skills/ingest-code/tests/test_incremental_components.py \
  skills/ingest-code/tests/test_code_graph_artifact.py -q
```

Result: `7 passed in 0.73s`.

```bash
bash skills/ingest-code/sanity.sh
```

Result: `Result: PASS`.

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result: `OK: checked 577 test file(s); no mock+proof claim violations`.

## Live Filesystem Proof

```bash
PYTHONPYCACHEPREFIX=/tmp/codex-pycache uv run --no-project --isolated \
  --with typer --with httpx --with loguru --with python-dotenv \
  python skills/ingest-code/scripts/prove_incremental_components.py \
  --out /tmp/ingest-code-incremental-components-proof-integrated
```

Result: `status=pass`, `mocked=false`, `live=true`.

Receipt:

- `/tmp/ingest-code-incremental-components-proof-integrated/proof-summary.json`
- `artifacts/tickets/agent-skills-1347/live-proof-summary.json`
- SHA-256: `cb5cddd6fcdd8f3234e3ecde4fcc144a0a0e5481b6ede8c172b285cad6924eb9`

Key readback assertions:

- initial run parsed 3 files;
- exact no-op replay parsed 0 files and reused 3 files;
- one source edit parsed 1 file and reused 2 files;
- delete omitted the removed file and reported 1 deletion;
- transform fingerprint bump reparsed current files;
- corrupt component hash forced recomputation of the affected file.

## Boundary

This closes the complete-bundle component reuse ticket. It does not close
`agent-skills#1346`: `scan --treesitter --code-index` still uses the legacy
per-symbol Memory upsert after local bundle generation until GMO exposes a
governed bundle-application endpoint.
