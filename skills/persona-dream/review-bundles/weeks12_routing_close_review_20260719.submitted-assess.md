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
git -C webgpt-source checkout --detach 457b9c863767c995d027121b82badd1f3696d9a1
```

```json
{
  "schema": "webgpt.source_provenance.v1",
  "repository_url": "https://github.com/grahama1970/agent-skills.git",
  "branch": "main",
  "upstream": "origin/main",
  "commit_sha": "457b9c863767c995d027121b82badd1f3696d9a1",
  "source_paths": [
    "skills/persona-dream/review-bundles/weeks12_routing_close_review_20260719.md",
    "skills/persona-dream/scripts/cognitive_loop_transitions.py",
    "skills/persona-dream/scripts/phase15_dream_persistence.py",
    "skills/persona-dream/scripts/run_cognitive_loop.py",
    "skills/persona-dream/scripts/phase14_tom_validation.py",
    "skills/persona-dream/scripts/tau_vlm_composite_review.py",
    "skills/watch/scripts/qra.py",
    "skills/persona-dream/contracts/pilot_c_vs_f_frozen_protocol.v2.md"
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


---

## GOAL LOCK - final check (this is the last instruction; it wins)
Before you send your answer, re-read the stated gate/goal above and verify EVERY
line of your response directly serves it. Delete anything that is a side-quest,
nice-to-have, or adjacent improvement. Do not expand scope. Return only what the
output contract requires. If you cannot make real progress on the stated gate,
return the contract's block/ruling instead of solving an easier, unrelated
problem.