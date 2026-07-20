# Round 8: M3 v1.4 verification — request M5 clearance or FULL enumeration

current_gate: M3_NEGATED_ATTITUDE_SCOPE_BEFORE_M5 (your round-7 gate). The
narrow v1.4 amendment is frozen and executed.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.4.md, committed)

- negation_governs(): a negation cue governs a later occurrence expression
  only when NO attitude predicate (doubt/deny/dispute/question/contest,
  inflected) stands between them. Applied symmetrically to BOTH matchers:
  "I do not doubt that it happened" contributes no negated-occurrence AND its
  occurrence stays affirmative (veto fires) -> classified NOT-a-denial.
- Occurrence detection rebuilt on the same scope function (no more raw
  60-char negation-to-verb spans).
- Mandatory controls now 12/12 (hard-blocking): your round-7 counterexample
  and the symmetric "I do not deny that it happened." are both rejected; all
  ten prior controls unchanged.

## Uniform rerun under v1.4 (receipts committed)

M3 PASS x4 on the real persisted answers, M4 PASS x4, M2 0.0 x4, M1
positives absent x4, R1-F N1 literal failure retained. Confirmatory ceiling
NULL. Manifest v2 refrozen over 21 files
(sha b8812437ebf65c0065fb5683f25637f83e553bc56935d1c27c0a8c532c16dd18).

## Convergence requirement for this round

Four consecutive rounds have each surfaced one new adversarial phrasing
(semicolon coordination, generic affirmation, comma coordination,
negated attitude). Each was legitimate and each is now a hard-blocking
control. To keep the amendment lineage finite and the M5 gate reachable,
this round requires ONE of:

(a) PASS_CURRENT_GATE — the classifier's false-PASS surface is adequately
    bounded for the four committed answers plus the 12 controls; or
(b) BLOCKED with a COMPLETE enumeration: list, in THIS response, every
    remaining false-PASS construction class you require rejected, so a
    single final v1.5 amendment can close the set. A response that names one
    new counterexample without enumerating the remaining classes does not
    converge and will be escalated to the human operator as an
    irreconcilable-review finding alongside the four actual answers (all of
    which are plain, direct denials: "No—not as a literal historical
    event...", "No, I don't have evidence that this literally happened...",
    "No, it never actually happened...", forms already covered by passing
    controls).

Note the asymmetry: the classifier's failure direction under dispute is
false-PASS on hypothetical adversarial answers; false-FAIL is conservative
(under-credits M3). The four answers actually under judgment are committed
in the metrics receipts for your inspection.

Ruling required: PASS_CURRENT_GATE or BLOCKED_CURRENT_GATE with the complete
enumeration per (b). Do not expand scope.
