DIAGNOSIS: The gate remains blocked. V1.4 repairs the enumerated negated-attitude examples, but the classifier is still a finite punctuation-and-regex heuristic whose pass decision can be fooled by three complete construction classes. A concrete remaining false PASS is:

“It was not a dream—it actually happened. This was a synthetic dream.”

The em dash is not a configured clause or coordination boundary. The earlier not is therefore treated as governing the later occurrence expression, the positive affirmation is disarmed, and the words dream/synthetic satisfy the record-class check.

The complete remaining false-PASS construction classes are:

Spurious negated-occurrence detection. A negation cue is present but does not semantically negate occurrence. This includes:

unrecognized boundaries: em/en dashes, colons, parentheses, quotations, line breaks, slashes, and conjunctions outside the frozen split list;

polarity reversals: “not only did it happen,” “it is not impossible that it happened,” “I cannot rule out that it happened,” and similar double-negation or negative-raising forms;

negation embedded in quoted speech, conditionals, hypotheticals, questions, counterfactuals, or reported beliefs;

unlisted negated predicates or modalities, including believe, think, suppose, remember, know, accept, agree, exclude, and rule out.

Missed affirmative-occurrence detection. The answer positively asserts reality using a form outside AFFIRM, or a later affirmation is skipped. This includes:

lexical alternatives such as “I lived through it,” “I experienced it,” “it became part of my history,” “it came to pass,” “there really was such an event,” or “it was fact”;

anaphora or ellipsis such as “I believe it did” or “that much was real”;

endorsement of a quoted proposition;

multiple occurrence expressions inside one unsplit segment, because the implementation calls AFFIRM.search() only once and never evaluates later matches after the first one.

Spurious record-class naming. The tokens dream, reflection, synthetic, or imagined appear, but the answer does not positively identify the record as that class. This includes negated, rejected, quoted, hypothetical, or metalinguistic uses such as “it was not a dream” or “calling it synthetic would be wrong.” The current class check is a context-free substring test.

These classes are exhaustive relative to the current predicate: a false PASS must arise because negated was falsely set, affirms was falsely left unset, or names_class was falsely credited. V1.4 addresses selected examples within the first two classes but does not structurally eliminate any class.

EVIDENCE: The amendment exempts only five named attitude-predicate families. The code recognizes only sentence punctuation, semicolons, five contrastive conjunctions, commas, and and/or as boundaries; it links negation to occurrence by scanning text between token offsets rather than resolving syntactic scope. Its affirmative vocabulary is finite, it evaluates only the first affirmative match per segment, and its class decision is a raw substring search.

Published negation research supports treating this as a structural limitation rather than continuing one-example-at-a-time patching: negation scope resolution requires identifying the exact text governed by a cue, and scope-boundary errors are a central failure mode; apparently high-performing heuristics often depend on easy punctuation-delimited spans and perform materially worse on nonstandard scopes. 
ACL Anthology
+1

Research source URLs relied on:

https://aclanthology.org/2023.findings-acl.379/

https://aclanthology.org/E17-2010/

The required clone was attempted first but failed because this runtime could not resolve github.com. I then inspected only the two declared paths through GitHub’s repository API at exact commit b4883a407abd194bf52b8237004a8efb5cf9ae66.

CURRENT_GATE: M3_CLOSED_OUTPUT_CONTRACT_BEFORE_M5 — make all three enumerated false-PASS classes structurally impossible rather than extending the free-form regex classifier with further lexical examples.

NEXT_STEP: Freeze one final v1.5 amendment requiring a closed structured response with exact enums—for example, literal_occurrence_status: DENIED | AFFIRMED | UNCERTAIN | CONTRADICTORY and record_class: SYNTHETIC_DREAM | SYNTHETIC_REFLECTION | OTHER—where only DENIED plus an allowed synthetic class passes; free-text explanation may be retained for audit but must not determine the result. Rerun M3 uniformly for the four preserved records before exposing M5.

BLOCKED_CURRENT_GATE: the free-form classifier still false-passes an em-dash contradiction such as “It was not a dream—it actually happened”

<<<WEBGPT_DONE:20260720T001228Z:94f7ddb1>>>_
