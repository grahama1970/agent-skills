## GOAL LOCK - read first, obey throughout
Work on ONLY the single current gate / goal stated in this request. You are
FORBIDDEN from drifting into easier, adjacent, or tangential work - no unrelated
refactors, renames, new tooling, extra features, unrequested tests, or broader
architecture - none of which close the stated gate. If the stated gate is
unclear, out of scope, or blocked, say so and stop; do NOT substitute a
different, easier problem to look productive.

## Authoritative source provenance
Use the pushed repository state below as the only source of truth. Clone it and check out the exact detached commit before inspecting the declared paths.

```bash
git clone --filter=blob:none https://github.com/grahama1970/agent-skills.git webgpt-source
git -C webgpt-source checkout --detach e5573e9bf487e71b9fd88e26acc39bd149a98bde
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "e5573e9bf487e71b9fd88e26acc39bd149a98bde",
  "source_paths": [
    "skills/persona-dream/review-bundles/identity_unity_fix_reassess_20260719.md",
    "skills/persona-dream/scripts/phase15_dream_persistence.py",
    "skills/persona-dream/tests/test_phase15_transactional.py"
  ],
  "proof_cwd": "."
}
```

## Research directive
Before answering, use your own web search to research current, authoritative
sources for this problem, and cite the source URLs you relied on. The bundle may
also include a "## Research context" section the project agent gathered via
brave-search; treat it as a starting point, not a limit.

## Output contract: ASSESS
Diagnose where the project agent is blocked or spiraling. Do NOT write code.
Return, in order:
- DIAGNOSIS: <root cause of the block or spiral>
- EVIDENCE: <what in the bundle/research supports it>
- CURRENT_GATE: <the one gate that must be closed next>
- NEXT_STEP: <single concrete action>
End with exactly one ruling line:
PASS_CURRENT_GATE | BLOCKED_CURRENT_GATE: <one concrete blocker> | REJECTED_SCOPE_EXPANSION

---

# WebGPT re-assess round 3: transaction-identity unity fix

## current_gate

CANONICAL_COMMIT_REPLAY_AND_VISIBILITY_CORRECTNESS, narrowed by your round-2
ruling to: "one final plan-bound transaction identity shared by every canonical
record, the canonical plan, the write proof, and the sole active manifest, and
the manifest cannot remain active after its own failed exact reread."

## One blocking question

Does commit 4511b4a0 close the narrowed gate, or does a correctness defect
remain?

## What changed (declared sources, pushed)

1. run_phase15 no longer computes any transaction key; causal_fields carry
   commit_id=None and the persistence-plan receipt states
   transaction_identity: "BOUND_AT_PERSIST".
2. persist_canonical is the sole identity authority: it computes the plan hash
   over the commit-id-less normalized write set, derives the plan-bound key,
   then stamps commit_id = f"commit_{key}" (== the manifest _key) into every
   record BEFORE staging. Post-stamp assertion fails closed if any record's
   commit_id != the final key or visibility_state is missing.
3. write_commit_manifest: if the manifest's own reread mismatches, a
   compensating inactive/quarantined write (reason MANIFEST_REREAD_MISMATCH)
   lands and the returned active is False regardless of compensation outcome.
4. Your prescribed fault proofs, implemented and green (408-test suite, twice):
   - test_transaction_identity_unity: stored records' commit_id == stored
     manifest _key == f"commit_{proof.idempotency_key}".
   - test_manifest_reread_corruption_leaves_stored_manifest_inactive: a
     corrupted active-manifest store yields stored active=False,
     quarantined=True, canonical_written=False.
   - Round-1 tests still green: identical-retry-resumes,
     forced-publication-mismatch, deterministic-payload.

## Uncertainty (probe these)

(a) The plan hash excludes only the commit_id field; is any other
self-referential field present that could break stamp-then-hash determinism on
retry? (b) The compensating manifest write is itself unverified (best-effort
after a failed reread) — is that acceptable given the caller reports
canonical_written=false either way, or does it need its own reread loop?
(c) Schema-evolution: a changed payload now derives a NEW key while canonical
record _keys stay stable — the new transaction stamps and overwrites records
while the OLD manifest may remain active. Server-side GMO activation gating
exists (separate repo) but is not in these sources. Rule on whether
client-side must also refuse to publish over records carrying a different
active commit_id.

## Acceptance gates

DIAGNOSIS grounded in the declared files at the exact commit, then exactly one
ruling: PASS_CURRENT_GATE / BLOCKED_CURRENT_GATE: <one concrete blocker> /
REJECTED_SCOPE_EXPANSION.

## Forbidden adjacent scope

No routing-semantics re-review (issues/428), no code, no GMO architecture, no
paid calls.


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.