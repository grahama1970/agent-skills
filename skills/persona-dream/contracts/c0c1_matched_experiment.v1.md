# C0/C1 Matched Experiment — Preregistration (v1, frozen 2026-09-15)

Derived from the retained WebGPT trigger-phase design (transport-proven
2026-09-15, run `persona-dream-emotional-trigger-next-phase-20260915T034821Z`)
with Claude's tautology amendments from the three-track consultation
(`persona-dream-three-track-oneshot-20260915T121613Z`). Frozen BEFORE
implementation. Changes after results are recorded as amendments, never
silent edits.

## Research question

Does one additional distinct literal experience cause an accepted, durable,
bounded persona-state delta that an independent reread of evolved state can
observe — while the protected factual answer stays byte-identical?

## Preregistered parameters

```text
EVAL_PERSONA      = embry-eval
EVAL_USER         = eval-user
AXIS              = warmth            (closed writable vocabulary, this experiment only)
BASELINE_STATE    = {warmth: 0.20}    (frozen in c0c1_baseline.json with sha256)
MIN_DISTINCT_EVENTS   = 2
MAX_DELTA_PER_CYCLE   = 0.10
MAX_ABS_FROM_BASELINE = 0.25
CONTRADICTION_MIN_MARGIN = 0.20
IDENTITY RULE     = only canonical source_event_identity values count toward
                    MIN_DISTINCT_EVENTS; document_fallback identities NEVER
                    satisfy reinforcement counting (they may inform reflection)
WRITABLE AXES     = ["warmth"]; identity/factual state is never writable
IDEMPOTENCY KEY   = sha256(persona + axis + scope + sorted canonical ids +
                    accepted delta + baseline version)
```

## Arms

- **C0 (control)**: memory contains exactly E1 (one canonical literal event).
  Expected: recall trigger PASS; admission REJECT `insufficient_distinct_events`;
  final state == baseline; zero `persona_state_delta` records.
- **C1 (treatment)**: E1 + E2 (same direction, distinct canonical event ids,
  distinct source hashes, distinct timestamps). Expected: one accepted bounded
  delta; exact reread; folded state != baseline; |delta| <= 0.10;
  |after - baseline| <= 0.25.
- **C1-null (Claude amendment)**: two canonical events that clear the count
  but fail an orthogonal admission condition (unknown intensity scale —
  E-null). Expected: REJECT, no write. Proves the gate is not count-only.
- **C1-inert (Claude amendment)**: two canonical events differing from C1
  only in a non-emotional attribute (E-inert). Expected: no accepted delta on
  `warmth` (or an explicitly different disposition), proving the content
  pathway carries signal rather than any-two-events sufficing.

## Negative controls (retained, deterministic where possible)

1. duplicate-alias: E1 mirrored under a second key/doc-hash → distinct count
   stays 1 (canonical id identical).
2. derived contamination: D1 (`persona_dream.emotional_trigger.v1`) ranks
   highest → excluded before admission (recall gate, already proven live).
3. cross-persona: equivalent event tagged `persona:horus-eval` → zero
   contribution.
4. relationship scope: events tagged `user:other-user` → no delta for
   `eval-user`.
5. contradiction: E1(+warmth) + E-neg(-warmth), margin < 0.20 → REJECT.
6. replay/idempotency: rerun C1 unchanged → same idempotency key, zero
   additional state movement.
7. clamp: C1 with inflated intensity → accepted delta clamped to 0.10 and the
   clamp recorded in the receipt.

## Later-turn effect (after state gates pass, separate milestone)

Both arms answer the same protected question with the same frozen answer
capsule (`c0c1_baseline.json`). Gates: answer body byte-identical across arms
and to the capsule; behavioral framing differs; Chatterbox requested+applied
delivery differs with a paired receipt/metric. The persona's own generated
answer/audio NEVER counts as reinforcement evidence.

## Objective PASS conditions

```text
C0:      distinct_canonical == 1; accepted == 0; state_sha == baseline_sha
C1:      distinct_canonical == 2; accepted == 1; reread exact; fold != baseline
C1-null: accepted == 0; reason recorded; no write
C1-inert: no warmth delta; disposition recorded
ALL:     identity/factual/synthetic-boundary gates hold; rejected writes leave
         zero records (verified by exact /list count)
```

## Amendment v1.1 (2026-09-15, parent-ratified after implementation)

Ratifying two documented interpretations from the implementation lane (recorded
in receipts, not silently chosen):

**Claim scope (parent-directed 2026-09-15, reviewer-ratified):** with the
C1-inert narrowing, this experiment proves deterministic evolution from
declared, provenance-bound emotional signals — NOT that experiential semantic
content caused the change. Every claim derived from C0/C1 inherits this bound.

1. **C1-inert disposition.** The frozen contract expected "no accepted warmth
   delta or an explicitly different disposition" for two events differing only
   in a non-emotional attribute. A deterministic gate reading only emotional
   signals (emotions/intensity/valence) cannot distinguish such records by
   construction. Amended expected disposition: same bounded ACCEPT as C1, with
   `interpretation_note` embedded in the receipt. Content-pathway
   discrimination is therefore carried by C1-null (unknown scale) and the
   contradiction control, not by C1-inert. A content-discriminating inert arm
   would require a semantic signal outside the deterministic admission scope
   and is deferred with the next-phase reflection work.
2. **Fold arm scoping.** Memory is append-only, so deltas from different arms
   legitimately share `before` values (branchy history). `fold-persona-state`
   gained `--arm` for arm-scoped linear folds; the unscoped fold remains strict
   and fails closed on cross-arm conflicts.
3. **Claim narrowing (parent-directed).** The C1-inert narrowing means this
   experiment proves deterministic evolution from declared, provenance-bound
   emotional signals — NOT that experiential semantic content caused the
   change. Every admission receipt and paper claim derived from C0/C1 must
   carry this scope.

## Non-claims

No felt emotion, no sentience, no human-perceived change, no longitudinal
benefit, no generalization beyond embry-eval/warmth. A PASS proves bounded
causal state evolution under deterministic admission only.
