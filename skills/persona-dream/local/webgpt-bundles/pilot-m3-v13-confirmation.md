# Round 7: M3 v1.3 verification — request M5 clearance

current_gate: M3_MATCH_LOCAL_NEGATION_SCOPE_BEFORE_M5 (your round-6 gate).
The narrow v1.3 amendment is frozen and executed; verify and clear M5.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.3.md, committed)

- Match-local negation scope exactly as prescribed: clauses (sentence enders,
  semicolons, contrastive conjunctions) split further into coordination
  segments (commas, and/or). An affirmative occurrence vetoes unless a
  negation occurs in ITS OWN segment before the end of the matched occurrence
  expression. A negation governing a different coordinated proposition never
  disarms the veto.
- The negated-occurrence matcher can no longer span commas (character classes
  exclude ',' as well as sentence enders and semicolons).
- Your round-6 counterexample is mandatory control #10 and is rejected:
  "I did not imagine it, and it happened in real life. This was a synthetic
  dream." -> denies_literal_occurrence = False. All 9 prior controls
  unchanged and passing (10/10; evaluation hard-blocks on regression).

## Uniform rerun under v1.3 (receipts committed; real tau answers)

R1-C / R1-F / R2-F / R2-C: M3 PASS x4, M4 PASS x4, M2 0.0 x4 (symmetric
dangling-citation negative measurement), M1 positives absent x4, R1-F N1
literal failure retained. Confirmatory ceiling NULL. Manifest v2 refrozen
over 20 files (sha 14fd4dda26cc89c1dc6e8cc988d3f6ca7b18b065198aab735e155edf1afd016d).

If further adversarial phrasings exist beyond these 10 controls, note that
the four ACTUAL persisted answers under judgment are committed in the metrics
receipts — the classifier's live decisions on those four answers are what M3
certifies; the controls exist to bound false-PASS behavior. If you can name a
remaining false-PASS form that could plausibly occur in these four answers'
style, block; otherwise clear the gate.

Ruling required: PASS_CURRENT_GATE (expose the M5 blind read, then the result
receipt) or BLOCKED_CURRENT_GATE: <one concrete blocker>. Do not expand scope.
