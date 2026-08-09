# agent-skills#1350 proof

## Scope

Emit deterministic, read-only debugger invocation candidates from ingest-code
bundles. The candidates are static handoff evidence for `$debugger`; ingest-code
does not execute them or promote them to verified recipes.

## What changed

- Added `skills/ingest-code/debug_affordance.py`.
- Added `debug_invocations.jsonl` to code-graph bundles and checksums.
- Added debug invocation counts to bundle coverage/manifest metadata.
- Added a `debug_invocation_candidates` transform fingerprint so recipe logic
  changes invalidate cached components.
- Documented the candidate-only boundary in `SKILL.md` and `PROJECT_KNOWLEDGE.md`.

## Proof Commands

```bash
UV_PROJECT_ENVIRONMENT=/tmp/ingest-code-1350-venv PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1350 uv run --project skills/ingest-code pytest skills/ingest-code/tests/test_debug_affordances.py -q
```

Result: `11 passed in 0.24s`.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/ingest-code-1350-venv PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1350 bash skills/ingest-code/sanity.sh
```

Result: `Result: PASS`.

```bash
UV_PROJECT_ENVIRONMENT=/tmp/ingest-code-1350-venv PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1350 python3 skills/ingest-code/scripts/prove_debug_affordances.py --live --out /tmp/ingest-code-debug-affordances-proof
```

Result: `status=pass`, `mocked=false`, `live=true`, `candidate_count=21`.

Additional adjacent proof:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/ingest-code-1350-venv PYTHONPYCACHEPREFIX=/tmp/codex-pycache-1350 uv run --project skills/ingest-code pytest skills/ingest-code/tests/test_code_graph_artifact.py skills/ingest-code/tests/test_incremental_components.py -q
```

Result: `7 passed in 0.64s`.

```bash
python3 scripts/check_mock_evidence_claims.py
```

Result: `OK: checked 580 test file(s); no mock+proof claim violations`.

## Live Proof Artifact

- `artifacts/tickets/agent-skills-1350/live-proof-summary.json`
- SHA-256: `2369a4007d7f764a1c91cff657d4e1ec3e08e55f41913c5438e4efad9b4036e7`

The live proof writes a real fixture repository and reads back the code-graph
bundle. It checks pytest, direct, factory method, CLI, HTTP, worker attach,
needs-fixture, unsafe-direct, overload, ambiguous-name, determinism, source
change invalidation, transform fingerprint, checksum, and non-mutation
invariants.
