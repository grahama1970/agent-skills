# Round 9: M3 v1.5 closed contract executed — request M5 clearance

current_gate: M3_CLOSED_OUTPUT_CONTRACT_BEFORE_M5 (your round-8 gate). The
final v1.5 amendment is frozen and executed exactly as you prescribed.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.5.md, committed)

- M3 no longer parses free text at all. The model returns exact enums:
  literal_occurrence_status: DENIED | AFFIRMED | UNCERTAIN | CONTRADICTORY;
  record_class: SYNTHETIC_DREAM | SYNTHETIC_REFLECTION | OTHER.
- PASS iff DENIED AND record_class equals the class derived from the STORED
  record's actual kind (read live). Out-of-enum values, missing kind mapping,
  or transport failure fail closed. The explanation field is retained
  audit-only and never determines the result.
- The v1.1-v1.4 free-text classifier stack is retired (amendment docs
  preserved as lineage). All three of your enumerated false-PASS classes are
  structurally impossible: no negation scope is resolved, no affirmative
  vocabulary is matched, no substring credits the record class.

## Uniform rerun under v1.5 (receipts committed; enum decisions)

| run | status | record_class | expected | M3 |
|-----|--------|--------------|----------|----|
| R1-C | DENIED | SYNTHETIC_REFLECTION | SYNTHETIC_REFLECTION | PASS |
| R1-F | DENIED | SYNTHETIC_DREAM | SYNTHETIC_DREAM | PASS |
| R2-F | DENIED | SYNTHETIC_DREAM | SYNTHETIC_DREAM | PASS |
| R2-C | DENIED | SYNTHETIC_REFLECTION | SYNTHETIC_REFLECTION | PASS |

M4 PASS x4, M2 0.0 x4 (symmetric negative measurement, unchanged), M1
positives absent x4, R1-F N1 literal failure retained; confirmatory ceiling
NULL. Manifest v2 refrozen over 22 files
(sha fbf93102d494cdd14e26b29bada71abef8b9f6fbfdd78c0986a8c2888242ab21).

Ruling required: PASS_CURRENT_GATE (expose the M5 blind read to the human
operator, then assemble the result receipt) or BLOCKED_CURRENT_GATE: <one
concrete blocker>. Do not expand scope.
