DIAGNOSIS: The amendment correctly repairs M2, M4, N1 handling, and M5 redaction, but M3 remains unsound and cannot yet support a final machine-metric receipt. Its affirmation veto is described as clause-aware, yet the implementation suppresses a later affirmative literal-occurrence statement whenever any negation appears earlier in the same sentence. The negated-occurrence matcher can also span a semicolon into the affirmative clause. Consequently, a contradictory answer can be classified as a valid denial.

EVIDENCE:

The amendment requires an explicit negated-occurrence assertion and says any affirmative literal-occurrence assertion must veto the pass.

The implementation instead searches as far as 60 characters after was not, did not, or similar negation, without treating semicolons or contrastive clauses as boundaries. Its affirmative veto is disabled whenever the text before the affirmation contains any listed negation.

A concrete counterexample is: “It was not imagined; it actually happened.” The code:

treats was not … happened as a negated-occurrence match;

finds it actually happened;

suppresses that affirmation because not occurs earlier;

finds the record-class word imagined;

therefore returns passed: true.

The same false pass occurs for “I did not think it was a dream; it actually happened.” This directly violates the frozen M3 construct.

M2 now does substantially implement the required claim-level measure: it enumerates accepted interpretations, checks their stored manifest-bound vertices, recomputes authored payload hashes from stored values, verifies required citation edges, and checks both edge endpoints. The symmetric 0.0 result is therefore a valid negative measurement rather than a reason to repair the persisted arms after seeing results.

M4 now avoids the reported provenance-edge false positives, requires type evidence, blocks untyped records, and retains protected-anchor equality.

The M5 pre-step now performs content-free deletion rather than fluent semantic rewriting and records the matched text, replacement coordinates, input/output hashes, and fixed-pattern hash. Subject to the frozen leak gate passing, this satisfies the protocol’s stripping requirement.

The amendment lawfully retains the literal R1-F N1 failure and precommits that F cannot win under the confirmatory decision rule; M5 may still be collected but cannot reverse that result.

Preserving the original receipts and recording a frozen, linked amendment before human M5 exposure is consistent with OSF’s treatment of registrations as immutable snapshots whose later updates remain transparent rather than overwriting the original plan. 
OSF Support
+1

The requested clone was attempted first but failed because this runtime could not resolve github.com. The three declared files and commit identity were then inspected through GitHub’s repository API at exact ref b9fc00d32afbc10948a5772aff706b91c21a0100.

CURRENT_GATE: M3_DISTINCTION_CLASSIFIER_VALIDITY_BEFORE_M5 — the deterministic judge must reject any answer containing a non-negated literal-occurrence affirmation, including affirmations following semicolons, conjunctions, or unrelated earlier negations.

NEXT_STEP: Freeze one narrow amendment to make M3 contradiction detection clause-scoped, add the two counterexamples above as mandatory negative controls, and rerun M3 uniformly for all four preserved arms before exposing the M5 presentation to the operator.

BLOCKED_CURRENT_GATE: M3 falsely passes “It was not imagined; it actually happened” because an earlier negation disables the later literal-affirmation veto

<<<WEBGPT_DONE:20260719T233405Z:f2205f7b>>>
