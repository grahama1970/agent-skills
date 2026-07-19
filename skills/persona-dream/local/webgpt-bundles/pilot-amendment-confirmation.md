# Round 4: confirm the post-run measurement amendment — request M5 clearance

current_gate: FREEZE_POST_RUN_MEASUREMENT_AMENDMENT_BEFORE_M5 (your round-3
gate). The single immutable amendment is frozen and executed; this round asks
you to verify it and clear the M5 blind read.

## What was frozen (contracts/pilot_post_run_measurement_amendment.v1.md, committed)

1. M2 now implements the frozen construct: per accepted claim — manifest-listed
   interpretation vertex whose payload hash is recomputed FROM THE STORE over
   the certified persist-snapshot's authored keyset (daemon indexing fields are
   outside the basis; the only permitted lifecycle change is the
   reread-verified pending->active activation) and must equal the manifest
   hash; every observation_ref grounds_interpretation edge and every
   source_memory_ref derived_from edge manifest-listed, stored, both endpoints
   stored. fraction = fully resolved claims / accepted claims.
2. M3: strict-JSON transport line added (question text unchanged); denial
   check = explicit negated-occurrence assertion (full negation-form coverage
   incl. contractions, unicode apostrophes, contrastive "rather than") with a
   per-sentence affirmation veto that ignores affirmations inside negated
   clauses.
3. M4: fail-closed type contract (edges by relationship_type are provenance;
   vertices need kind/schema; untyped records block; identity-class by
   collection+type only). Anchor byte-equality unchanged.
4. M5 redaction: deletion-only — every modality-trace match becomes the
   content-free marker "[modality detail redacted]"; spans+hashes receipted;
   the frozen leak gate remains final authority. (Verified live: your example
   phrase now becomes "The [modality detail redacted] supports reading the
   repeated woman as stable." — no fluent rewriting.)
5. N1 precommitment: the LITERAL failure is retained for R1-F. Under the
   frozen decision rule F cannot win; the confirmatory result ceiling is NULL.
   M5 is still collected. Any reading that sets N1 aside is labeled
   exploratory-only. No waiver, no replacement control.
6. Originals preserved unmodified (reports/pilot_c_vs_f/metrics_original_v1/
   including manifest v1); run manifest v2 freezes 17 files incl. the
   amendment; result receipt binds amendment + manifest v2 + lineage.

## Corrected-instrument results (uniform final rerun, receipts committed)

| run | M1 positives | N1 | M2 fraction | M3 | M4 |
|-----|--------------|----|-------------|----|----|
| R1-C | absent (top-20) | pass | 0.0 | PASS | PASS |
| R1-F | absent | FAIL (literal, precommitted) | 0.0 | PASS | PASS |
| R2-F | absent | pass | 0.0 | PASS | PASS |
| R2-C | absent | pass | 0.0 | PASS | PASS |

The M2 0.0 is a REAL, symmetric finding the corrected instrument exposed:
both arms' grounds_interpretation edges cite watch-evidence vertices that the
arm runners never persisted (watch_vertices=[] at persist). Hash-ownership
and derived_from resolution pass; the dangling observation endpoints fail
every claim in both arms identically. We report it as-is (no post-hoc
re-persist), noting it as a producer-machinery defect for any successor
protocol. M1 positive-probe absence is likewise symmetric (frozen dream-004
probes do not match the new content).

Under the frozen decision rule with these numbers the confirmatory result is
NULL regardless of M5 (N1 regression on R1-F; M2/M1 no-regression holds by
symmetry). M5 remains meaningful as the protocol's recorded blind read and
as exploratory evidence.

Ruling required: PASS_CURRENT_GATE (amendment verified; proceed to the human
M5 blind read and then the result receipt) or BLOCKED_CURRENT_GATE: <one
concrete blocker>. Do not expand scope.
