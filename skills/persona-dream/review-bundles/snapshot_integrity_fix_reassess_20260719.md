# WebGPT re-assess round 4: final-transaction-snapshot integrity fix

## current_gate

FINAL_TRANSACTION_SNAPSHOT_INTEGRITY, your round-3 definition: "one immutable,
final-stamped write-set snapshot must be the sole source for the canonical
plan, every plan payload hash, staging, publication, write proof, and manifest;
manifest deactivation must itself be exactly reread, and publication must not
overwrite records owned by another active commit."

## One blocking question

Does commit c8a71b9c close the gate, or does a correctness defect remain?

## What changed (declared sources, pushed)

1. persist_canonical deep-copies every write-set document before stamping —
   caller-held dicts are never mutated (your mutation-by-reference finding).
2. After stamping + assertion, ONE final_write_set_snapshot is materialized
   (deep-copied stamped documents + authored payload hashes). It is returned
   in the proof (normal and resume paths) and is the sole source for staging,
   publication, the manifest record_index, and the returned plan.
3. run_phase15's allowed path replaces the pre-persist plan with
   canonical_persistence_plan.v2 derived entirely from the returned snapshot:
   transaction_identity == final commit id == manifest _key; every record's
   embedded document + payload_sha256 come from the snapshot; causal fields
   carry the final commit id. The dry-run (not-allowed) path keeps the
   pre-persist plan with transaction_identity: "BOUND_AT_PERSIST" and zero
   writes — rule on whether that split is acceptable.
4. Conditional publication: before any store, each canonical key is checked;
   an existing record whose commit_id != the final commit id (including
   records with NO commit_id) quarantines the transaction as
   FOREIGN_COMMIT_OWNERSHIP with zero publications and no manifest.
5. The compensating inactive manifest write is store_and_reread verified;
   compensation_reread_match is reported; active stays False regardless.

## Fault proofs (your prescribed NEXT_STEP, implemented; 411-test suite green twice)

- test_final_snapshot_plan_integrity: every plan record hash recomputes
  exactly over the embedded document, equals the stored manifest record_index
  hash for the same (collection, key), and every document carries
  commit_id == manifest _key == plan.transaction_identity.
- test_publication_refuses_foreign_commit_ownership: pre-seeded foreign-owned
  key -> FOREIGN_COMMIT_OWNERSHIP quarantine, records_written=0, foreign
  record byte-unchanged, no active manifest for the new transaction.
- test_compensation_write_is_reread_verified: corrupted active manifest ->
  stored compensator quarantined + compensation_reread_match=True reported.
- All prior rounds' proofs still green (identity unity, identical-retry
  resume, forced publication mismatch, deterministic payload).

## Uncertainty (probe these)

(a) The staging path stages the stamped snapshot documents but staging keys
are namespaced by idempotency key — verify no staging/publication divergence
from the snapshot remains. (b) On the resume path the returned plan is also
snapshot-derived, but the prior manifest's record_index hashes are trusted
without recomputation — acceptable? (c) The foreign-ownership check runs
before publication but after staging — is staging under a foreign-owned
canonical situation a residual hazard, or is the staging namespace isolation
sufficient?

## Acceptance gates

DIAGNOSIS grounded in the declared files at the exact commit, then exactly one
ruling: PASS_CURRENT_GATE / BLOCKED_CURRENT_GATE: <one concrete blocker> /
REJECTED_SCOPE_EXPANSION.

## Forbidden adjacent scope

No routing-semantics re-review (issues/428), no code, no GMO architecture, no
paid calls.
