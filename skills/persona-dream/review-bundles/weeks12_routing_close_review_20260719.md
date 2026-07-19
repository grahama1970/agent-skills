# WebGPT assess bundle: WEEKS12_AND_ROUTING_CLOSE (2026-07-19)

## current_gate

WEEKS12_AND_ROUTING_CLOSE — are the correctness-critical persona-dream changes
between commits fbdab265 (your last review baseline) and 9246020d sound and
behavior-preserving? All changes are pushed on agent-skills@main; declared
source paths below are exact-commit inspectable.

## One blocking question

Do any of the three change groups below contain a correctness defect or a
silent behavior change that should block a second dream run?

## Objective and context

Since your last review (which ruled PASS_CURRENT_GATE with NEXT_STEP: green
CI), all of the following landed: CI green (403 tests), the P0 state
machine/transactional-persistence/watch-vertex fixes you and a second reviewer
demanded, a 23-caller Tau-routing migration with a strict static gate, six
weeks-1-2 integrity fixes (tautological hash guard, namespaced keys with a
frozen legacy exception, distinct ToM fallback statuses, interpretation
vertices, persona parameterization, causal-family fields), and pilot protocol
v2. Server-side (separate repo, informational): GMO now filters recall on
visibility_state (legacy-null visible) and gates activation server-side.

## Focus areas (review THESE, in order of risk)

1. TRANSACTIONAL PERSISTENCE + STATE MACHINE
   (cognitive_loop_transitions.py, phase15_dream_persistence.py,
   run_cognitive_loop.py): staged writes to persona_dream_canonical_staging,
   per-record exact reread + payload sha, publish, commit manifest as the
   sole visibility authority, idempotency key = sha256(dream_id + return hash
   + phase13 sha + phase14 sha), resume-or-quarantine on rerun. Question: can
   any partial write become visible to recall? Is the idempotency key
   collision-safe and rerun-sound? Do the five transitions actually block a
   BLOCKED/zero-accepted predecessor at every side-effect boundary?
2. TAU ROUTING MIGRATIONS (tau_vlm_composite_review.py, watch qra.py):
   multi-image identity/continuity VLM review now composites frame +
   reference sheets into ONE labeled montage for a single-image Tau node;
   free-text callers wrap/unwrap JSON-object-only node output. Question: does
   montage compositing or JSON wrapping change verdict semantics vs the prior
   multi-image direct calls (resolution loss, label confusion, lost
   system-prompt context)? ArcFace remains the identity authority — verify
   the claim that VLM demotion to advisory holds in the migrated code paths.
3. WRITER/SERVER FIELD-CONTRACT COHERENCE (phase15 fields vs GMO filtering):
   new records carry commit_id + visibility_state="pending" + causal-family
   fields; GMO hides non-active dream-class records except legacy-null.
   Question: any coherence gap — e.g. a record class the writer stamps that
   the server filter misses, or vice versa; the legacy-null exception being
   exploitable to bypass pending-hiding on NEW writes?

## Research context

Distilled from /brave-search (outbox/staged-commit literature): (a) staged
publish + single visibility switch is only sound if consumers honor the
switch universally — any reader bypassing the manifest re-creates the
partial-visibility bug; (b) idempotency keys must derive from the full
logical write-set, not a subset, or replays with changed inputs collide; (c)
without a delete primitive, quarantine must be a terminal readable state, and
compensation must be explicit. Evaluate the implementation against these.
Sources: medium.com/@robert_84835 outbox two-stage commit;
aloknecessary.github.io idempotency patterns; techinterview.org distributed
transactions.

## Commands already run (evidence available)

pytest tests/ -q -> 403 passed (twice); test_weeks12_integrity_defects.py ->
14 passed; check_tau_routing_boundary.py --strict -> exit 0; live dry-run
receipt watch_gauntlet/59b9ff3155d6/cognitive_loop/weeks12_live_dryrun/
(genuine chain accepted, PARTIAL aggregate correctly withheld); 4 live Tau
route receipts under reports/pipeline-complete/.persona-dream/tau_live_receipts/.

## Uncertainty

Whether montage-based VLM review preserves discrimination at reduced
per-image resolution; whether the reread-fidelity float normalization
(0.0->0 tolerated) can mask a real corruption class; whether any recall path
other than GMO's filtered ones can see staging/pending records.

## Acceptance gates for this review

DIAGNOSIS section per focus area with file-grounded findings (or NONE_FOUND
with evidence), then exactly one ruling: PASS_CURRENT_GATE /
BLOCKED_CURRENT_GATE: <one concrete blocker> / REJECTED_SCOPE_EXPANSION.

## Forbidden adjacent scope

No code, no diffs, no re-architecture of GMO or Chatterbox, no pilot-design
review (protocol v2 was separately reviewed), no paid provider calls.
