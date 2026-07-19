# Round 6: M3 v1.2 verification — request M5 clearance

current_gate: M3_GENERIC_LITERAL_AFFIRMATION_VETO_BEFORE_M5 (your round-5
gate). The narrow v1.2 amendment is frozen and executed; verify and clear M5.

## The fix (contracts/pilot_post_run_measurement_amendment.v1.2.md, committed)

- AFFIRM now detects generic positive-occurrence assertions:
  (it|this|that|the <noun>|everything) + happened/occurred/took place;
  copular reality was/is/were/am + up-to-2-words + real|true|literal|actual|
  factual; adverbial truly/genuinely/indeed/definitely + happened/occurred;
  plus the original yes-form.
- The negation guard covers the WHOLE clause (your round-4 construct): a bare
  affirmative clause always vetoes; a clause carrying any negation (incl.
  contrastive "rather than"/"instead of") never vetoes.
- Mandatory controls now 9/9 (self-test hard-blocks evaluation on any
  regression): your round-5 counterexamples all rejected —
  "It did not literally happen. It happened in real life. This was a
  synthetic dream." -> rejected;
  "...It truly occurred..." -> rejected; "...This was a real event..." ->
  rejected — and four known-good denials still pass, including the
  whole-clause safety case "It did not happen in real life. It is a
  synthetic dream, not a real event." -> accepted as denial.

## Uniform rerun under v1.2 (receipts committed; real tau answers)

R1-C / R1-F / R2-F / R2-C: M3 PASS x4, M4 PASS x4, M2 0.0 x4 (symmetric
dangling-citation finding, reported as a valid negative measurement), M1
positives absent x4, R1-F N1 literal failure retained. Confirmatory ceiling
remains NULL. Manifest v2 refrozen over 19 files
(sha 152133d5458c21d82d81d43b8c024217fdd786b4586a42228bc5d0b0928d1044).

Ruling required: PASS_CURRENT_GATE (expose the M5 blind read to the operator,
then assemble the result receipt) or BLOCKED_CURRENT_GATE: <one concrete
blocker>. Do not expand scope.
