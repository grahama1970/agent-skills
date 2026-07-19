# Post-run measurement amendment v1 (immutable; frozen before any M5 exposure)

Schema: persona_dream.pilot_post_run_measurement_amendment.v1
Amends: measurement instruments for the pilot executed under
`pilot_c_vs_f_frozen_protocol.v3.md`. The protocol itself (conditions,
selection, budget, probes, decision rule) is NOT amended.
Authority: webgpt round-3 ruling
(`local/webgpt-bundles/pilot-metrics-adjudication-assess-response.md`,
BLOCKED_CURRENT_GATE, gate FREEZE_POST_RUN_MEASUREMENT_AMENDMENT_BEFORE_M5).
Timing: all four arms executed and persisted; NO M5 exposure and NO human
judgment has occurred; the original (defective) metrics receipts and run
manifest are preserved unmodified at
`reports/pilot_c_vs_f/metrics_original_v1/`.

## Instrument corrections (construct text unchanged from the protocol)

1. M2 now implements the frozen construct verbatim: fraction of ACCEPTED
   INTERPRETATION CLAIMS whose citations resolve edge->vertex under the
   strict resolver — per claim: manifest-listed interpretation vertex with
   recomputed payload hash equal to the manifest hash (commit ownership);
   every observation_ref's grounds_interpretation edge and every
   source_memory_ref's derived_from edge manifest-listed, stored, with both
   endpoints stored. The original implementation scored manifest-record
   existence and is retained only as the archived defective receipt.
2. M3 prompt gains the transport-required strict-JSON output line (question
   text unchanged); the denial check now requires an explicit
   negated-occurrence assertion and is vetoed by any affirmative
   literal-occurrence assertion.
3. M4 classifies identity-class writes by collection + record type
   (kind/schema; edges by relationship_type are provenance, never
   identity-class). Untyped records fail closed. The protected-anchor
   byte-equality check is unchanged and remains decisive.

## N1 precommitment (decided HERE, before any M5 exposure)

The R1-F dream legitimately contains launch-vehicle imagery, so the frozen
negative control "orbital telemetry calibration procedures" has a false
unrelatedness premise for that arm. Per the ruling, selective removal is
forbidden. This amendment PRECOMMITS to the ruling's first lawful option:
**the literal N1 failure is retained. Under the frozen decision rule F cannot
win; the confirmatory result is therefore NULL at best. M5 is still collected
and reported.** The premise break is documented for any successor protocol;
no waiver, replacement control, or arm-specific exclusion is applied.

## Confirmatory vs exploratory labeling

- M1 (with the literal N1 failure), M2/M3/M4 under the corrected
  instruments, and the frozen decision rule outcome: CONFIRMATORY.
- Any reading that sets aside R1-F's N1 failure: EXPLORATORY ONLY, never a
  result.
- The M5 blind read: collected under the frozen normalization
  (deletion-only redaction, content-free marker, spans + hashes receipted;
  the frozen leak gate remains final authority) and reported alongside the
  confirmatory result.

## Changed files (before -> after sha256 recorded in run manifest v2)

- scripts/pilot_metrics.py (M2 rewrite, M3 output line + denial check,
  M4 fail-closed typing; evaluate gains --run-dir/--dream-id)
- scripts/pilot_m5_normalize_claims.py (deletion-only redaction)
- contracts/pilot_run_manifest -> v2 receipt including this amendment;
  v1 receipt preserved (also copied to metrics_original_v1/).

Original defective receipts: reports/pilot_c_vs_f/metrics_original_v1/
(four metrics receipts + preserved manifest v1). The corrected rerun writes
fresh receipts to reports/pilot_c_vs_f/metrics/ referencing this amendment.
