# WebGPT re-assess: CANONICAL_COMMIT_REPLAY_AND_VISIBILITY_CORRECTNESS fix

## current_gate

CANONICAL_COMMIT_REPLAY_AND_VISIBILITY_CORRECTNESS — the gate YOU defined in
your prior ruling (weeks12_routing_close_review_20260719-assess-response.md,
verdict BLOCKED_CURRENT_GATE): "an identical canonical retry must resolve to
the existing committed write set without quarantine, and no commit manifest may
become active unless every intended canonical record has independently reread
with the exact expected payload."

## One blocking question

Does commit 2e3d2837 (skills/persona-dream/scripts/phase15_dream_persistence.py
+ the two test files) correctly close that gate, or does a correctness defect
remain in the corrected code?

## What changed (all in the declared source paths, pushed)

1. build_dream_memory_document: created_at now comes from
   deterministic_created_at(interpretation, packet) — a pure function of the
   phase-13/packet timestamps; raises (fail-closed) when no immutable source
   timestamp exists. No utc_now() remains in any canonical payload.
2. compute_idempotency_key: new canonical_plan_sha256 parameter binds the key
   to the hash of the complete normalized write-set payloads (computed after
   the now-deterministic write set is built, before manifest lookup). Legacy
   callers (retroactive reconcile) intentionally omit it so historical
   manifest keys stay stable — evaluate whether that dual-mode is sound.
3. persist_canonical rerun path: when a prior manifest exists and every record
   rereads exactly, it returns the prior commit untouched (records_written=0,
   no restaging, no republish, no quarantine, prior active state reported).
   Drifted/incomplete prior sets still quarantine.
4. write_commit_manifest: active = all_published AND staging_all_match AND
   non-empty record_index; failed sets write quarantined:true,
   quarantine_reason:"PUBLICATION_REREAD_MISMATCH", active:false. The caller's
   canonical_dream_memory_written additionally requires manifest.active.
5. Pre-stage assertion (non-retroactive runs): any canonical record missing
   commit_id or visibility_state raises before staging (closes the
   legacy-null-shaped bypass you flagged as a hardening gap).

## Fault-injection proof (your prescribed NEXT_STEP, implemented)

tests/test_phase15_transactional.py, all green (406-test suite passed twice):
- test_identical_retry_resumes_prior_active_commit: second identical run →
  resumed_from_prior_commit=True, quarantine=None, records_written=0, stored
  state byte-identical before/after retry, manifest stays active.
- test_forced_publication_mismatch_leaves_no_active_manifest: corrupted
  publish → canonical_written=False, stored manifest active=False,
  quarantined=True.
- test_canonical_payload_is_deterministic_and_wall_clock_refused: two builds
  byte-equal; missing source timestamps raise.

## Uncertainty (probe these)

(a) Is the optional canonical_plan_sha256 (legacy dual-mode) exploitable —
e.g. a caller omitting it colliding with a plan-bound key? (b) The resume
path's reverify uses authored-payload comparison; can a legitimate later code
change to payload construction make an intact prior commit read as drift and
quarantine it (schema-evolution replay)? (c) Any remaining path where a
manifest reread failure still leaves active=true stored server-side?

## Acceptance gates

DIAGNOSIS grounded in the declared files at the exact commit, then exactly one
ruling: PASS_CURRENT_GATE / BLOCKED_CURRENT_GATE: <one concrete blocker> /
REJECTED_SCOPE_EXPANSION.

## Forbidden adjacent scope

No re-review of the routing-semantics findings (ticketed as issues/428), no
code, no GMO/Chatterbox architecture, no paid calls.
