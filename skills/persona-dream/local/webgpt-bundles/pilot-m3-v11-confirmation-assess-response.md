DIAGNOSIS: The v1.1 amendment fixes the two mandated semicolon counterexamples, but it still does not enforce its stated rule that any non-negated literal-occurrence affirmation vetoes M3. The classifier recognizes affirmations only in the narrow forms yes … happen or it/this/that really|actually|literally happened; ordinary affirmations remain invisible. Therefore M3 is still capable of false PASS results, and the human M5 presentation should not yet be exposed.

EVIDENCE: The amendment requires clause-scoped detection and says an affirmation in its own non-negated clause must veto the denial. The implementation’s affirmative matcher is much narrower than that requirement, while the aggregate decision accepts any detected negation when that narrow matcher finds no affirmation. The five self-tests cover the two requested actually happened counterexamples but do not cover an unmodified bare affirmative.

A concrete false pass remains:

“It did not literally happen. It happened in real life. This was a synthetic dream.”

The first sentence supplies negated = true; the second is an explicit literal-occurrence affirmation but does not match AFFIRM; the third supplies the required record-class words. m3_distinction() therefore produces denies_literal_occurrence = true, names_record_class = true, and passed = true. A similar false pass occurs with “It truly occurred” or “This was a real event.”

The preserved v1→v1.1 amendment lineage is methodologically acceptable: OSF guidance supports timestamped, justified registration updates while preserving the frozen original. That transparency does not compensate for the implementation failing its amended construct. 
OSF Support
+1

The prescribed clone was attempted first but failed because this runtime could not resolve github.com; I then inspected only the two declared files through GitHub’s repository API at exact ref 64aa0a96e9b142f9f160ee88bfa626f3df6bf806.

CURRENT_GATE: M3_GENERIC_LITERAL_AFFIRMATION_VETO_BEFORE_M5 — the classifier must reject every explicit positive assertion that the event happened, occurred, was real, or formed literal history, not only assertions containing yes, really, actually, or literally.

NEXT_STEP: Freeze one narrow v1.2 amendment adding generic positive-occurrence detection and mandatory negative controls for “It happened in real life,” “It truly occurred,” and “This was a real event”; rerun M3 uniformly for all four preserved arms and expose M5 only after every control and rerun passes.

BLOCKED_CURRENT_GATE: M3 falsely passes “It did not literally happen. It happened in real life. This was a synthetic dream.”
