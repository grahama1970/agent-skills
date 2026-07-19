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
git -C webgpt-source checkout --detach 4a0c09e864c4eeae430054dd8de66f9719f6d259
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "4a0c09e864c4eeae430054dd8de66f9719f6d259",
  "source_paths": [
    "skills/persona-dream/review-bundles/manifest_replay_validation_reassess_20260719.md",
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

# WebGPT re-assess round 5: active-manifest replay validation fix

## current_gate

ACTIVE_MANIFEST_REPLAY_VALIDATION, your round-4 definition: "an existing
manifest may be resumed only when its transaction identity, Phase 13/14
hashes, active/quarantine state, record count, and complete (collection, key,
payload_sha256) index exactly match the final stamped snapshot and the
reverified canonical records."

## One blocking question

Does commit 7c517c8e close the gate, or does a correctness defect remain in
the transaction layer? If none remains, rule PASS so the loop can terminate.

## What changed (declared sources, pushed)

1. Resume branch now validates the complete prior-manifest binding against the
   final stamped snapshot before accepting: idempotency_key equality,
   phase13/14 sha equality, active is True and not quarantined, record_count
   == expected, and the full (collection, key, payload_sha256) index dict ==
   the snapshot-derived expected index. Only then, and only with every record
   rereading exactly, does it resume.
2. Any binding mismatch quarantines with reason
   PRIOR_MANIFEST_BINDING_MISMATCH via a store_and_reread-VERIFIED inactive
   write; quarantine_reread_match is recorded in the quarantine object.
3. Your prescribed fault proof, implemented and green (412-test suite, twice):
   test_corrupted_prior_manifest_index_quarantines_on_retry — clean commit,
   then ONLY the stored active manifest's record_index payload hashes
   tampered, then retry: resumed=False, quarantine reason
   PRIOR_MANIFEST_BINDING_MISMATCH, quarantine_reread_match=True, stored
   manifest active=False quarantined=True, canonical_dream_memory_written
   False. All prior rounds' proofs still green (snapshot/plan integrity,
   identity unity, foreign-commit refusal, compensation reread,
   identical-retry resume, forced publication mismatch, deterministic
   payload).

## Uncertainty (probe these)

(a) The quarantine path spreads **prior into the quarantine doc — if the
prior manifest contains fields corrupted to non-serializable or oversized
values, can the verified quarantine write itself fail, and is the resulting
state (quarantine_reread_match=False, canonical_written=False) acceptable?
(b) Round-4's residual staging question: staging occurs in a dedicated
namespace keyed by idempotency key before the foreign-ownership check —
confirm or refute that this is hazard-free. (c) Anything else remaining in
this file that keeps the gate open?

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