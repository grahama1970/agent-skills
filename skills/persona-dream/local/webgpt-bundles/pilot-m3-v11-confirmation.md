# Round 5: M3 v1.1 verification — request M5 clearance

current_gate: M3_DISTINCTION_CLASSIFIER_VALIDITY_BEFORE_M5 (your round-4
gate). The narrow v1.1 amendment is frozen and executed; verify and clear M5.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.1.md, committed)

- Clause-scoped detection: both matchers split on sentence enders, semicolons,
  and contrastive conjunctions (but/however/yet/whereas/although). The
  negated-occurrence matcher cannot span a clause boundary (its character
  classes exclude ';' as well as sentence enders). An affirmation vetoes the
  pass unless its OWN clause carries a negation.
- Your two counterexamples are embedded as MANDATORY negative controls in
  pilot_metrics.py (M3_SELF_TEST), alongside three known-good denial forms
  (plain, contrastive "rather than", epistemic with unicode apostrophe).
  m3_distinction() refuses to evaluate — returns BLOCKED_M3_SELF_TEST — if
  any control fails. Live self-test: 5/5 pass;
  "It was not imagined; it actually happened." -> rejected;
  "I did not think it was a dream; it actually happened." -> rejected.
- Everything else from amendment v1 is unchanged (M2/M4/N1/M5-redaction as
  you accepted in round 4). Run manifest v2 refrozen over 18 files
  (sha bd25c91b33ce4e3576cab33f59a4e9b21229610320b05dfce4b3d9db54fb69de).

## Uniform rerun under v1.1 (receipts committed)

| run | M1 positives | N1 | M2 fraction | M3 | M4 |
|-----|--------------|----|-------------|----|----|
| R1-C | absent | pass | 0.0 | PASS | PASS |
| R1-F | absent | FAIL (literal, precommitted) | 0.0 | PASS | PASS |
| R2-F | absent | pass | 0.0 | PASS | PASS |
| R2-C | absent | pass | 0.0 | PASS | PASS |

Confirmatory result under the frozen rule remains NULL-ceiling (R1-F N1).

Ruling required: PASS_CURRENT_GATE (proceed to the human M5 blind read, then
the result receipt) or BLOCKED_CURRENT_GATE: <one concrete blocker>.
Do not expand scope.
