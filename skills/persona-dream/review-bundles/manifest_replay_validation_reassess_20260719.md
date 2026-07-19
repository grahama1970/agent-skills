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
