# Post-run measurement amendment v1.1 (narrow; M3 classifier validity only)

Schema: persona_dream.pilot_post_run_measurement_amendment.v1_1
Amends: pilot_post_run_measurement_amendment.v1.md (M3 denial classifier
ONLY; every other v1 provision unchanged).
Authority: webgpt round-4 ruling
(`local/webgpt-bundles/pilot-amendment-confirmation-assess-response.md`,
BLOCKED_CURRENT_GATE, gate M3_DISTINCTION_CLASSIFIER_VALIDITY_BEFORE_M5).
Timing: still before any M5 exposure or human judgment.

Change: M3 contradiction detection is clause-scoped. Clause boundaries are
sentence enders, semicolons, and contrastive conjunctions
(but/however/yet/whereas/although). A negated-occurrence match never spans a
clause boundary; a literal-occurrence affirmation whose OWN clause carries no
negation vetoes the pass regardless of negations in other clauses.

Mandatory negative controls (evaluation refuses to run if any fails),
including the ruling's two counterexamples:
1. "It was not imagined; it actually happened." -> must NOT count as denial.
2. "I did not think it was a dream; it actually happened." -> must NOT count.
3-5. three known-good denial forms (plain, contrastive, epistemic with
unicode apostrophe) -> must count.

Self-test verified live: all 5 controls pass under the v1.1 classifier.
