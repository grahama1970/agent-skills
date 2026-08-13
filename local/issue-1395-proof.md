# agent-skills #1395 closure proof

Issue: `#1395 -- ingest-code: emit a versioned analysis handoff without changing canonical code-graph identity`
Repository: `grahama1970/agent-skills`

## Implemented

- Added `ingest-code.analysis_handoff.v1` emission and `ingest-code.analysis_handoff_verification.v1` readback verification.
- `scan` and `rescan` now emit `artifacts/ingest-code/analysis_handoff.json` by default for Tree-sitter static bundles, with `--emit-analysis-handoff` for a deterministic alternate output path.
- The handoff binds source identity, canonical bundle digest, checksums digest, environment manifest digest, artifact inventory, coverage/reconciliation eligibility, projection request/apply provenance, allowed downstream analysis profiles, proof scope, and explicit non-claims.
- The verifier reads every referenced static artifact, recomputes digests and JSONL counts, verifies checksums, checks source hashes against the current source files, validates environment/projection references, and fails closed for path escapes or unsupported artifact/media changes.
- Emit-only handoffs keep `generation_id: null`; apply handoffs bind a Memory/GMO generation id and receipt digest.
- Incomplete coverage blocks downstream absence/exhaustive/callgraph/runtime claim classes.
- Canonical code-graph identity remains independent from the handoff path, emission timestamp, kernel executions, model summaries, host-call receipts, and derived claims.
- Strengthened the committed `fixtures/agentic_eval.json` with positive, negative, and adversarial cases.

## Deterministic proof

Mocked: yes for existing focused projection/freshness test doubles.
Live: no for this command.

```text
uv run --project skills/ingest-code --locked pytest skills/ingest-code/tests -q
63 passed in 7.56s
```

```text
bash skills/ingest-code/sanity.sh
Result: PASS
```

```text
python3 scripts/check_mock_evidence_claims.py
OK: checked 626 test file(s); no mock+proof claim violations
```

## Agentic eval proof

Mocked: false.
Fixture-backed: true.
Live services: false.

```text
/home/graham/workspace/experiments/agent-skills/skills/agentic-evals/run.sh run skills/ingest-code/fixtures/agentic_eval.json --output local/issue-1395-agentic-evals-report.json
```

Receipt:

```text
local/issue-1395-agentic-evals-report.json
```

Result:

- readiness: `READY`
- cases: 4
- trials: 12
- passed trials: 12

## Live readback proof

Mocked: no.
Live: yes.

Emit-mode scanner readback:

```text
/tmp/issue-1395-live-emit-545mOR/emit-summary.json
```

Result:

- real `run.sh scan`
- Tree-sitter static bundle emitted
- projection mode: `emit`
- analysis handoff verification: `PASS`
- verification errors: `[]`

Memory/GMO apply readback:

```text
/home/graham/workspace/experiments/memory/src/issue-1395-apply-20260813T153155Z/apply-summary.json
```

Result:

- real `run.sh scan`
- Tree-sitter static bundle emitted
- projection mode: `apply`
- real Memory/GMO `/code/projection/apply`
- projection receipt status: `applied`
- generation id: `cg_afa0d435bc00bd32e5924553718fe540a697686b4a4d0035`
- analysis handoff verification: `PASS`
- verification errors: `[]`

Same-static emit/apply comparison:

```text
/home/graham/workspace/experiments/memory/src/issue-1395-apply-20260813T153155Z/same-static-comparison.json
```

Result:

- apply handoff verification: `PASS`
- emit handoff verification: `PASS`
- static diffs: `[]`
- dynamic diffs only: `emitted_at`, `generation_provenance`, `handoff_identity_digest`, `projection_artifacts`
- `differ_only_projection_generation_provenance: true`

## Proof boundary

mocked: yes for focused existing pytest doubles around projection and freshness clients
live: yes for real `ingest-code` runner, Tree-sitter extraction, emit-mode handoff readback, Memory/GMO apply, generation receipt, and same-static emit/apply comparison

This proof does not claim runtime debugger proof, model summary truth, semantic correctness, or Memory activation from emit-only requests.
