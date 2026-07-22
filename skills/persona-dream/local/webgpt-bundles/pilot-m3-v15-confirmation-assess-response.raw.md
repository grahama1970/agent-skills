DIAGNOSIS: The v1.5 closed-output contract resolves M3_CLOSED_OUTPUT_CONTRACT_BEFORE_M5. M3 no longer infers meaning from free-text negation, affirmation vocabulary, punctuation, or record-class substrings. The decision now depends exclusively on two validated enum values, with the expected class independently derived from the stored record’s kind. No remaining code-level defect in the declared files prevents the human M5 blind read.

EVIDENCE: The immutable amendment explicitly supersedes the v1.1–v1.4 free-text classifier and defines a fail-closed rule: only literal_occurrence_status == DENIED together with the stored-kind-derived synthetic class can pass; transport failure, an unsupported record kind, or an out-of-enum value fails. The explanation is expressly audit-only.

The implementation matches that contract:

The status and record-class domains are closed allowlists.

expected_class is derived from the live stored record rather than accepted from the model.

A missing kind mapping blocks before model evaluation.

Both returned values are checked against their allowlists.

PASS is the exact conjunction status == "DENIED" and rclass == expected_class.

The explanation is persisted but excluded from the decision.

This structurally eliminates the three previously enumerated deterministic false-PASS classes: there is no negation-scope detector to over-credit denial, no finite affirmative lexicon to miss an assertion, and no free-text class-name search to credit a negated or quoted use. Enumerated values are the standard mechanism for restricting a property to a finite admissible set. 
JSON Schema
 Structured outputs can enforce output shape while still allowing semantic mistakes inside permitted values, so this ruling is appropriately limited to closure of the classifier contract, not a claim that a model can never choose the wrong enum. 
OpenAI

Given the stated uniform rerun—four DENIED decisions with record classes matching the stored kinds—the M3 results are eligible for the pilot receipt. The retained R1-F N1 failure still caps the confirmatory result at NULL; M5 cannot reverse that frozen machine-metric outcome.

The prescribed clone was attempted first but failed because this runtime could not resolve github.com. I inspected only the two declared paths through GitHub’s repository API at exact commit c4412e854bdcf6b56135c647abdd81e1da80a7e3.

CURRENT_GATE: M3_CLOSED_OUTPUT_CONTRACT_BEFORE_M5 is closed. The frozen M5 presentation may now be exposed to the human operator.

NEXT_STEP: Conduct the frozen, leak-gated M5 blind read and capture the human-authored, order-sealed judgment receipt.

PASS_CURRENT_GATE

<<<WEBGPT_DONE:20260720T002735Z:7cc268ba>>>
