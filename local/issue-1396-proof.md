# agent-skills #1396 closure proof

Issue: `#1396 -- ingest-code: emit freshness-bound runtime verification requests for static invocation candidates`
Repository: `grahama1970/agent-skills`

## Implemented

- Added `ingest-code.runtime_verification_request.v1` rows in `artifacts/ingest-code/runtime_verification_requests.jsonl`.
- Added `runtime_verification_request.py` with deterministic request building and `ingest-code.runtime_verification_request_verification.v1` readback verification.
- `scan` and `rescan` emit runtime verification requests after the analysis handoff and record the artifact in `.ingest-code.json`.
- Requests bind candidate id/digest, repo/branch/commit/worktree disposition, scope, canonical bundle/checksum digest, generation id when available, symbol id/version/content hash, source path/span/hash, invocation target, exact fixture refs or unresolved-input reasons, downstream profile, contained file grants, resource limits, environment manifest, analysis handoff, proof scope, identity digest, and non-claims.
- Dispositions implemented: `READY_FOR_VERIFICATION`, `NEEDS_INPUT`, `NEEDS_HUMAN_DECISION`, `UNSUPPORTED_PROFILE`, `AMBIGUOUS_TARGET`, `DYNAMIC_TARGET`, `STALE_SOURCE_BINDING`, `INCOMPLETE_COVERAGE`, and `BLOCKED_POLICY`.
- Runtime result fields such as stdout, stderr, exit code, observations, accepted effects, and debugger receipts are rejected by the static request verifier.
- Request emission is outside the canonical code-graph bundle digest.

## Deterministic proof

Mocked: yes for existing focused projection/freshness test doubles.
Live: no for this command.

```text
uv run --project skills/ingest-code --locked pytest skills/ingest-code/tests -q
69 passed in 10.55s
```

```text
bash skills/ingest-code/sanity.sh
Result: PASS
```

```text
python3 scripts/check_mock_evidence_claims.py
OK: checked 628 test file(s); no mock+proof claim violations
```

## Agentic eval proof

Mocked: false.
Fixture-backed: true.
Live services: false.

```text
/home/graham/workspace/experiments/agent-skills/skills/agentic-evals/run.sh run skills/ingest-code/fixtures/agentic_eval.json --output local/issue-1396-agentic-evals-report.json
```

Receipt:

```text
local/issue-1396-agentic-evals-report.json
```

Result:

- readiness: `READY`
- cases: 5
- trials: 15
- passed trials: 15

## Live readback proof

Mocked: no.
Live: yes.

Emit-mode scanner readback:

```text
/tmp/issue-1396-live-emit-t2zBFO/runtime-request-summary.json
```

Result:

- real `run.sh scan`
- Tree-sitter static bundle emitted
- projection mode: `emit`
- request rows: 5
- dispositions: `READY_FOR_VERIFICATION=4`, `NEEDS_INPUT=1`
- all request verifications passed: `true`
- runtime result fields present: `false`

Memory/GMO apply readback:

```text
/home/graham/workspace/experiments/memory/src/issue-1396-apply-20260813T154605Z/runtime-request-apply-summary.json
```

Result:

- real `run.sh scan`
- Tree-sitter static bundle emitted
- projection mode: `apply`
- real Memory/GMO generation receipt
- generation id: `cg_3c4a4c167b79a62cea4d99adcd5a17fdf3086e00f7a65317`
- request rows: 4
- all request verifications passed: `true`
- all rows bind generation: `true`

## Proof boundary

mocked: yes for focused existing pytest doubles around projection and freshness clients
live: yes for real `ingest-code` runner, Tree-sitter extraction, emit-mode request readback, Memory/GMO apply, and generation-bound request readback

This proof does not claim target-code execution, debugger observations, Memory promotion from request rows, Tau node acceptance, model summaries, or semantic correctness.
