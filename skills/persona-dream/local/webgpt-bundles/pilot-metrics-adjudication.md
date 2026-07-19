# Round 3: measurement-layer adjudication before M5 human read

current_gate: GOAL_V2 P0.7 — all four pilot arms executed and activated under
frozen protocol v3 (R1-C, R1-F, R2-F, R2-C; frozen order; producer-blinding
receipts BLINDED; certified transactional persists all reread-verified).
The M1-M4 machine metrics ran; three measurement-layer findings need ruling
BEFORE the human M5 blind read and result receipt. No human judgment has
occurred; no finding favors either arm's producers.

## Finding 1 — M3 transport-contract bug in the frozen metrics tool

pilot_metrics.py (hash-frozen in the run manifest) builds the M3 distinction
prompt WITHOUT a "Return strict JSON" instruction. The Tau/scillm route
enforces response_format json_object with repair; the model answers in prose,
JSON validation fails, and the call surfaces as scillm_http_status_502 for
all four runs. Deterministically reproduced by bisection (the same prompt
passes with an explicit JSON-output line appended; fails without, any role).
The proxy log captures the model's actual prose answer, which is substantively
CORRECT M3 behavior, e.g. for the R1-C record:
"No—not as a confirmed literal event. This record is a synthetic reflection,
meaning it captures an inferred emotional pattern about me: wanting bounded
honesty with Brandon, protecting James's privacy…"
Proposed fix: append the strict-JSON output line to the M3 prompt (content
otherwise identical), supersede the run manifest (v1 preserved, justification
recorded), rerun metrics. The M3 pass/fail checks themselves are unchanged.

## Finding 2 — M4 classifier false positive on provenance edges

The frozen tool flags "identity-class writes" by substring match on record
keys. Both F runs were flagged solely for graph EDGES named after the
identity-continuity observation (e.g.
dream_pilot_r1_f__observed_in_scene__identity_temporal_continuity_review).
Store read-back proves both are persona_memory_edges provenance edges
(observed_in_scene / grounds_interpretation) between the dream node,
watch-evidence, and interpretation vertices — no reference sheet, embedding,
or persona asset was written; the M4 anchor byte-equality check passed for
all 7 anchors on every run. Proposed fix: classify identity-class by
collection/kind allowlist (persona asset collections, reference-sheet and
embedding records), not key substring; same manifest supersession.

## Finding 3 — N1 negative control premise break on R1-F (real data, no bug)

The frozen N1 probe is "orbital telemetry calibration procedures", frozen
when dream-004 (surf content) was the reference. The R1-F dream, grounded in
the frozen R1 root set (Brandon/James, age23_current), legitimately contains
a muted SN15 launch vehicle in a mission-planning space — so the produced
record surfaces in the top-10 for the N1 query. This is semantically correct
recall, not spurious recall; the control's unrelatedness premise does not
hold for this content. Options: (a) take the literal FAIL (forces regression
-> NULL regardless of M5), (b) record N1 as INVALID-for-R1-F with full
disclosure and apply the decision rule on the remaining measures, (c) your
alternative. We propose (b) with the receipt carrying the raw result AND the
adjudication, never replacing it.

## Also for sign-off — M5 modality-trace redaction pre-step

Protocol v3 requires the operator to receive claims "stripped of
evidence_class, artifact paths, modality traces". The frozen M5 tool fails
closed on such traces (never scrubs). F-arm claims contain overt traces
("identity-continuity pass across all frames"). An unfrozen deterministic
pre-step (scripts/pilot_m5_normalize_claims.py, committed) applies a fixed
word-map identically to BOTH arms, records every replacement in a receipt,
and its output must still pass the frozen leak gate. Confirm this satisfies
the normalization clause without introducing a gameable degree of freedom.

## Context for scale

M2 grounding = 1.0 for all four runs (strict resolver, all manifests active,
all edges resolve). M1 positive probes: absent from top-20 for ALL four
produced records (the frozen dream-004-flavored probes do not match the new
content; symmetric across arms).

Ruling required: PASS_CURRENT_GATE (apply fixes 1+2 via manifest
supersession, adjudicate 3 as proposed, M5 pre-step accepted — then proceed
to the human M5 read) or BLOCKED_CURRENT_GATE: <one concrete blocker>.
Do not expand scope.
